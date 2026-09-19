from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    ROOT / "src",
    ROOT / "adapters/personalization-bilibili/src",
    ROOT / "adapters/personalization-article/src",
):
    sys.path.insert(0, str(source_path))
