#!/usr/bin/env bash
# Fetch the two external pieces the prototype needs. Neither is committed:
#   * MobileSAM code + 39 MB checkpoint (Apache-2.0)
#   * FUSeg - Foot Ulcer Segmentation Challenge dataset (for evaluation only)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor weights

if [ ! -d vendor/MobileSAM ]; then
  git clone --depth 1 https://github.com/ChaoningZhang/MobileSAM vendor/MobileSAM
fi
cp vendor/MobileSAM/weights/mobile_sam.pt weights/mobile_sam.pt
pip install -e vendor/MobileSAM
pip install -e .

if [ ! -d vendor/wound-segmentation ]; then
  git clone --depth 1 https://github.com/uwm-bigdata/wound-segmentation vendor/wound-segmentation
fi
echo
echo "FUSeg root: vendor/wound-segmentation/data/Foot Ulcer Segmentation Challenge"
echo "Try:  python -m wound_proto.evaluate synth --n 40"
