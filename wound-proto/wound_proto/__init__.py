"""wound-proto: Phase 0 wound-measurement prototype.

Pipeline: ArUco marker -> metric homography  |  box prompt -> MobileSAM mask
          -> mask rectified into the metric plane -> area / perimeter / length / width.

Two error sources are kept separable on purpose:
  * calibration + measurement  (tested on synthetic fixtures with exact ground truth)
  * segmentation               (tested on FUSeg against clinician masks)
"""
from .calibrate import Calibration, calibrate, detect_marker
from .measure import measure
from .segment import Segmenter, postprocess

__all__ = ["Calibration", "calibrate", "detect_marker", "measure", "Segmenter", "postprocess"]
__version__ = "0.1.0"
