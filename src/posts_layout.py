"""
Shared layout helpers for the per-topic Posts/ tree.

Single source of truth for:
    - merge_meta(existing, new)    — unified meta.json merge strategy
    - resolve_topic_slug(post)     — round-trip-safe slug derivation for drafter
    - slug_from_source_url(url)    — lookup existing topic by source URL

Historical context: Task #2 (reorg) and Task #5 (chinese drafter integration)
both introduced their own meta.json merge logic and their own slug derivation,
which drifted. Code-reviewer flagged this as tasks #11 and #12. This module is
the fix — `reorganize_posts.py` and `drafter.py` now both import from here.
"""

import json
import re
import sys as _sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

PROJECT_ROOT = Path(__file__).parent.parent
POSTS_DIR = PROJECT_ROOT / "Posts"

_SRC_DIR = str(PROJECT_ROOT / "src")
if _SRC_DIR not in _sys.path:
    _sys.path.insert(0, _SRC_DIR)

try:
    from recursive_discovery import normalize_url as _base_normalize_url
except ImportError:
    def _base_normalize_url(url: str) -> str:
        return (url or "").strip()


_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = frozenset({
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "ref_url",
    "igshid", "yclid", "msclkid", "_hsenc", "_hsmi",
})


def _strip_tracking_params(url: str) -> str:
    """Drop common tracking query parameters while preserving real content params.

    Removes `utm_*`, `fbclid`, `gclid`, etc. Keeps everything else — e.g.
    `?id=123`, `?page=2`, `?v=dQw4w9WgXcQ`, Reddit's `?t=week` — because
    those are frequently load-bearing for content identity.
    """
    if not url:
        return url
    try:
        parts = urlparse(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    kept = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
        and not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    new_query = urlencode(kept, doseq=True)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, ""))


def _normalize_url(url: str) -> str:
    """Canonical form for source-URL comparison: base normalize + tracking strip."""
    return _base_normalize_url(_strip_tracking_params(url))


MERGE_PRESERVE_KEYS = (
    "tags",
    "references",
    "topic_label",
    "source_name",
    "source_url",
    "title",
)

MERGE_UPDATE_KEYS = (
    "post_number",
    "topic_slug",
    "has_chinese",
    "drafted_at",
    "migrated_at",
    "source_type",
)


def merge_meta(existing: dict | None, new: dict) -> dict:
    """Merge a freshly-built meta dict with any existing on-disk meta.

    Rules:
      - Keys in MERGE_PRESERVE_KEYS: if existing has a truthy value, keep it.
        This protects hand-edited fields (tags, references curated by the
        author, topic label reclassifications, etc.) from being clobbered.
      - Keys in MERGE_UPDATE_KEYS: new value always wins. These are intrinsic
        facts (post number, slug, Chinese presence, timestamps) that should
        reflect the latest state.
      - Any other key in `existing` is preserved as-is (future extensibility).

    Pass existing=None to simply return `new` as a fresh dict.
    """
    if not existing:
        return dict(new)

    merged = dict(existing)
    for key in MERGE_UPDATE_KEYS:
        if key in new:
            merged[key] = new[key]
    for key in MERGE_PRESERVE_KEYS:
        if not merged.get(key) and new.get(key):
            merged[key] = new[key]
    for key, value in new.items():
        if key not in merged:
            merged[key] = value
    return merged


def _slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower())
    return text.strip("_") or "post"


def slug_from_source_url(source_url: str) -> str | None:
    """Scan existing Posts/<slug>/meta.json files for a match on source_url.

    Returns the matching slug or None. Used by `resolve_topic_slug` so that
    round-tripping a migrated post through the drafter doesn't regenerate a
    new slug and orphan the original directory.

    Matching is done on `normalize_url`-canonicalized forms (fragments stripped,
    host lowercased, trailing slash dropped) so that tracking-parameter churn
    like `?utm_source=feed` or a stray `#comments` anchor doesn't orphan an
    existing topic. This matters most for reddit and forum re-scrapes where
    the same thread can surface with different query params each run.
    """
    if not source_url or not POSTS_DIR.exists():
        return None
    target = _normalize_url(source_url)
    if not target:
        return None
    for topic_dir in POSTS_DIR.iterdir():
        if not topic_dir.is_dir():
            continue
        meta_path = topic_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        existing = _normalize_url(meta.get("source_url", ""))
        if existing and existing == target:
            return topic_dir.name
    return None


def resolve_topic_slug(post: dict) -> str:
    """Determine the per-topic directory slug for a drafted post.

    Priority:
      1. If an existing `meta.json` already maps `post.source_url` → slug,
         reuse that slug (round-trip-safe for migrated posts).
      2. Otherwise, derive `{topic}_{slugified_title[:40]}` for new content.
    """
    source_url = post.get("source_url", "") or ""
    existing_slug = slug_from_source_url(source_url)
    if existing_slug:
        return existing_slug

    topic = post.get("topic", "general") or "general"
    title_slug = _slugify(post.get("title", ""))[:40]
    return f"{topic}_{title_slug}" if title_slug else topic
