"""Extract text from the SNOC TSD.

The image's `cryptography` package is broken (its Rust binding needs a missing
cffi backend) and raises a PanicException rather than ImportError, so pypdf's
own try/except fallback never fires. Block the module at import time and pypdf
falls back to its no-crypto provider, which is all an unencrypted PDF needs.
"""
import sys

class Block:
    def find_module(self, name, path=None):
        return self if name == "cryptography" or name.startswith("cryptography.") else None
    def load_module(self, name):
        raise ImportError(f"{name} blocked (broken in this image)")

sys.meta_path.insert(0, Block())
sys.path.insert(0, "/tmp/pdlib")

from pypdf import PdfReader

src = sys.argv[1]
out = sys.argv[2]
r = PdfReader(src)
parts = []
for i, pg in enumerate(r.pages):
    parts.append(f"\n<!-- page {i+1} -->\n" + (pg.extract_text() or ""))
s = "".join(parts)
open(out, "w").write(s)
print(f"pages={len(r.pages)} chars={len(s)}")
