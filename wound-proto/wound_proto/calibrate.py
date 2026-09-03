"""Scale calibration from a printed ArUco marker.

A marker of known side length gives four image points with known metric
positions. From those we build a homography that maps the *image plane* onto a
*metric plane* (millimetres). Measuring in that plane, rather than multiplying
pixels by a single "px per mm", corrects perspective foreshortening when the
camera is not square-on.

Limitation, stated up front: a homography assumes the wound is coplanar with
the marker. Wounds on curved anatomy (heel, calf, sacrum) violate that, and the
error grows with curvature. That is the problem depth sensing (LiDAR / ToF)
exists to solve; it is out of scope for Phase 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# 4x4 dictionary: robust at small print sizes, plenty of ids for a prototype.
ARUCO_DICT = cv2.aruco.DICT_4X4_50

# Resolution of the metric plane we rectify into. 0.1 mm / px is finer than any
# clinical need and keeps the warped canvas a sane size for a phone photo.
RECT_PX_PER_MM = 10.0
MAX_RECT_SIDE = 6000  # px - cap the rectified canvas under extreme perspective


@dataclass
class Calibration:
    marker_id: int
    corners_px: np.ndarray            # (4, 2) image-space corners, TL TR BR BL
    marker_mm: float
    homography: np.ndarray            # 3x3, image px -> metric plane px
    rect_px_per_mm: float             # resolution of the metric plane
    rect_size: tuple[int, int]        # (w, h) of the rectified canvas
    naive_px_per_mm: float            # mean marker side / marker_mm, for comparison
    tilt_deg: float = field(default=0.0)   # crude perspective estimate for reporting

    @property
    def mm_per_rect_px(self) -> float:
        return 1.0 / self.rect_px_per_mm

    def to_dict(self) -> dict:
        return dict(
            marker_id=int(self.marker_id),
            marker_mm=float(self.marker_mm),
            naive_px_per_mm=round(float(self.naive_px_per_mm), 4),
            rect_px_per_mm=float(self.rect_px_per_mm),
            rect_size=[int(self.rect_size[0]), int(self.rect_size[1])],
            tilt_deg=round(float(self.tilt_deg), 1),
            corners_px=np.round(self.corners_px, 1).tolist(),
        )


def detect_marker(img_bgr: np.ndarray, dictionary: int = ARUCO_DICT):
    """Return (marker_id, corners[4,2]) for the largest detected marker, or None."""
    d = cv2.aruco.getPredefinedDictionary(dictionary)
    params = cv2.aruco.DetectorParameters()
    # Sub-pixel corner refinement matters: scale error is proportional to
    # corner error, and a 20 mm marker at 200 px means 1 px = 0.5% of scale.
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    det = cv2.aruco.ArucoDetector(d, params)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    corners, ids, _ = det.detectMarkers(gray)
    if ids is None or len(ids) == 0:
        return None
    # OpenCV 4.x returns ids as (N,1), 5.x as (N,): flatten so both work
    ids = np.asarray(ids).reshape(-1)
    quads = [np.asarray(c).reshape(4, 2).astype(np.float64) for c in corners]
    areas = [cv2.contourArea(q.astype(np.float32)) for q in quads]
    i = int(np.argmax(areas))
    return int(ids[i]), quads[i]


def _perspective_tilt_deg(corners: np.ndarray) -> float:
    """Crude tilt estimate: ratio of the shorter to longer opposite-side pair."""
    tl, tr, br, bl = corners
    top, bottom = np.linalg.norm(tr - tl), np.linalg.norm(br - bl)
    left, right = np.linalg.norm(bl - tl), np.linalg.norm(br - tr)
    r = min(min(top, bottom) / max(top, bottom), min(left, right) / max(left, right))
    return float(np.degrees(np.arccos(np.clip(r, 0.0, 1.0))))


def calibrate(img_bgr: np.ndarray, marker_mm: float,
              dictionary: int = ARUCO_DICT) -> Calibration | None:
    """Detect the marker and build the image->metric homography.

    Returns None if no marker is found; callers should then report pixel-only
    measurements and flag the result as uncalibrated rather than guess.
    """
    found = detect_marker(img_bgr, dictionary)
    if found is None:
        return None
    marker_id, corners = found
    h, w = img_bgr.shape[:2]

    side_px = float(np.mean([np.linalg.norm(corners[i] - corners[(i + 1) % 4]) for i in range(4)]))
    naive_px_per_mm = side_px / marker_mm

    # Metric square for the marker, in rectified pixels. Placed at the origin;
    # we will translate the whole plane after seeing where the image lands.
    s = marker_mm * RECT_PX_PER_MM
    dst = np.array([[0, 0], [s, 0], [s, s], [0, s]], dtype=np.float64)
    H0 = cv2.getPerspectiveTransform(corners.astype(np.float32), dst.astype(np.float32))

    # Where do the image corners land in the metric plane? Translate so the
    # rectified canvas starts at (0,0) and size it to contain the whole image.
    img_corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32).reshape(-1, 1, 2)
    proj = cv2.perspectiveTransform(img_corners, H0).reshape(-1, 2)
    xmin, ymin = proj.min(axis=0)
    xmax, ymax = proj.max(axis=0)
    rect_w, rect_h = float(xmax - xmin), float(ymax - ymin)

    scale = 1.0
    if max(rect_w, rect_h) > MAX_RECT_SIDE:
        scale = MAX_RECT_SIDE / max(rect_w, rect_h)
    T = np.array([[scale, 0, -xmin * scale], [0, scale, -ymin * scale], [0, 0, 1]], dtype=np.float64)
    H = T @ H0
    rect_size = (int(np.ceil(rect_w * scale)) + 1, int(np.ceil(rect_h * scale)) + 1)

    return Calibration(
        marker_id=marker_id, corners_px=corners, marker_mm=marker_mm,
        homography=H, rect_px_per_mm=RECT_PX_PER_MM * scale, rect_size=rect_size,
        naive_px_per_mm=naive_px_per_mm, tilt_deg=_perspective_tilt_deg(corners),
    )


def rectify_mask(mask: np.ndarray, calib: Calibration) -> np.ndarray:
    """Warp a binary mask from image space into the metric plane (uint8 0/1)."""
    m = (mask > 0).astype(np.uint8)
    return cv2.warpPerspective(m, calib.homography, calib.rect_size, flags=cv2.INTER_NEAREST)
