#!/usr/bin/env python3
"""Render results/*/summary.json into the README placeholders.

Run after both evaluations:  python scripts/fill_readme.py
Idempotent: re-running replaces the previously rendered blocks.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"


def synth_block(s: dict) -> str:
    c, e2e = s["calibration_only"], s["end_to_end"]
    rows = "\n".join(
        f"| {t}° | {v['calib_area']['mean_abs_pct']:.2f}% / {v['calib_area']['p95_abs_pct']:.2f}% "
        f"| {v['naive_area']['mean_abs_pct']:.2f}% / {v['naive_area']['p95_abs_pct']:.2f}% "
        f"| {v['dice']:.3f} | {v['e2e_area']['mean_abs_pct']:.2f}% / {v['e2e_area']['p95_abs_pct']:.2f}% |"
        for t, v in s["by_tilt"].items())
    return f"""**{s['n']} fixtures, {s['marker_mm']:.0f} mm marker, marker detected in {s['marker_detect_rate']*100:.0f}%.**
Absolute error, mean / p95:

| Tilt | Area, homography (perfect mask) | Area, naive scale | Dice, MobileSAM | Area, end-to-end |
|---|---|---|---|---|
{rows}
| **all** | **{c['area']['mean_abs_pct']:.2f}% / {c['area']['p95_abs_pct']:.2f}%** | {s['naive_scale_area']['mean_abs_pct']:.2f}% / {s['naive_scale_area']['p95_abs_pct']:.2f}% | **{e2e['dice']:.3f}** | **{e2e['area']['mean_abs_pct']:.2f}% / {e2e['area']['p95_abs_pct']:.2f}%** |

Length error {c['length']['mean_abs_pct']:.2f}% mean, width {c['width']['mean_abs_pct']:.2f}% mean (perfect mask).
The end-to-end column is what a user gets: segmentation error stacked on calibration error."""


def fuseg_block(s: dict) -> str:
    d, dr, dt, i = s["dice_post"], s["dice_raw"], s["dice_tightbox"], s["iou_post"]
    ex = s["examples"]
    unit = "wounds" if s.get("per_wound") else "images"
    n_img = s.get("n_images", s["n"])
    skipped = s.get("n_skipped_empty_gt", 0)
    multi = s.get("n_multi_wound_images", 0)
    head = (f"**{s['n']} {unit} across {n_img} images** ({skipped} images with empty masks skipped; "
            f"{multi} images hold more than one wound), {s['secs_per_image_cpu']:.1f} s/image on CPU."
            if s.get("per_wound") else
            f"**{s['n']} images** ({skipped} with empty masks skipped), {s['secs_per_image_cpu']:.1f} s/image on CPU.")
    return f"""{head}

| | mean | median | std | p10 | min |
|---|---|---|---|---|---|
| Dice, raw SAM mask | {dr['mean']:.3f} | {dr['median']:.3f} | {dr['std']:.3f} | {dr['p10']:.3f} | {dr['min']:.3f} |
| **Dice, after post-processing** | **{d['mean']:.3f}** | **{d['median']:.3f}** | {d['std']:.3f} | {d['p10']:.3f} | {d['min']:.3f} |
| IoU, after post-processing | {i['mean']:.3f} | {i['median']:.3f} | {i['std']:.3f} | {i['p10']:.3f} | {i['min']:.3f} |
| Dice, tight GT box (perfect user) | {dt['mean']:.3f} | {dt['median']:.3f} | {dt['std']:.3f} | {dt['p10']:.3f} | {dt['min']:.3f} |

{s['frac_dice_post_ge_0_80']*100:.0f}% of {unit} reach Dice ≥ 0.80; {s['frac_dice_post_lt_0_50']*100:.1f}% fall below 0.50.
{"For reference, the published *supervised* FUSegNet reaches Dice 0.859 on this benchmark. Zero-shot MobileSAM with a loose box per wound matches it; the tight-box row shows how much a careful user adds." if s.get("per_wound") else "This protocol is superseded by the per-wound one above; see *Reading the failures*."}

Overlays (green = clinician mask, blue = prediction, yellow = prompt box) in `{s.get('out_dir', 'results/fuseg')}/overlays/`;
worst `{ex['worst']}`, median `{ex['median']}`, best `{ex['best']}`."""


def finetune_block(log: dict, zs: dict, ft: dict) -> str:
    """Phase 1: training curve summary + zero-shot vs fine-tuned per-wound table."""
    eps = [e for e in log["epochs"] if e["epoch"] > 0]
    secs = sum(e.get("secs", 0) for e in eps)
    row = lambda k, name: (f"| {name} | {zs[k]['mean']:.3f} | {ft[k]['mean']:.3f} | "  # noqa: E731
                           f"{ft[k]['mean'] - zs[k]['mean']:+.3f} | {zs[k]['median']:.3f} | {ft[k]['median']:.3f} "
                           f"| {zs[k]['p10']:.3f} | {ft[k]['p10']:.3f} | {zs[k]['min']:.3f} | {ft[k]['min']:.3f} |")
    tight = (f" and with tight boxes {log['baseline_val_dice_tight']:.3f} → **{log['best_val_dice_tight']:.3f}**"
             if "best_val_dice_tight" in log else "")
    return f"""**{log['args']['epochs']} epochs, {secs/60:.0f} min on 4 CPU cores, best epoch {log['best_epoch']}.**
During training, per-wound validation Dice with loose boxes went {log['baseline_val_dice']:.3f} (zero-shot) → **{log['best_val_dice']:.3f}**{tight}.
The table is the independent evaluation of the saved checkpoint through the full pipeline.

| FUSeg validation, per wound ({ft['n']} wounds) | zero-shot mean | fine-tuned mean | Δ | zero-shot median | fine-tuned median | zs p10 | ft p10 | zs min | ft min |
|---|---|---|---|---|---|---|---|---|---|
{row('dice_raw', 'Dice, raw SAM mask')}
{row('dice_post', '**Dice, after post-processing**')}
{row('iou_post', 'IoU, after post-processing')}
{row('dice_tightbox', 'Dice, tight GT box (perfect user)')}

Wounds at Dice ≥ 0.80: {zs['frac_dice_post_ge_0_80']*100:.0f}% → **{ft['frac_dice_post_ge_0_80']*100:.0f}%**; below 0.50: {zs['frac_dice_post_lt_0_50']*100:.1f}% → {ft['frac_dice_post_lt_0_50']*100:.1f}%.
Overlays in `{ft.get('out_dir', 'results/fuseg-perwound-ft')}/overlays/`; worst `{ft['examples']['worst']}`, median `{ft['examples']['median']}`, best `{ft['examples']['best']}`."""


def fill(text: str, marker: str, block: str) -> str:
    start, end = f"<!-- {marker} -->", f"<!-- /{marker} -->"
    rendered = f"{start}\n{block}\n{end}"
    if end in text:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: rendered, text, flags=re.S)
    return text.replace(start, rendered)


def main():
    text = README.read_text()
    synth = ROOT / "results/synth/synth_summary.json"
    fuseg = ROOT / "results/fuseg/fuseg_summary.json"
    if synth.exists():
        text = fill(text, "SYNTH_SUMMARY", synth_block(json.load(open(synth))))
        print("filled SYNTH_SUMMARY")
    if fuseg.exists():
        text = fill(text, "FUSEG_SUMMARY", fuseg_block(json.load(open(fuseg))))
        print("filled FUSEG_SUMMARY")
    perwound = ROOT / "results/fuseg-perwound/fuseg_summary.json"
    if perwound.exists():
        text = fill(text, "FUSEG_PERWOUND", fuseg_block(json.load(open(perwound))))
        print("filled FUSEG_PERWOUND")
    log = ROOT / "results/finetune/log.json"
    ft = ROOT / "results/fuseg-perwound-ft/fuseg_summary.json"
    if log.exists() and ft.exists() and perwound.exists():
        text = fill(text, "FINETUNE", finetune_block(json.load(open(log)), json.load(open(perwound)),
                                                     json.load(open(ft))))
        print("filled FINETUNE")
    README.write_text(text)


if __name__ == "__main__":
    main()
