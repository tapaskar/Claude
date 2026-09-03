"""Synthetic fixtures with exact ground truth.

We cannot photograph a wound in this environment, and even where you can, you
cannot know its true area to the square millimetre. A synthetic scene can: the
wound and the marker are drawn in a metric plane at a known mm/px, so area,
perimeter, length and width are exact by construction. The scene is then
perspective-warped to fake a tilted phone camera. Ground truth is invariant to
that warp - which is precisely what the calibration has to undo.

This isolates two errors the app will have in production:
  calibration + measurement   -> feed the pipeline the warped GT mask
  segmentation                -> feed it the warped photo and let SAM find the mask
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .calibrate import ARUCO_DICT
from .measure import _length_width, _largest_contour

SCENE_PX_PER_MM = 8.0          # metric plane resolution for drawing
SCENE_MM = (120.0, 120.0)      # scene extent, mm


@dataclass
class Fixture:
    photo_bgr: np.ndarray
    gt_mask: np.ndarray           # bool, in photo space
    gt_area_mm2: float
    gt_perimeter_mm: float
    gt_length_mm: float
    gt_width_mm: float
    marker_mm: float
    tilt_deg: float
    seed: int


def _wound_polygon(rng, cx, cy, r_mm, n=180):
    """Perturbed ellipse: radius modulated by a few low-order harmonics."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    a = r_mm * rng.uniform(0.8, 1.2)
    b = r_mm * rng.uniform(0.6, 1.0)
    mod = 1.0 + sum(rng.uniform(0.03, 0.12) * np.sin(k * t + rng.uniform(0, 2 * np.pi))
                    for k in (2, 3, 5))
    x = cx + a * mod * np.cos(t)
    y = cy + b * mod * np.sin(t)
    return np.stack([x, y], axis=1)


def _skin(rng, h, w):
    base = np.array(rng.choice([[205, 170, 145], [180, 140, 115], [140, 100, 80],
                                [95, 65, 50], [225, 195, 175]]), dtype=np.float32)
    img = np.ones((h, w, 3), np.float32) * base[::-1]  # to BGR
    noise = rng.normal(0, 6, (h, w, 1)).astype(np.float32)
    img += noise
    # soft vignette / uneven lighting
    yy, xx = np.mgrid[0:h, 0:w]
    grad = ((xx / w) * rng.uniform(-25, 25) + (yy / h) * rng.uniform(-25, 25)).astype(np.float32)
    img += grad[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def make_fixture(seed: int = 0, marker_mm: float = 20.0, tilt_deg: float = 0.0,
                 wound_r_mm: float | None = None, out_size: int = 1024) -> Fixture:
    rng = np.random.default_rng(seed)
    W = int(SCENE_MM[0] * SCENE_PX_PER_MM)
    H = int(SCENE_MM[1] * SCENE_PX_PER_MM)
    scene = _skin(rng, H, W)

    # ---- wound, drawn in the metric plane -----------------------------------
    r_mm = wound_r_mm if wound_r_mm is not None else rng.uniform(8, 22)
    cx_mm, cy_mm = rng.uniform(45, 75), rng.uniform(50, 80)
    poly_mm = _wound_polygon(rng, cx_mm, cy_mm, r_mm)
    poly_px = np.round(poly_mm * SCENE_PX_PER_MM).astype(np.int32)
    gt_scene = np.zeros((H, W), np.uint8)
    cv2.fillPoly(gt_scene, [poly_px], 1)

    # wound bed: dark red core, pinker rim, a little texture
    wound_col = np.array(rng.choice([[40, 30, 150], [50, 40, 170], [35, 25, 120]]), np.float32)
    rim_col = wound_col * 0.6 + np.array([120, 120, 220], np.float32) * 0.4
    dist = cv2.distanceTransform(gt_scene, cv2.DIST_L2, 5)
    rim = np.clip(dist / (2.5 * SCENE_PX_PER_MM), 0, 1)[..., None]
    tex = rng.normal(0, 10, (H, W, 1)).astype(np.float32)
    wound_img = rim * wound_col + (1 - rim) * rim_col + tex
    scene = scene.astype(np.float32)
    scene[gt_scene == 1] = wound_img[gt_scene == 1]
    scene = np.clip(scene, 0, 255).astype(np.uint8)

    # ---- marker, metric size, on a white sticker with a quiet zone ----------
    d = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    mid = int(rng.integers(0, 50))
    mpx = int(marker_mm * SCENE_PX_PER_MM)
    marker = cv2.aruco.generateImageMarker(d, mid, mpx)
    pad = int(0.35 * mpx)
    sticker = np.full((mpx + 2 * pad, mpx + 2 * pad), 255, np.uint8)
    sticker[pad:pad + mpx, pad:pad + mpx] = marker
    # place away from the wound, random corner-ish region
    sx = int(rng.uniform(8, 25) * SCENE_PX_PER_MM)
    sy = int(rng.uniform(8, 25) * SCENE_PX_PER_MM)
    scene[sy:sy + sticker.shape[0], sx:sx + sticker.shape[1]] = sticker[..., None]

    # ---- exact ground truth in the metric plane ------------------------------
    mm_per_px = 1.0 / SCENE_PX_PER_MM
    cnt = _largest_contour(gt_scene)
    gt_area = float(gt_scene.sum()) * mm_per_px ** 2
    gt_perim = float(cv2.arcLength(cnt, True)) * mm_per_px
    L, Wd, _, _ = _length_width(cnt)

    # ---- perspective warp: simulate a tilted camera --------------------------
    src = np.array([[0, 0], [W, 0], [W, H], [0, H]], np.float32)
    t = np.radians(tilt_deg)
    # foreshorten one edge pair; add a mild random keystone on the other axis
    k = 0.5 * (1 - np.cos(t))
    kx = rng.uniform(-0.08, 0.08) * (tilt_deg / 45.0)
    dst = np.array([[W * k + W * kx, 0], [W * (1 - k), 0],
                    [W, H], [0 - W * kx, H]], np.float32)
    dst -= dst.min(axis=0)
    dst *= out_size / dst.max(axis=0)
    Hm = cv2.getPerspectiveTransform(src, dst)
    photo = cv2.warpPerspective(scene, Hm, (out_size, out_size),
                                borderValue=(60, 60, 60))
    gt_photo = cv2.warpPerspective(gt_scene, Hm, (out_size, out_size), flags=cv2.INTER_NEAREST)
    # mild camera blur + JPEG-ish noise
    photo = cv2.GaussianBlur(photo, (0, 0), rng.uniform(0.6, 1.4))
    photo = np.clip(photo.astype(np.float32) + rng.normal(0, 3, photo.shape), 0, 255).astype(np.uint8)

    return Fixture(photo_bgr=photo, gt_mask=gt_photo.astype(bool),
                   gt_area_mm2=gt_area, gt_perimeter_mm=gt_perim,
                   gt_length_mm=L * mm_per_px, gt_width_mm=Wd * mm_per_px,
                   marker_mm=marker_mm, tilt_deg=tilt_deg, seed=seed)
