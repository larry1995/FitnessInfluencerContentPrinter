"""
contentprinter — stable library surface for the ContentPrinter pipeline.

This package is the supported import path for downstream consumers (e.g. the
CentralStrengthKB iOS app's FastAPI service). Everything exported here is
covered by the stability promise documented in API_SURFACE.md at the repo
root — function signatures, return types, and graceful-degradation semantics
will not change without a compatibility shim.

Internal pipeline modules live in `src/` and are imported by these shims
via a `sys.path` prepend below. Consumers should NOT import from `src.*`
directly — use `contentprinter.*` so future refactors don't break the app.
"""

import sys as _sys
from pathlib import Path as _Path

_SRC_DIR = _Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SRC_DIR))

from contentprinter.drafter import generate_draft
from contentprinter.parser import parse_draft_text
from contentprinter.chinese_drafter import (
    generate_chinese_from_english,
    is_llm_configured,
)
from contentprinter.single_page_generator import render_page
from contentprinter.pdf_downloader import download_references

__version__ = "0.1.1"

__all__ = [
    "generate_draft",
    "parse_draft_text",
    "generate_chinese_from_english",
    "is_llm_configured",
    "render_page",
    "download_references",
    "__version__",
]
