"""Library surface for draft generation.

Wraps `src/drafter.py` with a stable signature. The underlying
`draft_post_template` is script-oriented (assumes brand + sequence number
from a config file); this wrapper makes those optional so a FastAPI handler
can call `generate_draft(article)` with sane defaults.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import drafter as _drafter

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_BRAND_CACHE: dict | None = None


def _default_brand() -> dict:
    """Load and cache the default brand config from config/sources.json."""
    global _DEFAULT_BRAND_CACHE
    if _DEFAULT_BRAND_CACHE is None:
        with open(_PROJECT_ROOT / "config" / "sources.json", encoding="utf-8") as f:
            _DEFAULT_BRAND_CACHE = json.load(f)["brand"]
    return _DEFAULT_BRAND_CACHE


def generate_draft(
    article: dict[str, Any],
    *,
    brand: dict | None = None,
    post_number: int = 1,
) -> dict[str, Any]:
    """Generate an Instagram post draft dict from a scraped-article dict.

    Args:
        article: A scraped-article dict. Must contain at minimum `title`,
            `full_text`, and ideally `topic`, `source`, `url`, `summary`.
            This is the same shape that `src/scraper.py` and the other
            scrapers emit into `Posts/raw/*.json`.
        brand: Optional brand config override. Defaults to the project's
            `config/sources.json` brand block (Central Strength Gym).
        post_number: Sequential post number for the draft. Callers that
            produce multiple drafts in a batch should pass a running
            counter; callers producing one-off drafts can leave the default.

    Returns:
        A `Post` dict with keys: `post_number`, `topic`, `source`,
        `source_url`, `title`, `caption`, `key_points`, `carousel_slides`,
        `suggested_visual`, `drafted_at`.

    Stability: `Post` shape is part of the public surface. New fields may be
    added; existing fields and their types will not change.

    No network calls. No file writes. Safe to call from request handlers.
    """
    if not isinstance(article, dict) or not article.get("title"):
        raise ValueError("article must be a dict with a non-empty 'title'")
    brand = brand if brand is not None else _default_brand()
    return _drafter.draft_post_template(article, brand, post_number)
