#!/usr/bin/env python3
"""Run the frozen MobileSAM image encoder once per image and cache the result.

Decoder-only fine-tuning never needs the encoder again, so this turns a ~1 s
forward pass per step into a 2 MB file read. Train images are cached twice
(as-is and horizontally flipped) - the only image-level augmentation possible
once the encoder is frozen.

    python scripts/cache_embeddings.py [--root DIR] [--out cache]
"""
import argparse
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import cv2
import numpy as np
import torch
from mobile_sam import sam_model_registry
from mobile_sam.utils.transforms import ResizeLongestSide

HERE = Path(__file__).resolve().parent.parent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/tmp/wound-segmentation/data/Foot Ulcer Segmentation Challenge")
    ap.add_argument("--ckpt", default=str(HERE / "weights" / "mobile_sam.pt"))
    ap.add_argument("--out", default=str(HERE / "cache"))
    args = ap.parse_args(argv)
    root, out = Path(args.root), Path(args.out)

    torch.set_num_threads(4)
    sam = sam_model_registry["vit_t"](checkpoint=args.ckpt).eval()
    tf = ResizeLongestSide(sam.image_encoder.img_size)

    @torch.no_grad()
    def embed(rgb):
        x = torch.as_tensor(tf.apply_image(rgb)).permute(2, 0, 1)[None].float()
        return sam.image_encoder(sam.preprocess(x))[0].half().numpy()   # (256,64,64) fp16

    jobs = []
    for split, flip in (("train", True), ("validation", False)):
        (out / split).mkdir(parents=True, exist_ok=True)
        for f in sorted((root / split / "images").glob("*.png")):
            jobs.append((split, f, False))
            if flip:
                jobs.append((split, f, True))
    print(f"{len(jobs)} encoder passes -> {out}", flush=True)
    t0, done = time.time(), 0
    for i, (split, f, flip) in enumerate(jobs):
        dst = out / split / (f.stem + ("_flip" if flip else "") + ".npy")
        if dst.exists():
            continue
        rgb = cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2RGB)
        if flip:
            rgb = np.ascontiguousarray(rgb[:, ::-1])
        np.save(dst, embed(rgb))
        done += 1
        if done % 50 == 1:
            el = time.time() - t0
            print(f"  [{i+1}/{len(jobs)}] {el/60:.1f} min elapsed, "
                  f"eta {el/done*(len(jobs)-i-1)/60:.0f} min", flush=True)
    (out / "DONE").write_text(f"{len(jobs)} embeddings in {(time.time()-t0)/60:.1f} min\n")
    print("CACHE DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
