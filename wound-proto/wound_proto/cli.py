"""Analyze one photo.

  python -m wound_proto photo.jpg --box 410,380,780,720 --marker-mm 20 \\
      --out result.json --overlay overlay.png

The box is the user's loose rectangle around the wound, in image pixels
(x0,y0,x1,y1). If no marker is found the result is pixel-only and
`calibrated` is false - it never guesses a scale.
"""
from __future__ import annotations

import argparse
import json
import sys

import cv2

from .calibrate import calibrate
from .evaluate import overlay
from .measure import measure
from .segment import Segmenter


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wound_proto")
    ap.add_argument("image")
    ap.add_argument("--box", required=True, help="x0,y0,x1,y1 in image pixels")
    ap.add_argument("--marker-mm", type=float, default=20.0, help="printed marker side length")
    ap.add_argument("--out", default=None, help="write JSON here (default: stdout)")
    ap.add_argument("--overlay", default=None, help="write an annotated PNG here")
    ap.add_argument("--ckpt", default=None)
    args = ap.parse_args(argv)

    img = cv2.imread(args.image)
    if img is None:
        ap.error(f"cannot read {args.image}")
    box = [float(v) for v in args.box.split(",")]
    if len(box) != 4:
        ap.error("--box must be x0,y0,x1,y1")

    seg = Segmenter(args.ckpt)
    mask, score = seg.segment(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), box)
    calib = calibrate(img, args.marker_mm)
    result = measure(mask, calib)
    result.update(image=args.image, box_xyxy=box, sam_score=round(score, 3),
                  marker_found=calib is not None)
    if calib is None:
        result["warning"] = ("no calibration marker detected - measurements are in pixels only; "
                             "place a printed marker of known size in the frame")

    js = json.dumps(result, indent=1)
    if args.out:
        open(args.out, "w").write(js)
    else:
        print(js)
    if args.overlay:
        ov = overlay(img, None, mask, box)
        if calib is not None:
            c = calib.corners_px.astype(int)
            cv2.polylines(ov, [c.reshape(-1, 1, 2)], True, (255, 0, 255), 2)
            if result.get("calibrated"):
                txt = f"{result['area_cm2']:.2f} cm2  L {result['length_mm']:.0f} x W {result['width_mm']:.0f} mm"
                cv2.putText(ov, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imwrite(args.overlay, ov)
    return 0


if __name__ == "__main__":
    sys.exit(main())
