# wound-proto — Phase 0 wound-measurement prototype

Photo + printed marker + a loose box around the wound → **area, perimeter, length, width in millimetres.**

```
python -m wound_proto photo.jpg --box 442,338,777,583 --marker-mm 20 \
    --out result.json --overlay overlay.png
```

<p><img src="results/demo/overlay.png" width="420" alt="fixture at 30 degree tilt: marker corners in magenta, prompt box in yellow, MobileSAM contour in blue"></p>

This is Phase 0 from the build plan (prove the pipeline, get two honest numbers) plus the
Phase 1 segmenter fine-tune, which lifts per-wound Dice on FUSeg from 0.86 to 0.90 with 3.5 M
trained parameters and 11 CPU-minutes of training after a one-off 28-minute embedding pass.
It is **not** a medical device and must not be
used to make clinical decisions.

## What it does

| Stage | How | Why this way |
|---|---|---|
| Scale | Detect an **ArUco marker** of known side length (OpenCV, sub-pixel corners) and build a **homography** from the image plane to a metric plane | A single "pixels per mm" number is wrong the moment the camera tilts; the homography corrects foreshortening. See the table below for how wrong. |
| Boundary | **MobileSAM** (10 M params, CPU ≈ 1–2 s/image) prompted with the user's box, then largest component + hole fill | The size class you would ship on a phone. Box prompts are what a user can give. |
| Measure | Warp the mask into the metric plane, count area, trace the contour for perimeter, convex hull for max-Feret length and perpendicular width | Clinical length × width convention; everything measured *after* rectification. |
| Honesty | If no marker is found, results are pixel-only and `calibrated: false` | It never guesses a scale. |

Two error sources are kept **separable**: calibration + measurement is tested on
synthetic fixtures with exact ground truth; segmentation is tested on FUSeg against
clinician masks. The end-to-end synthetic run stacks them, which is what a user gets.

## Setup

```bash
bash scripts/setup.sh          # clones MobileSAM (+39 MB checkpoint) and the FUSeg dataset
python -m wound_proto.evaluate synth --n 40
python -m wound_proto.evaluate fuseg --root "vendor/wound-segmentation/data/Foot Ulcer Segmentation Challenge"
```

Requires Python ≥ 3.10, `opencv-contrib-python-headless` ≥ 4.8 (works on 5.x), `torch`, `timm`.
No GPU needed.

## Results

### Calibration + measurement — synthetic fixtures, exact ground truth

Perfect mask supplied; only the marker → homography → measurement path is under test.
`naive` is what you get from `pixels × (mm/px)` with no perspective correction.

| Camera tilt | Area error, homography | Area error, naive scale | Length err | Width err |
|---|---|---|---|---|
| 0° | 0.39% | 0.27% | −0.06% | −0.17% |
| 15° | 0.72% | 4.63% | 0.70% | 0.32% |
| 30° | **−0.23%** | **16.15%** | −0.17% | 0.26% |
| 45° | **0.70%** | **38.99%** | 0.70% | 0.42% |

The homography stays under 1% at every tilt. Naive scaling is off by a sixth at
30° and by more than a third at 45° — and 30° is an ordinary handheld angle. This
single table is the case for using a marker-derived homography rather than a ruler.

<!-- SYNTH_SUMMARY -->
**40 fixtures, 20 mm marker, marker detected in 100%.**
Absolute error, mean / p95:

| Tilt | Area, homography (perfect mask) | Area, naive scale | Dice, MobileSAM | Area, end-to-end |
|---|---|---|---|---|
| 0° | 0.36% / 0.62% | 0.37% / 0.48% | 0.987 | 1.96% / 8.57% |
| 15° | 0.43% / 0.79% | 3.67% / 8.71% | 0.978 | 3.59% / 15.59% |
| 30° | 0.64% / 1.14% | 13.98% / 25.16% | 0.994 | 0.84% / 2.51% |
| 45° | 0.72% / 1.24% | 34.70% / 51.19% | 0.993 | 1.18% / 4.42% |
| **all** | **0.54% / 1.14%** | 13.18% / 45.92% | **0.988** | **1.89% / 7.06%** |

Length error 0.48% mean, width 0.61% mean (perfect mask).
The end-to-end column is what a user gets: segmentation error stacked on calibration error.
<!-- /SYNTH_SUMMARY -->

### Segmentation — FUSeg validation split, zero-shot MobileSAM

Box prompt = ground-truth bounding box dilated by up to 15% per side with random
asymmetry, to simulate a user drawing loosely. No fine-tuning of any kind.

**Per wound — one box per ground-truth component.** This is what a user does and is
the number to quote.

<!-- FUSEG_PERWOUND -->
**253 wounds across 195 images** (5 images with empty masks skipped; 38 images hold more than one wound), 0.8 s/image on CPU.

| | mean | median | std | p10 | min |
|---|---|---|---|---|---|
| Dice, raw SAM mask | 0.859 | 0.893 | 0.110 | 0.710 | 0.354 |
| **Dice, after post-processing** | **0.860** | **0.894** | 0.109 | 0.711 | 0.355 |
| IoU, after post-processing | 0.768 | 0.808 | 0.153 | 0.552 | 0.216 |
| Dice, tight GT box (perfect user) | 0.891 | 0.920 | 0.089 | 0.779 | 0.419 |

75% of wounds reach Dice ≥ 0.80; 0.8% fall below 0.50.
For reference, the published *supervised* FUSegNet reaches Dice 0.859 on this benchmark. Zero-shot MobileSAM with a loose box per wound matches it; the tight-box row shows how much a careful user adds.

Overlays (green = clinician mask, blue = prediction, yellow = prompt box) in `results/fuseg-perwound/overlays/`;
worst `0245.png`, median `0946.png`, best `0796.png`.
<!-- /FUSEG_PERWOUND -->

**Per image — one box around the entire mask.** Kept because it is the naive protocol
and it shows a real design constraint (below).

<!-- FUSEG_SUMMARY -->
**195 images** (5 with empty masks skipped), 1.8 s/image on CPU.

| | mean | median | std | p10 | min |
|---|---|---|---|---|---|
| Dice, raw SAM mask | 0.784 | 0.875 | 0.227 | 0.391 | 0.001 |
| **Dice, after post-processing** | **0.781** | **0.871** | 0.233 | 0.391 | 0.001 |
| IoU, after post-processing | 0.689 | 0.771 | 0.254 | 0.243 | 0.000 |
| Dice, tight GT box (perfect user) | 0.833 | 0.919 | 0.205 | 0.530 | 0.000 |

67% of images reach Dice ≥ 0.80; 13.3% fall below 0.50.
This protocol is superseded by the per-wound one above; see *Reading the failures*.

Overlays (green = clinician mask, blue = prediction, yellow = prompt box) in `results/fuseg/overlays/`;
worst `0548.png`, median `0948.png`, best `0796.png`.
<!-- /FUSEG_SUMMARY -->

**Reading the failures.** The worst per-image case (`0548.png`) holds two wounds on two
legs. A single box spanning both is not a wound prompt, so SAM segmented a leg edge and
post-processing then kept the wrong blob. That is a protocol artefact, but it encodes a
product rule: **the app must take one box per wound and never infer a box from a region.**
It also explains why post-processing does not lift the per-image score — "largest
component" deletes legitimate secondary wounds. The remaining low scores are genuine:
faint boundaries under peri-wound erythema, wet wound beds that read as skin, and small
ulcers where a 15% loose box is proportionally huge. The per-wound worst case (`0245.png`,
Dice 0.35) is the last kind: a ~20 × 40 px ulcer beside the little toe on dark skin, where
prediction and clinician mask nearly coincide but a few boundary pixels are most of the
area. Small-wound sensitivity and a Fitzpatrick-stratified evaluation are Phase 1's
first two targets.

Copies of the four instructive overlays are in `results/demo/fuseg-examples/`.

### End-to-end demo

`results/demo/`: a 30°-tilted fixture, ground truth **551.8 mm²**, L 32.4 × W 23.2 mm.

```
area_cm2                    5.512       (551.2 mm²  →  −0.1%)
length_mm                   32.56
width_mm                    23.25
naive_area_mm2              595.42      (what naive scaling would have reported: +7.9%)
perspective_correction_pct  −8.03
sam_score                   0.987
```

## Phase 1 — fine-tuning the segmenter

The plan said "fine-tune a real segmenter (SegFormer-B2 or nnU-Net)". This environment
cannot reach any pretrained backbone, and training one from scratch on 810 images loses
to a distilled SAM encoder, so Phase 1 follows the MedSAM recipe instead, scaled to a CPU:

| | |
|---|---|
| Frozen | MobileSAM image encoder (6.1 M) and prompt encoder — their outputs are precomputed once by `scripts/cache_embeddings.py` (fp16, 2 MB per image) |
| Trained | the mask decoder's single-mask path: 3.5 M parameters (the IoU head and the three unused multi-mask hypernetworks stay as shipped) |
| Data | FUSeg train, 810 images + horizontal flips = 1,620 embeddings; validation 200 images for model selection only |
| Prompt | ground-truth box dilated per side by a random amount **from tight to 20 %** (the evaluation draws 4.5–15 %), so the decoder sees both a careful user and a sloppy one |
| Selection | best epoch by the mean of two validation scores: loose boxes (the evaluation protocol) and exact boxes (the "perfect user"), so neither can regress unnoticed |
| Loss | BCE + soft Dice on the 512 × 512 logits, AdamW 1e-4 / wd 0.01, cosine schedule over 10 epochs, grad-clip 1.0, batch 8; one wound (connected component) per sample |
| Output | a full MobileSAM state dict, so `Segmenter(ckpt)`, the CLI and `evaluate.py --ckpt` load it unchanged |

```bash
python scripts/cache_embeddings.py                       # ~1 s/image on 4 cores, once
python -m wound_proto.finetune --epochs 10 --out weights/mobile_sam_fuseg.pt   # ~40 min on 4 cores
python -m wound_proto.evaluate fuseg --per-wound --ckpt weights/mobile_sam_fuseg.pt \
    --root "vendor/wound-segmentation/data/Foot Ulcer Segmentation Challenge" --out results/fuseg-perwound-ft
```

<!-- FINETUNE -->
**10 epochs, 36 min on 4 CPU cores, best epoch 3.**
During training, per-wound validation Dice with loose boxes went 0.861 (zero-shot) → **0.902** and with tight boxes 0.892 → **0.882**.
The table is the independent evaluation of the saved checkpoint through the full pipeline.

| FUSeg validation, per wound (253 wounds) | zero-shot mean | fine-tuned mean | Δ | zero-shot median | fine-tuned median | zs p10 | ft p10 | zs min | ft min |
|---|---|---|---|---|---|---|---|---|---|
| Dice, raw SAM mask | 0.859 | 0.901 | +0.042 | 0.893 | 0.931 | 0.710 | 0.807 | 0.354 | 0.434 |
| **Dice, after post-processing** | 0.860 | 0.901 | +0.041 | 0.894 | 0.931 | 0.711 | 0.802 | 0.355 | 0.404 |
| IoU, after post-processing | 0.768 | 0.829 | +0.061 | 0.808 | 0.871 | 0.552 | 0.669 | 0.216 | 0.253 |
| Dice, tight GT box (perfect user) | 0.891 | 0.880 | -0.011 | 0.920 | 0.907 | 0.779 | 0.753 | 0.419 | 0.400 |

Wounds at Dice ≥ 0.80: 75% → **90%**; below 0.50: 0.8% → 0.4%.
Overlays in `results/fuseg-perwound-ft/overlays/`; worst `0974.png`, median `0405.png`, best `0796.png`.
<!-- /FINETUNE -->

**Reading it.** The gain is where a product needs it. Paired per wound, 62 % of the 253
wounds improved by more than 0.01 Dice and 8 % got worse; wounds under 2,000 px, the ones
Phase 0 flagged as the weak spot, went from 0.828 to 0.874, larger ones from 0.912 to 0.945.
The p10 moved more than the mean (0.711 → 0.802), which is what you want from a
segmenter: fewer bad days, not a better best day. The synthetic fixtures are a regression
check, not a target, and did not regress: end-to-end area error 1.89 % / 7.06 % (mean / p95)
zero-shot versus 1.86 % / 5.46 % fine-tuned.

**The trade-off, and why the first run was thrown away.** The v1 fine-tune (kept in
`results/*-v1/`) reached 0.906 on loose boxes but dropped the tight-box "perfect user" score
from 0.891 to 0.842, with one total miss, because training boxes were never tighter than 6 %
per side and the decoder learned to expect a margin. v2 trains on boxes from exactly tight to
20 % loose and selects the epoch on the mean of both validation scores. The tight-box score is
still 0.011 below zero-shot, almost all of it on small wounds (0.863 → 0.846; large wounds
0.937 → 0.935). The remaining worst case (`0974.png`, a 74-pixel wound, Dice 0.40 against
0.89 zero-shot) is the same lesson: at that size a few boundary pixels are most of the area,
and the fine-tuned decoder is not yet better than SAM's edge prior. The next experiment is
not more epochs, the curve was flat after epoch 3, it is the share of tight boxes in
training, or routing very small wounds to the zero-shot decoder.

**What it cost.** 3.5 M trainable parameters, one 28-minute encoder pass to cache
embeddings, then 3.5 minutes per epoch on four CPU cores; the selected checkpoint is from
epoch 3. Weights are not committed (40 MB); the two commands above reproduce them.

**Reading the numbers.** The independent evaluation confirms the training curve: with the
loose boxes a real user draws, per-wound Dice goes from 0.860 to 0.901, the median from 0.894
to 0.931, and the tenth percentile from 0.711 to 0.802. Paired per wound, 62 % improve by more
than 0.01 and 8 % get worse. The gain is largest where Phase 0 was weakest: wounds under 2,000
px rise from 0.828 to 0.874, larger ones from 0.912 to 0.945. The synthetic pipeline is
unchanged (Dice 0.988 → 0.989, end-to-end area error 1.89 % → 1.86 % mean), so the
fine-tune did not disturb the geometry.

The one cost is the tight-box row. The first run (`results/*-v1/`) trained only on boxes
dilated by at least 6 % and dropped the "perfect user" Dice from 0.891 to 0.842; training from
tight to 20 % loose (this run) recovers most of it, 0.880, with the remaining −0.011 carried
entirely by small wounds (0.863 → 0.846; large wounds 0.937 → 0.935). Zero-shot SAM is already
excellent when the box is exact, so a decoder tuned to FUSeg's annotation style trades a little
of that for robustness to sloppy boxes. The worst v2 case (`0974.png`, a 74 px wound, Dice 0.40
where zero-shot had 0.89) is that trade in one image. The share of tight boxes in training,
or a rule that trusts the box more when it is small, is the first knob to turn in Phase 2.

Cost of the whole thing: 3.5 M trained parameters, best epoch reached after 11 minutes on four
CPU cores once embeddings are cached, and no new dependency. Weights are not committed; the
run reproduces from the three commands above.

## Limitations — read before extrapolating

- **Coplanarity.** The homography assumes the wound lies in the marker's plane. On curved
  anatomy (heel, calf, sacrum) that is false, and the error grows with curvature. This is
  the problem depth sensing (LiDAR / ToF) exists for; out of scope here.
- **Synthetic fixtures are generous.** High-contrast wound on plain skin, ideal marker print.
  Real photos have glare, moist wound beds, peri-wound erythema, dressings and hair. The
  FUSeg number is the realistic one for boundaries; the synthetic number isolates the
  geometry.
- **FUSeg is diabetic foot ulcers only.** Pressure injuries, venous leg ulcers, burns and
  surgical wounds are not represented, and public data for them barely exists. Expect the
  zero-shot Dice to drop on those until you have your own labelled images.
- **Skin tone.** The synthetic generator samples five base tones, but FUSeg skews light.
  Any product claim of "works across skin tones" needs a Fitzpatrick-stratified evaluation
  on real images, which this prototype cannot provide.
- **The tilt estimate** reported in `calibration.tilt_deg` is a crude foreshortening ratio for
  display only. Correction comes from the homography, not from that number.
- **Not a medical device.** An app that outputs wound area for clinical use is Software as a
  Medical Device (EU MDR, FDA, CDSCO). Intended use has to be decided before the next line
  of product code.

## What comes next (Phase 2)

1. **Data before models.** The decoder fine-tune above took FUSeg from 0.86 to 0.90 in one
   epoch and plateaued by epoch 13; the ceiling is now the data, not the optimiser. Add
   DFUC2022 and AZH, and start collecting your own images from day one — public data will
   not cover your wound types, skin tones or lighting.
2. Replace the ArUco square with a purpose-designed sticker (colour patch for white balance,
   known size, patient-safe adhesive) — same maths, better detection under glare.
3. Report **both** errors on every result: mask Dice against a clinician, and area error
   against a ruler. Calibration error compounds on segmentation error.
4. Tissue classification (granulation / slough / necrosis / epithelial) is the long pole
   and has no public data. Build the annotation pipeline first: the fine-tuned decoder
   pre-segments, wound-care nurses correct. For the classifier itself, a linear probe on
   MedSigLIP embeddings (Google's 400 M medical image encoder, trained with dermatology data)
   is the cheapest first experiment; MedGemma belongs to the report-writing layer above it,
   not to measurement.

## Testing

Four layers, cheapest first. Each one isolates a different failure.

| Layer | Command | What it proves | Pass criterion |
|---|---|---|---|
| Unit | `pip install -e ".[test]"` then `pytest -q -m "not model"` (3 s) | Marker detection, homography, measurement and post-processing on fixtures with exact ground truth; no weights needed | All green. Area within 2.5 % at 0°, 30°, 45°; no marker → `calibrated: false`, never a guessed scale |
| Unit + model | `pytest -q` (~25 s) | Batched Phase 1 decoder equals the stock decoder; MobileSAM segments a fixture; the CLI runs end to end | All green. Dice > 0.90 on a fixture, area within 10 % after segmentation |
| Synthetic | `python -m wound_proto.evaluate synth --n 40` | Calibration + measurement statistics; homography vs naive scale at every tilt | Homography mean error ≈ 0.5 %, p95 ≈ 1 %; naive error grows with tilt |
| Real data | `python -m wound_proto.evaluate fuseg --per-wound --root <FUSeg dir>` (~3 min) | Segmentation against clinician masks | Per-wound Dice ≥ 0.86 zero-shot; a fine-tuned `--ckpt` must beat it, not just match it |

Then the test that none of the above replaces: **print a 20 mm ArUco marker** (id 0 from
`DICT_4X4_50`, e.g. `cv2.aruco.generateImageMarker`), place it beside an object of known
size such as a coin or a drawn shape, photograph it square-on and at ~30° with a phone, and
run the CLI on both. The two areas should agree with each other and with the ruler to within
a few percent, and `perspective_correction_pct` should be near zero square-on and clearly
non-zero when tilted. That is the acceptance test a clinician will run whether you do or not.

## Layout

```
wound_proto/
  calibrate.py   ArUco detection → metric homography; rectify_mask()
  segment.py     MobileSAM box prompt + postprocess()
  measure.py     area / perimeter / length / width, pixel and metric
  synth.py       fixture generator with exact ground truth + perspective warp
  evaluate.py    `fuseg` and `synth` sub-commands
  finetune.py    Phase 1: train the MobileSAM mask decoder on cached FUSeg embeddings
  cli.py         analyse one photo
scripts/setup.sh            fetch MobileSAM + FUSeg (not committed)
scripts/cache_embeddings.py run the frozen image encoder once per FUSeg image -> cache/
scripts/fill_readme.py      render results/*.json into this file
results/         summaries and training log committed; overlays, fixtures, cache and weights are not
```
