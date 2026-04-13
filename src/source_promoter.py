"""
Promote raw reddit/forum scraper records into the per-topic work/ layout.

The scrapers (reddit_scraper, forum_scraper) emit batch JSON into
`work/raw/reddit_*.json` and `work/raw/forum_*.json`. This module takes
one such record and fans it out into:

    work/<slug>/en/draft.txt      — human-editable caption stub
    work/<slug>/en/source.json    — structured community metadata
                                    (matches config/source_format_design.md
                                     §3.2 for reddit, §4.2 for forum)
    work/<slug>/meta.json         — topic-level metadata, with `source_type`
    work/<slug>/pdfs/             — empty directory (for consistency with
                                    the rest of the layout)

Called by `reddit_scraper.scrape_reddit()` and `forum_scraper.scrape_forums()`
after their scrape loops finish. Also callable directly:

    python src/source_promoter.py --raw work/raw/reddit_20260412_001530.json

Design:
- Never overwrites an existing hand-edited `draft.txt`. The draft stub is a
  one-time seed; if the file already exists, the promoter only refreshes
  `source.json` and `meta.json`.
- Uses `posts_layout.resolve_topic_slug` so a record that round-trips (e.g.
  re-scraped reddit thread) always lands in the same topic directory.
- Guarantees `len(reddit_callouts) <= 4` and `len(forum_quote_chain) <= 4`
  per frontend-writer's renderer contract.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from posts_layout import merge_meta, resolve_topic_slug

PROJECT_ROOT = Path(__file__).parent.parent
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize

MAX_REDDIT_CALLOUTS = 4
MAX_FORUM_QUOTE_CHAIN = 4
MAX_FLAIR_CHARS = 20
MAX_RANK_CHARS = 30

_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF"         # miscellaneous symbols & pictographs
    r"\U00002600-\U000027BF"          # dingbats & misc symbols
    r"\U0001F000-\U0001F2FF"          # mahjong / playing cards / enclosed
    r"\U0001F1E6-\U0001F1FF"          # regional indicator (flags)
    r"\U0000FE00-\U0000FE0F"          # variation selectors
    r"\U0000200D]",                   # zero-width joiner
    flags=re.UNICODE,
)


def _sanitize_label(raw: str | None, max_chars: int) -> str | None:
    """Scraper-owned flair/rank sanitization (spec from sidecar schema Q4)."""
    if not raw:
        return None
    cleaned = _EMOJI_RE.sub("", raw).strip()
    if not cleaned or not any(ch.isalnum() for ch in cleaned):
        return None
    return cleaned[:max_chars]


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_") or "post"


def _truncate_slug_on_word_boundary(slug: str, max_chars: int) -> str:
    """Truncate a slug so it never splits mid-word.

    Breaks at the last `_` within `max_chars`, falling back to a hard cut
    only when the first word is itself longer than `max_chars`. Fixes the
    `..._vs_percentage_trai` awkwardness from #13 first-encounter slugs
    without changing round-trip semantics (already-migrated topics are
    still preferred via `posts_layout.resolve_topic_slug`).
    """
    if len(slug) <= max_chars:
        return slug
    cut = slug[:max_chars]
    last_break = cut.rfind("_")
    if last_break > 0:
        return cut[:last_break]
    return cut


def _derive_community_slug(record: dict) -> str:
    """Build a per-topic slug for a community record.

    Uses `posts_layout.resolve_topic_slug` to round-trip via source_url first.
    Falls back to `{source_type}_<subreddit_or_forum>_<title_slug>`.
    """
    round_trip = resolve_topic_slug({
        "topic": record.get("source_type", "community"),
        "title": record.get("thread_title") or record.get("title", ""),
        "source_url": record.get("thread_permalink") or record.get("url", ""),
    })
    if round_trip and not round_trip.startswith(
        (f"{record.get('source_type', 'x')}_", "community_")
    ):
        return round_trip

    source_type = record.get("source_type") or "community"
    if source_type == "reddit":
        prefix = f"reddit_{record.get('subreddit', 'unknown')}"
    elif source_type == "forum":
        prefix = f"forum_{_slugify(record.get('forum_name', 'unknown'))}"
    else:
        prefix = source_type

    title = record.get("thread_title") or record.get("title", "")
    title_slug = _truncate_slug_on_word_boundary(_slugify(title), 40)
    return f"{prefix}_{title_slug}" if title_slug else prefix


def _build_reddit_sidecar(record: dict) -> dict:
    callouts_raw = record.get("reddit_callouts", []) or []
    callouts: list[dict] = []
    for raw in callouts_raw[:MAX_REDDIT_CALLOUTS]:
        callouts.append({
            "author": raw.get("author", "u/unknown"),
            "score": int(raw.get("score", 0) or 0),
            "body": (raw.get("body", "") or "")[:500],
            "permalink": raw.get("permalink", "") or "",
            "is_op_reply": bool(raw.get("is_op_reply", False)),
            "flair": _sanitize_label(raw.get("flair"), MAX_FLAIR_CHARS),
        })

    return {
        "source_type": "reddit",
        "subreddit": record.get("subreddit", ""),
        "thread_title": record.get("thread_title") or record.get("title", ""),
        "thread_score": int(record.get("thread_score", record.get("score", 0)) or 0),
        "thread_permalink": record.get("thread_permalink") or record.get("url", ""),
        "op_author": record.get("op_author", "u/unknown"),
        "op_body": (record.get("op_body") or record.get("full_text", ""))[:600],
        "fetched_at": record.get("scraped_at", datetime.now().isoformat(timespec="seconds")),
        "evidence_info": {},
        "reddit_callouts": callouts,
    }


def _build_forum_sidecar(record: dict) -> dict:
    chain_raw = record.get("forum_quote_chain", []) or []
    chain: list[dict] = []
    for raw in chain_raw[:MAX_FORUM_QUOTE_CHAIN]:
        chain.append({
            "author": raw.get("author", "unknown"),
            "rank": _sanitize_label(raw.get("rank"), MAX_RANK_CHARS),
            "body": (raw.get("body", "") or "")[:600],
            "quoting": raw.get("quoting"),
            "permalink": raw.get("permalink", "") or "",
        })

    forum_meta = record.get("forum_meta", {}) or {}
    return {
        "source_type": "forum",
        "forum_name": forum_meta.get("forum_name") or record.get("source", ""),
        "subforum": forum_meta.get("subforum", ""),
        "thread_title": record.get("thread_title") or record.get("title", ""),
        "thread_url": record.get("thread_url") or record.get("url", ""),
        "op_author": record.get("op_author", "unknown"),
        "op_rank": _sanitize_label(record.get("op_rank"), MAX_RANK_CHARS),
        "op_post_count": record.get("op_post_count"),
        "op_body": (record.get("op_body") or record.get("full_text", ""))[:800],
        "fetched_at": record.get("scraped_at", datetime.now().isoformat(timespec="seconds")),
        "evidence_info": {},
        "forum_quote_chain": chain,
    }


def _build_draft_stub(record: dict, sidecar: dict) -> str:
    """One-time seed for `draft.txt`. Humans layer their own commentary on top.

    Intentionally terse — the author doesn't want the scraper to pretend it's
    writing the post. We just hand them the thread title, OP excerpt, top
    callouts as reference material, and let them craft the caption.
    """
    lines: list[str] = []
    source_type = sidecar.get("source_type", "community")
    lines.append("=" * 60)
    lines.append(f"POST — {source_type.upper()} THREAD")
    if source_type == "reddit":
        lines.append(f"Source: r/{sidecar.get('subreddit', '')} "
                     f"({sidecar.get('thread_permalink', '')})")
    else:
        lines.append(f"Source: {sidecar.get('forum_name', '')} "
                     f"({sidecar.get('thread_url', '')})")
    lines.append(f"Drafted: {datetime.now().isoformat(timespec='seconds')} (auto-seeded)")
    lines.append("=" * 60)
    lines.append("")
    lines.append("CAPTION:")
    lines.append("-" * 40)
    lines.append(sidecar.get("thread_title", "").strip() or "(untitled)")
    lines.append("")
    op_body = sidecar.get("op_body", "").strip()
    if op_body:
        lines.append("OP excerpt:")
        lines.append(op_body)
        lines.append("")

    callouts = sidecar.get("reddit_callouts") or sidecar.get("forum_quote_chain") or []
    if callouts:
        lines.append("Top callouts (raw — edit before posting):")
        for i, c in enumerate(callouts, 1):
            author = c.get("author", "")
            score = c.get("score")
            flair = c.get("flair") or c.get("rank") or ""
            header = f"  {i}. {author}"
            if score is not None:
                header += f" ▲{score}"
            if flair:
                header += f" [{flair}]"
            lines.append(header)
            body = (c.get("body", "") or "").strip()
            if body:
                lines.append(f"     {body[:300]}")
        lines.append("")

    lines.append("-" * 40)
    lines.append("")
    lines.append("NOTE: this file is a one-time scraper seed. Edit it to add")
    lines.append("your commentary, pick the strongest 2-3 callouts, and write")
    lines.append("the Central Strength caption. The renderer reads source.json")
    lines.append("for the structured layout — don't try to recreate it here.")
    lines.append("")
    return "\n".join(lines)


def promote_record(record: dict, *, dry_run: bool = False) -> tuple[str, str]:
    """Promote one raw scraper record to the per-topic layout.

    Returns `(slug, status)` where status is one of:
      "created"            — topic dir did not exist; draft + source + meta written
      "updated"            — source + meta refreshed; existing draft.txt preserved
      "skipped (no title)" — record had no usable title/source_url
    """
    source_type = record.get("source_type", "")
    if source_type not in {"reddit", "forum"}:
        return ("", f"skipped (source_type={source_type!r}, not a community record)")

    title = record.get("thread_title") or record.get("title", "")
    if not title:
        return ("", "skipped (no title)")

    slug = _derive_community_slug(record)
    topic_dir = POSTS_DIR / slug
    en_dir = topic_dir / "en"
    pdfs_dir = topic_dir / "pdfs"
    draft_path = en_dir / "draft.txt"
    sidecar_path = en_dir / "source.json"
    meta_path = topic_dir / "meta.json"

    sidecar = (
        _build_reddit_sidecar(record) if source_type == "reddit"
        else _build_forum_sidecar(record)
    )

    new_meta = {
        "topic_slug": slug,
        "topic_label": "community",
        "source_type": source_type,
        "source_name": record.get("source", ""),
        "source_url": sidecar.get("thread_permalink") or sidecar.get("thread_url", ""),
        "title": title,
        "drafted_at": sidecar.get("fetched_at", ""),
        "has_chinese": (topic_dir / "zh" / "draft.txt").exists(),
    }

    existing_meta = None
    if meta_path.exists():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_meta = None

    merged_meta = merge_meta(existing_meta, new_meta)

    if dry_run:
        return (slug, "dry-run")

    en_dir.mkdir(parents=True, exist_ok=True)
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    draft_existed = draft_path.exists()
    if not draft_existed:
        draft_path.write_text(_build_draft_stub(record, sidecar), encoding="utf-8")

    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    meta_path.write_text(
        json.dumps(merged_meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return (slug, "updated" if draft_existed else "created")


def promote_records(records: list[dict], *, dry_run: bool = False) -> dict:
    summary = {"created": 0, "updated": 0, "skipped": 0, "slugs": []}
    for record in records:
        slug, status = promote_record(record, dry_run=dry_run)
        if status.startswith("created"):
            summary["created"] += 1
            summary["slugs"].append(slug)
        elif status.startswith("updated") or status.startswith("dry-run"):
            summary["updated"] += 1
            summary["slugs"].append(slug)
        else:
            summary["skipped"] += 1
    return summary


def promote_from_raw_file(path: Path, *, dry_run: bool = False) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list of records")
    print(f"[promote] {path.name}: {len(data)} record(s)")
    summary = promote_records(data, dry_run=dry_run)
    print(f"  created={summary['created']} updated={summary['updated']} "
          f"skipped={summary['skipped']}")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Promote raw reddit/forum scraper records to per-topic drafts"
    )
    parser.add_argument("--raw", type=Path, help="Specific work/raw/*.json file to promote")
    parser.add_argument("--all", action="store_true",
                        help="Promote every work/raw/reddit_*.json and forum_*.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.raw and not args.all:
        parser.error("specify --raw PATH or --all")

    targets: list[Path] = []
    if args.raw:
        targets.append(args.raw)
    if args.all:
        raw_dir = POSTS_DIR / "raw"
        if raw_dir.exists():
            targets.extend(sorted(raw_dir.glob("reddit_*.json")))
            targets.extend(sorted(raw_dir.glob("forum_*.json")))

    if not targets:
        print("[INFO] no raw files found to promote")
        sys.exit(0)

    for path in targets:
        promote_from_raw_file(path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
