"""Wound measurements from a binary mask, optionally in metric units.

With a Calibration the mask is warped into the metric plane first, so the
numbers below are perspective-corrected. Without one, only pixel measurements
are returned and `calibrated` is False - the app should never silently report
pixels as centimetres.

Length / width follow the clinical convention: length is the longest chord
across the wound (max Feret diameter); width is the greatest extent measured
perpendicular to that length axis.
"""
from __future__ import annotations

import cv2
import numpy as np

from .calibrate import Calibration, rectify_mask


def _largest_contour(mask_u8: np.ndarray):
    cnts, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    return max(cnts, key=cv2.contourArea)


def _length_width(contour) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Max Feret diameter and the perpendicular extent, from the convex hull."""
    hull = cv2.convexHull(contour).reshape(-1, 2).astype(np.float64)
    if len(hull) < 2:
        return 0.0, 0.0, hull[0], hull[0]
    # hull is small (tens of points): brute-force pairwise is fine
    d = np.linalg.norm(hull[:, None, :] - hull[None, :, :], axis=2)
    i, j = np.unravel_index(int(np.argmax(d)), d.shape)
    length = float(d[i, j])
    axis = hull[j] - hull[i]
    if length == 0:
        return 0.0, 0.0, hull[i], hull[j]
    u = axis / length
    v = np.array([-u[1], u[0]])
    proj = (hull - hull[i]) @ v
    width = float(proj.max() - proj.min())
    return length, width, hull[i], hull[j]


def _metrics_in_plane(mask_u8: np.ndarray, mm_per_px: float | None):
    cnt = _largest_contour(mask_u8)
    if cnt is None:
        return None
    area_px = float(mask_u8.sum())
    perim_px = float(cv2.arcLength(cnt, True))
    length_px, width_px, p0, p1 = _length_width(cnt)
    out = dict(area_px=area_px, perimeter_px=perim_px,
               length_px=length_px, width_px=width_px,
               length_axis_px=[p0.tolist(), p1.tolist()])
    if mm_per_px is not None:
        out.update(
            area_mm2=area_px * mm_per_px ** 2,
            area_cm2=area_px * mm_per_px ** 2 / 100.0,
            perimeter_mm=perim_px * mm_per_px,
            length_mm=length_px * mm_per_px,
            width_mm=width_px * mm_per_px,
        )
    return out


def measure(mask: np.ndarray, calib: Calibration | None = None) -> dict:
    """Measure a wound mask. Metric fields appear only when calib is given."""
    m = (mask > 0).astype(np.uint8)
    result: dict = dict(calibrated=False)

    px = _metrics_in_plane(m, None)
    if px is None:
        result.update(empty=True, area_px=0.0)
        return result
    result.update({k: px[k] for k in ("area_px", "perimeter_px", "length_px", "width_px")})
    x, y, w, h = cv2.boundingRect(_largest_contour(m))
    result["bbox_px"] = [int(x), int(y), int(w), int(h)]

    if calib is None:
        return result

    rect = rectify_mask(m, calib)
    met = _metrics_in_plane(rect, calib.mm_per_rect_px)
    if met is None:
        result.update(calibrated=False, note="mask fell outside the rectified plane")
        return result

    # Naive scale for comparison: what you would get from px * (mm/px) without
    # correcting perspective. The gap between the two is the tilt error.
    naive_area_mm2 = result["area_px"] / calib.naive_px_per_mm ** 2
    result.update(
        calibrated=True,
        area_mm2=round(met["area_mm2"], 2),
        area_cm2=round(met["area_cm2"], 3),
        perimeter_mm=round(met["perimeter_mm"], 2),
        length_mm=round(met["length_mm"], 2),
        width_mm=round(met["width_mm"], 2),
        naive_area_mm2=round(naive_area_mm2, 2),
        perspective_correction_pct=round(100.0 * (met["area_mm2"] - naive_area_mm2) / met["area_mm2"], 2),
        calibration=calib.to_dict(),
    )
    return result
