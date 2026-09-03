"""Phase 1: fine-tune the MobileSAM mask decoder on FUSeg.

The MedSAM recipe, scaled to a CPU: the image encoder and prompt encoder are
frozen, image embeddings are precomputed once (scripts/cache_embeddings.py), and
only the 4 M-parameter mask decoder is trained. Each step is then a prompt-encode
+ decode on a cached embedding - tens of milliseconds - so 25 epochs over 1,620
embeddings (810 images + horizontal flips) fit in well under an hour without a GPU.

Why this and not a SegFormer / nnU-Net:
  * no pretrained backbones are reachable from this environment, and training a
    segmenter from scratch on 810 images loses to a distilled SAM encoder;
  * it is a drop-in: the result is a full MobileSAM state dict, so Segmenter() loads
    it unchanged and the whole Phase 0 pipeline, CLI and evaluation apply as-is;
  * the box prompt stays. That is the UX Phase 0 established, and training with
    jittered boxes directly attacks the loose-box sensitivity Phase 0 measured.

    python -m wound_proto.finetune --epochs 25 --out weights/mobile_sam_fuseg.pt
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

warnings.filterwarnings("ignore")

ROOT = Path("/tmp/wound-segmentation/data/Foot Ulcer Segmentation Challenge")
IMG = 512          # every FUSeg image is 512 x 512; asserted at load
SAM_IN = 1024      # MobileSAM input frame; boxes are scaled 512 -> 1024


def _jitter_box(mask: np.ndarray, jitter: float, rng) -> np.ndarray:
    """GT bbox dilated per side by U(0.3,1)*jitter - same as evaluate.box_from_mask."""
    ys, xs = np.where(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1 - x0 + 1, y1 - y0 + 1
    j = lambda: rng.uniform(0.3, 1.0) * jitter  # noqa: E731
    box = np.array([x0 - w * j(), y0 - h * j(), x1 + w * j(), y1 + h * j()], dtype=np.float32)
    return np.clip(box, 0, IMG - 1)


class CachedFUSeg:
    """(embedding fp16 .npy, mask png, flipped) triples."""

    def __init__(self, split: str, cache: Path, with_flip: bool):
        self.items = []
        for f in sorted((ROOT / split / "labels").glob("*.png")):
            for flip in ((False, True) if with_flip else (False,)):
                e = cache / split / (f.stem + ("_flip" if flip else "") + ".npy")
                if e.exists():
                    self.items.append((e, f, flip))
        # drop empty masks - nothing to prompt on
        keep = []
        for e, f, flip in self.items:
            m = cv2.imread(str(f), 0)
            assert m.shape == (IMG, IMG), f"{f} is {m.shape}, expected {IMG}x{IMG}"
            if (m > 127).any():
                keep.append((e, f, flip))
        self.items = keep

    def __len__(self):
        return len(self.items)

    def get(self, i):
        e, f, flip = self.items[i]
        emb = torch.from_numpy(np.load(e).astype(np.float32))
        m = cv2.imread(str(f), 0) > 127
        if flip:
            m = np.ascontiguousarray(m[:, ::-1])
        return emb, m


def soft_dice_loss(logits, target, eps=1.0):
    p = torch.sigmoid(logits)
    inter = (p * target).sum(dim=(1, 2, 3))
    return 1 - ((2 * inter + eps) / (p.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3)) + eps)).mean()


def decode_batched(dec, image_embeddings, image_pe, sparse, dense):
    """MaskDecoder.predict_masks for a batch of *different* images.

    The stock decoder repeat-interleaves one image embedding across N prompts
    (one image, many prompts). Training wants the opposite pairing - B images,
    one box each - so this mirrors predict_masks line for line, minus the
    repeat. Same modules, same parameters, so the state dict is unchanged.
    """
    b = image_embeddings.shape[0]
    output_tokens = torch.cat([dec.iou_token.weight, dec.mask_tokens.weight], dim=0)
    tokens = torch.cat((output_tokens[None].expand(b, -1, -1), sparse), dim=1)
    src = image_embeddings + dense
    pos_src = image_pe.expand(b, -1, -1, -1)
    _, c, h, w = src.shape
    hs, src = dec.transformer(src, pos_src, tokens)
    upscaled = dec.output_upscaling(src.transpose(1, 2).view(b, c, h, w))
    # multimask_output=False selects mask token 0 (what SamPredictor / Segmenter use),
    # so only hypernetwork 0 is evaluated; the IoU head is not part of the box UX.
    hyper_in = dec.output_hypernetworks_mlps[0](hs[:, 1, :])[:, None]     # (B,1,32)
    b, c, h, w = upscaled.shape
    return (hyper_in @ upscaled.view(b, c, h * w)).view(b, 1, h, w)


def forward_decoder(sam, emb, boxes_512):
    """emb (B,256,64,64), boxes in 512-px image space -> logits at 512 x 512."""
    boxes = torch.as_tensor(boxes_512 * (SAM_IN / IMG), dtype=torch.float32)
    with torch.no_grad():
        sparse, dense = sam.prompt_encoder(points=None, boxes=boxes, masks=None)
    low_res = decode_batched(sam.mask_decoder, emb, sam.prompt_encoder.get_dense_pe(),
                             sparse, dense)                       # (B,1,256,256)
    return F.interpolate(low_res, (IMG, IMG), mode="bilinear", align_corners=False)


@torch.no_grad()
def validate(sam, ds: CachedFUSeg, boxes: list[np.ndarray]) -> float:
    """Mean Dice on the validation split with fixed pre-drawn jittered boxes."""
    sam.mask_decoder.eval()
    dices = []
    for i in range(len(ds)):
        emb, m = ds.get(i)
        logits = forward_decoder(sam, emb[None], boxes[i][None])
        pred = (logits[0, 0] > 0).numpy()
        inter = np.logical_and(pred, m).sum()
        dices.append(2 * inter / (pred.sum() + m.sum() + 1e-9))
    sam.mask_decoder.train()
    return float(np.mean(dices))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wound_proto.finetune")
    ap.add_argument("--cache", default="cache")
    ap.add_argument("--ckpt", default="weights/mobile_sam.pt")
    ap.add_argument("--out", default="weights/mobile_sam_fuseg.pt")
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--jitter", type=float, default=0.20,
                    help="train-time box dilation; wider than eval's 0.15 on purpose")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log", default="results/finetune/log.json")
    args = ap.parse_args(argv)

    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    from mobile_sam import sam_model_registry

    sam = sam_model_registry["vit_t"](checkpoint=args.ckpt)
    for p in sam.image_encoder.parameters():
        p.requires_grad_(False)
    for p in sam.prompt_encoder.parameters():
        p.requires_grad_(False)
    dec = sam.mask_decoder
    trained = [dec.iou_token, dec.mask_tokens, dec.transformer, dec.output_upscaling,
               dec.output_hypernetworks_mlps[0]]          # the modules on the mask-0 path
    params = [p for m in trained for p in m.parameters()]
    print(f"trainable: {sum(p.numel() for p in params)/1e6:.2f}M "
          f"(mask decoder, single-mask path; {sum(p.numel() for p in dec.parameters())/1e6:.2f}M in decoder)")

    cache = Path(args.cache)
    train = CachedFUSeg("train", cache, with_flip=True)
    val = CachedFUSeg("validation", cache, with_flip=False)
    print(f"train samples {len(train)} (with flips) | val {len(val)}")
    # fixed validation boxes so epoch-to-epoch Dice is comparable
    vrng = np.random.default_rng(1234)
    val_boxes = [_jitter_box(val.get(i)[1], 0.15, vrng) for i in range(len(val))]

    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.01)
    steps_per_epoch = (len(train) + args.bs - 1) // args.bs
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs * steps_per_epoch)
    bce = torch.nn.BCEWithLogitsLoss()

    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    log = dict(args=vars(args), epochs=[])
    base = validate(sam, val, val_boxes)
    print(f"epoch  0  val dice {base:.4f}  (zero-shot baseline, same boxes)")
    log["epochs"].append(dict(epoch=0, val_dice=round(base, 4)))
    best, best_ep = base, 0
    torch.save(sam.state_dict(), args.out)          # never worse than baseline

    sam.mask_decoder.train()
    for ep in range(1, args.epochs + 1):
        t0 = time.time()
        order = rng.permutation(len(train))
        tot, n = 0.0, 0
        for s in range(0, len(order), args.bs):
            idx = order[s:s + args.bs]
            embs, masks, boxes = [], [], []
            for i in idx:
                e, m = train.get(i)
                embs.append(e); masks.append(m); boxes.append(_jitter_box(m, args.jitter, rng))
            emb = torch.stack(embs)
            gt = torch.from_numpy(np.stack(masks)).float()[:, None]
            logits = forward_decoder(sam, emb, np.stack(boxes))
            loss = bce(logits, gt) + soft_dice_loss(logits, gt)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step(); sched.step()
            tot += float(loss) * len(idx); n += len(idx)
        vd = validate(sam, val, val_boxes)
        mark = ""
        if vd > best:
            best, best_ep = vd, ep
            torch.save(sam.state_dict(), args.out)
            mark = "  *saved*"
        print(f"epoch {ep:2d}  loss {tot/n:.4f}  val dice {vd:.4f}  "
              f"lr {sched.get_last_lr()[0]:.2e}  {time.time()-t0:.0f}s{mark}", flush=True)
        log["epochs"].append(dict(epoch=ep, train_loss=round(tot / n, 4), val_dice=round(vd, 4),
                                  secs=round(time.time() - t0)))
        json.dump(log, open(args.log, "w"), indent=1)

    log.update(best_val_dice=round(best, 4), best_epoch=best_ep, baseline_val_dice=round(base, 4))
    json.dump(log, open(args.log, "w"), indent=1)
    print(f"\nbest val dice {best:.4f} at epoch {best_ep}  (baseline {base:.4f})  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
