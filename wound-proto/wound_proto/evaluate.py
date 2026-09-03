"""Evaluation: segmentation on FUSeg, measurement on synthetic fixtures.

  python -m wound_proto.evaluate fuseg --root <FUSeg dir> --split validation
  python -m wound_proto.evaluate synth --n 40

Two numbers come out, and they answer different questions:
  * Dice on FUSeg     - given a loose user box, how good is the boundary?
  * area error, synth - given a perfect boundary, how good is the metric?
The end-to-end synthetic run stacks them, which is what a user experiences.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from .calibrate import calibrate
from .measure import measure
from .segment import Segmenter, postprocess
from .synth import make_fixture


def dice_iou(pred: np.ndarray, gt: np.ndarray) -> tuple[float, float]:
    p, g = pred.astype(bool), gt.astype(bool)
    inter = np.logical_and(p, g).sum()
    ps, gs = p.sum(), g.sum()
    dice = 2 * inter / (ps + gs) if (ps + gs) else 1.0
    union = np.logical_or(p, g).sum()
    iou = inter / union if union else 1.0
    return float(dice), float(iou)


def box_from_mask(mask: np.ndarray, jitter: float, rng) -> np.ndarray | None:
    """GT bbox dilated by `jitter` fraction per side, with random asymmetry.

    Simulates a user drawing a loose rectangle: not tight, not centred.
    """
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1 - x0 + 1, y1 - y0 + 1
    H, W = mask.shape
    j = lambda: rng.uniform(0.3, 1.0) * jitter   # noqa: E731
    box = np.array([x0 - w * j(), y0 - h * j(), x1 + w * j(), y1 + h * j()])
    box[[0, 2]] = np.clip(box[[0, 2]], 0, W - 1)
    box[[1, 3]] = np.clip(box[[1, 3]], 0, H - 1)
    return box


def overlay(img_bgr, gt, pred, box=None):
    out = img_bgr.copy()
    if gt is not None:
        cnts, _ = cv2.findContours(gt.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, cnts, -1, (0, 200, 0), 2)         # green = ground truth
    cnts, _ = cv2.findContours(pred.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, cnts, -1, (255, 80, 0), 2)           # blue = prediction
    if box is not None:
        x0, y0, x1, y1 = [int(v) for v in box]
        cv2.rectangle(out, (x0, y0), (x1, y1), (0, 200, 255), 1)  # yellow = prompt
    return out


# ------------------------------------------------------------------ FUSeg ---
MIN_GT_COMPONENT_PX = 64   # smaller GT blobs are annotation specks, not wounds


def gt_components(gt: np.ndarray, per_wound: bool):
    """Yield the masks the prompt should target: whole mask, or one per wound."""
    if not per_wound:
        yield gt
        return
    n, labels, stats, _ = cv2.connectedComponentsWithStats(gt.astype(np.uint8), connectivity=8)
    comps = [(labels == i) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= MIN_GT_COMPONENT_PX]
    if not comps:                       # everything was specks: fall back to the whole mask
        comps = [gt]
    yield from comps


def eval_fuseg(root: Path, split: str, n: int | None, jitter: float, out: Path,
               seed: int = 0, ckpt: str | None = None, per_wound: bool = False):
    """Zero-shot Dice on FUSeg.

    per_wound=False: one box from the bbox of the entire GT mask. Wrong when an
        image holds several wounds - the box spans them and SAM picks one.
    per_wound=True:  one box per GT connected component, scored against that
        component. This is what a user does (one box per wound) and is the
        number to quote.
    """
    img_dir, lbl_dir = root / split / "images", root / split / "labels"
    files = sorted(img_dir.glob("*.png"))
    if n:
        files = files[:n]
    rng = np.random.default_rng(seed)
    seg = Segmenter(ckpt)
    out.mkdir(parents=True, exist_ok=True)
    (out / "overlays").mkdir(exist_ok=True)

    rows, t_total, n_skipped = [], 0.0, 0
    for k, f in enumerate(files):
        img = cv2.imread(str(f))
        gt = cv2.imread(str(lbl_dir / f.name), 0) > 127
        if gt.sum() == 0:
            n_skipped += 1
            continue
        t0 = time.time()
        seg.set_image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))   # encode once per image
        t_enc = time.time() - t0
        comps = list(gt_components(gt, per_wound))
        union_post = np.zeros_like(gt)
        first_box = None
        for ci, comp in enumerate(comps):
            box = box_from_mask(comp, jitter, rng)
            first_box = first_box if first_box is not None else box
            t1 = time.time()
            raw, score = seg.predict_box(box, post=False)
            dt = (time.time() - t1) + (t_enc if ci == 0 else 0.0)
            t_total += dt
            post = postprocess(raw)
            union_post |= post
            d_raw, i_raw = dice_iou(raw, comp)
            d_post, i_post = dice_iou(post, comp)
            tight = box_from_mask(comp, 0.0, rng)          # "perfect user" upper bound
            raw_t, _ = seg.predict_box(tight, post=False)
            d_tight, _ = dice_iou(postprocess(raw_t), comp)
            rows.append(dict(image=f.name, component=ci, n_components=len(comps),
                             gt_px=int(comp.sum()), sam_score=round(score, 3),
                             dice_raw=round(d_raw, 4), iou_raw=round(i_raw, 4),
                             dice_post=round(d_post, 4), iou_post=round(i_post, 4),
                             dice_tightbox=round(d_tight, 4), secs=round(dt, 2)))
        if k % 25 == 0:
            print(f"  [{k+1}/{len(files)}] {f.name} comps {len(comps)} dice {rows[-1]['dice_post']:.3f}",
                  flush=True)
        cv2.imwrite(str(out / "overlays" / f.name), overlay(img, gt, union_post, first_box))

    with open(out / "fuseg_per_image.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    def stats(key):
        v = np.array([r[key] for r in rows])
        return dict(mean=round(float(v.mean()), 4), median=round(float(np.median(v)), 4),
                    std=round(float(v.std()), 4), p10=round(float(np.percentile(v, 10)), 4),
                    min=round(float(v.min()), 4))

    summary = dict(
        dataset="FUSeg", split=split, per_wound=per_wound,
        n=len(rows), n_images=len({r["image"] for r in rows}), n_skipped_empty_gt=n_skipped,
        n_multi_wound_images=len({r["image"] for r in rows if r["n_components"] > 1}),
        box_jitter=jitter, checkpoint=str(ckpt or "weights/mobile_sam.pt"),
        model="MobileSAM vit_t (box prompt, " + ("fine-tuned decoder)" if ckpt else "zero-shot)"),
        dice_raw=stats("dice_raw"), dice_post=stats("dice_post"),
        iou_post=stats("iou_post"), dice_tightbox=stats("dice_tightbox"),
        frac_dice_post_ge_0_80=round(float(np.mean([r["dice_post"] >= 0.8 for r in rows])), 3),
        frac_dice_post_lt_0_50=round(float(np.mean([r["dice_post"] < 0.5 for r in rows])), 3),
        secs_per_image_cpu=round(t_total / len(rows), 2),
    )
    # keep the three most instructive overlays easy to find
    srt = sorted(rows, key=lambda r: r["dice_post"])
    summary["examples"] = dict(worst=srt[0]["image"], median=srt[len(srt) // 2]["image"],
                               best=srt[-1]["image"])
    json.dump(summary, open(out / "fuseg_summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))
    return summary


# -------------------------------------------------------------- synthetic ---
def eval_synth(n: int, out: Path, seed: int = 0, ckpt: str | None = None,
               tilts=(0, 15, 30, 45), marker_mm: float = 20.0):
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixtures").mkdir(exist_ok=True)
    seg = Segmenter(ckpt)
    rng = np.random.default_rng(seed)
    rows = []
    per_tilt = max(1, n // len(tilts))
    k = 0
    for tilt in tilts:
        for _ in range(per_tilt):
            fx = make_fixture(seed=seed * 1000 + k, marker_mm=marker_mm, tilt_deg=tilt)
            calib = calibrate(fx.photo_bgr, marker_mm)
            row = dict(idx=k, tilt_deg=tilt, gt_area_mm2=round(fx.gt_area_mm2, 1),
                       gt_length_mm=round(fx.gt_length_mm, 1), gt_width_mm=round(fx.gt_width_mm, 1),
                       marker_found=calib is not None)
            if calib is not None:
                # (a) calibration + measurement only: perfect mask
                m_gt = measure(fx.gt_mask, calib)
                row.update(est_tilt_deg=round(calib.tilt_deg, 1),
                           calib_area_err_pct=round(100 * (m_gt["area_mm2"] - fx.gt_area_mm2) / fx.gt_area_mm2, 2),
                           naive_area_err_pct=round(100 * (m_gt["naive_area_mm2"] - fx.gt_area_mm2) / fx.gt_area_mm2, 2),
                           calib_length_err_pct=round(100 * (m_gt["length_mm"] - fx.gt_length_mm) / fx.gt_length_mm, 2),
                           calib_width_err_pct=round(100 * (m_gt["width_mm"] - fx.gt_width_mm) / fx.gt_width_mm, 2))
                # (b) end to end: SAM finds the mask from a loose box
                box = box_from_mask(fx.gt_mask, 0.15, rng)
                pred, score = seg.segment(cv2.cvtColor(fx.photo_bgr, cv2.COLOR_BGR2RGB), box)
                d, _ = dice_iou(pred, fx.gt_mask)
                m_e2e = measure(pred, calib)
                row.update(dice=round(d, 4), sam_score=round(score, 3),
                           e2e_area_err_pct=round(100 * (m_e2e.get("area_mm2", 0) - fx.gt_area_mm2) / fx.gt_area_mm2, 2))
                if k < 8:
                    cv2.imwrite(str(out / "fixtures" / f"fx_{k:02d}_tilt{tilt}.png"),
                                overlay(fx.photo_bgr, fx.gt_mask, pred, box))
            rows.append(row)
            k += 1

    with open(out / "synth_per_fixture.csv", "w", newline="") as fh:
        keys = sorted({kk for r in rows for kk in r}, key=lambda s: (s != "idx", s))
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)

    found = [r for r in rows if r["marker_found"]]
    abs_ = lambda key, rs: [abs(r[key]) for r in rs if key in r]  # noqa: E731

    def agg(key, rs):
        v = np.array(abs_(key, rs))
        return dict(mean_abs_pct=round(float(v.mean()), 2), p95_abs_pct=round(float(np.percentile(v, 95)), 2)) if len(v) else None

    summary = dict(
        n=len(rows), marker_detect_rate=round(len(found) / len(rows), 3), marker_mm=marker_mm,
        calibration_only=dict(area=agg("calib_area_err_pct", found),
                              length=agg("calib_length_err_pct", found),
                              width=agg("calib_width_err_pct", found)),
        naive_scale_area=agg("naive_area_err_pct", found),
        end_to_end=dict(area=agg("e2e_area_err_pct", found),
                        dice=round(float(np.mean([r["dice"] for r in found])), 4)),
        by_tilt={str(t): dict(
            calib_area=agg("calib_area_err_pct", [r for r in found if r["tilt_deg"] == t]),
            naive_area=agg("naive_area_err_pct", [r for r in found if r["tilt_deg"] == t]),
            e2e_area=agg("e2e_area_err_pct", [r for r in found if r["tilt_deg"] == t]),
            dice=round(float(np.mean([r["dice"] for r in found if r["tilt_deg"] == t])), 4),
        ) for t in tilts},
    )
    json.dump(summary, open(out / "synth_summary.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wound_proto.evaluate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("fuseg")
    a.add_argument("--root", required=True, help="FUSeg 'Foot Ulcer Segmentation Challenge' dir")
    a.add_argument("--split", default="validation")
    a.add_argument("--n", type=int, default=None)
    a.add_argument("--jitter", type=float, default=0.15, help="box dilation fraction per side")
    a.add_argument("--out", default="results/fuseg")
    a.add_argument("--ckpt", default=None)
    a.add_argument("--per-wound", action="store_true",
                   help="one box per GT connected component (what a user does); score per wound")
    b = sub.add_parser("synth")
    b.add_argument("--n", type=int, default=40)
    b.add_argument("--out", default="results/synth")
    b.add_argument("--ckpt", default=None)
    b.add_argument("--marker-mm", type=float, default=20.0)
    args = ap.parse_args(argv)
    if args.cmd == "fuseg":
        eval_fuseg(Path(args.root), args.split, args.n, args.jitter, Path(args.out),
                   ckpt=args.ckpt, per_wound=args.per_wound)
    else:
        eval_synth(args.n, Path(args.out), ckpt=args.ckpt, marker_mm=args.marker_mm)


if __name__ == "__main__":
    sys.exit(main())
