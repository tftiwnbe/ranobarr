from __future__ import annotations

import re
from typing import Any


def normalize_book_title(raw_title: Any) -> str:
    title = re.sub(r"\s+", " ", str(raw_title or "")).strip()
    title = re.sub(r"\s*\((?:новелла)\)\s*$", "", title, flags=re.IGNORECASE)
    return title.strip() or "Untitled"
