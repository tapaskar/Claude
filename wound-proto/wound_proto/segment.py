"""Box-prompted wound segmentation with MobileSAM.

MobileSAM = SAM's prompt encoder + mask decoder with a 5M-param TinyViT image
encoder distilled from SAM ViT-H. It runs in ~2 s per image on a laptop CPU and
is the size class you would actually ship on a phone, which is why it is the
Phase 0 choice over ViT-B/H SAM or MedSAM.

The prompt is a bounding box. In the app that box comes from the user drawing
loosely around the wound; in evaluation it comes from the ground-truth mask,
dilated to simulate that looseness.
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

_DEFAULT_CKPT = Path(__file__).resolve().parent.parent / "weights" / "mobile_sam.pt"


def postprocess(mask: np.ndarray, open_px: int = 3) -> np.ndarray:
    """Largest connected component, holes filled, light morphological open.

    SAM masks on skin often carry a stray blob or a pinhole; a wound is one
    region without holes at this level of detail, so this is safe to enforce.
    """
    m = (mask > 0).astype(np.uint8)
    if m.sum() == 0:
        return m.astype(bool)
    if open_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_px, open_px))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return m.astype(bool)
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    m = (labels == largest).astype(np.uint8)
    # drawContours with FILLED on the external contour fills interior holes
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(m)
    cv2.drawContours(filled, cnts, -1, 1, thickness=cv2.FILLED)
    return filled.astype(bool)


class Segmenter:
    def __init__(self, checkpoint: str | os.PathLike | None = None, device: str = "cpu"):
        import torch
        from mobile_sam import SamPredictor, sam_model_registry

        ckpt = Path(checkpoint or os.environ.get("WOUND_PROTO_SAM_CKPT", _DEFAULT_CKPT))
        if not ckpt.exists():
            raise FileNotFoundError(
                f"MobileSAM checkpoint not found at {ckpt}. "
                "Run scripts/setup.sh or set WOUND_PROTO_SAM_CKPT.")
        self.model = sam_model_registry["vit_t"](checkpoint=str(ckpt))
        self.model.eval().to(device)
        self.predictor = SamPredictor(self.model)
        self.device = device
        self._torch = torch

    def set_image(self, img_rgb: np.ndarray) -> None:
        self.predictor.set_image(img_rgb)

    def predict_box(self, box_xyxy, post: bool = True) -> tuple[np.ndarray, float]:
        """Segment inside a box (x0, y0, x1, y1) on the image set by set_image()."""
        box = np.asarray(box_xyxy, dtype=np.float32)
        with self._torch.no_grad():
            masks, scores, _ = self.predictor.predict(box=box, multimask_output=False)
        mask = masks[0]
        return (postprocess(mask) if post else mask.astype(bool)), float(scores[0])

    def segment(self, img_rgb: np.ndarray, box_xyxy, post: bool = True) -> tuple[np.ndarray, float]:
        self.set_image(img_rgb)
        return self.predict_box(box_xyxy, post=post)
