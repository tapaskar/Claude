"""Fast checks for the Phase 0/1 pipeline.

    pytest -q                  # everything (~30 s on CPU, needs weights/mobile_sam.pt)
    pytest -q -m "not model"   # geometry + measurement only, no weights, ~3 s

The synthetic fixtures carry exact ground truth, so the calibration tests are
strict; the model tests only guard against regressions, the real numbers live
in results/ and are produced by wound_proto.evaluate.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from wound_proto.calibrate import calibrate, detect_marker
from wound_proto.measure import measure
from wound_proto.segment import postprocess
from wound_proto.synth import make_fixture

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = ROOT / "weights" / "mobile_sam.pt"
model = pytest.mark.model


def dice(a, b):
    return 2 * np.logical_and(a, b).sum() / (a.sum() + b.sum() + 1e-9)


def loose_box(mask, frac=0.10):
    ys, xs = np.where(mask)
    w, h = xs.max() - xs.min(), ys.max() - ys.min()
    return [xs.min() - frac * w, ys.min() - frac * h, xs.max() + frac * w, ys.max() + frac * h]


# ----------------------------------------------------------- calibration ---

@pytest.mark.parametrize("tilt", [0.0, 30.0, 45.0])
def test_homography_recovers_area_with_perfect_mask(tilt):
    fx = make_fixture(seed=3, marker_mm=20.0, tilt_deg=tilt)
    calib = calibrate(fx.photo_bgr, 20.0)
    assert calib is not None, "marker not detected on a clean fixture"
    r = measure(fx.gt_mask, calib)
    assert r["calibrated"]
    err = abs(r["area_mm2"] - fx.gt_area_mm2) / fx.gt_area_mm2
    assert err < 0.025, f"area error {err:.1%} at {tilt} deg"
    assert abs(r["length_mm"] - fx.gt_length_mm) / fx.gt_length_mm < 0.03
    assert abs(r["width_mm"] - fx.gt_width_mm) / fx.gt_width_mm < 0.03


def test_naive_scale_is_wrong_when_tilted():
    fx = make_fixture(seed=3, marker_mm=20.0, tilt_deg=30.0)
    r = measure(fx.gt_mask, calibrate(fx.photo_bgr, 20.0))
    naive_err = abs(r["naive_area_mm2"] - fx.gt_area_mm2) / fx.gt_area_mm2
    homog_err = abs(r["area_mm2"] - fx.gt_area_mm2) / fx.gt_area_mm2
    assert naive_err > 0.05 and homog_err < naive_err


def test_no_marker_means_pixels_only():
    blank = np.full((480, 640, 3), 128, np.uint8)
    assert detect_marker(blank) is None
    assert calibrate(blank, 20.0) is None
    m = np.zeros((480, 640), bool); m[100:200, 100:250] = True
    r = measure(m, None)
    assert r["calibrated"] is False and r["area_px"] == 150 * 100
    assert "area_mm2" not in r


def test_empty_mask_is_reported_not_measured():
    r = measure(np.zeros((64, 64), bool), None)
    assert r.get("empty") and r["area_px"] == 0


# ------------------------------------------------------ post-processing ---

def test_postprocess_keeps_largest_component_and_fills_holes():
    m = np.zeros((256, 256), bool)
    m[50:150, 50:150] = True          # wound
    m[95:105, 95:105] = False         # hole in it
    m[200:206, 200:206] = True        # stray blob
    p = postprocess(m)
    assert p[100, 100], "hole not filled"
    assert not p[203, 203], "stray blob kept"
    assert p[50:150, 50:150].mean() > 0.97


# -------------------------------------------------------------- Phase 1 ---

def test_jitter_box_contains_gt_and_stays_in_frame():
    from wound_proto.finetune import _jitter_box
    m = np.zeros((512, 512), bool); m[5:60, 450:510] = True   # near the corner
    rng = np.random.default_rng(0)
    for _ in range(20):
        x0, y0, x1, y1 = _jitter_box(m, 0.2, rng)
        assert 0 <= x0 <= 450 and 0 <= y0 <= 5 and 509 <= x1 <= 511 and 59 <= y1 <= 511


# ---------------------------------------------------------- with model ---

@pytest.fixture(scope="module")
def sam():
    if not WEIGHTS.exists():
        pytest.skip("weights/mobile_sam.pt missing - run scripts/setup.sh")
    pytest.importorskip("mobile_sam")
    from mobile_sam import sam_model_registry
    return sam_model_registry["vit_t"](checkpoint=str(WEIGHTS)).eval()


@model
def test_batched_decoder_matches_stock_decoder(sam):
    import torch
    from wound_proto.finetune import decode_batched
    torch.manual_seed(0)
    emb = torch.randn(1, 256, 64, 64)
    with torch.no_grad():
        sp, de = sam.prompt_encoder(points=None, boxes=torch.tensor([[300., 200., 800., 600.]]), masks=None)
        ref, _ = sam.mask_decoder(image_embeddings=emb, image_pe=sam.prompt_encoder.get_dense_pe(),
                                  sparse_prompt_embeddings=sp, dense_prompt_embeddings=de,
                                  multimask_output=False)
        mine = decode_batched(sam.mask_decoder, emb, sam.prompt_encoder.get_dense_pe(), sp, de)
    assert float((ref - mine).abs().max()) < 1e-3


@model
def test_segmenter_on_fixture(sam):
    from wound_proto.segment import Segmenter
    fx = make_fixture(seed=7, tilt_deg=15.0)
    mask, score = Segmenter(WEIGHTS).segment(cv2.cvtColor(fx.photo_bgr, cv2.COLOR_BGR2RGB),
                                             loose_box(fx.gt_mask))
    assert dice(mask, fx.gt_mask) > 0.90 and score > 0.5


@model
def test_cli_end_to_end(sam, tmp_path):
    from wound_proto.cli import main
    import json
    fx = make_fixture(seed=11, tilt_deg=30.0)
    img = tmp_path / "fx.png"; cv2.imwrite(str(img), fx.photo_bgr)
    box = ",".join(f"{v:.0f}" for v in loose_box(fx.gt_mask))
    out = tmp_path / "r.json"
    assert main([str(img), "--box", box, "--marker-mm", "20", "--out", str(out),
                 "--overlay", str(tmp_path / "ov.png")]) == 0
    r = json.loads(out.read_text())
    assert r["marker_found"] and r["calibrated"]
    assert abs(r["area_mm2"] - fx.gt_area_mm2) / fx.gt_area_mm2 < 0.10
    assert (tmp_path / "ov.png").exists()
