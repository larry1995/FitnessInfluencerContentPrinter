"""
Reddit scraper for ContentPrinter.

Reads public JSON listings from old.reddit.com (no auth, no API key) for the
subreddits configured in config/reddit_sources.json, then recursively expands
outbound links in top-level selftext and top-comments up to depth 2. Each
surfaced article gets fetched as HTML and distilled with the same BeautifulSoup
cleanup used by src/scraper.py, so downstream drafting/meta steps just work.

Notes
-----
* Uses src/http_utils.create_session for all HTTP (timeout + retry).
* No login; no OAuth. We only read public listings.
* Visited set persisted across runs at Posts/.seen_reddit_hashes.json —
  prevents duplicates and cycles.
* `--fixture-dir DIR` routes all HTTP through local files for CI smoke tests.
  Expected layout:
      DIR/reddit/<subreddit>_<listing>.json
      DIR/html/<sha1-of-url>.html

Run:
    python src/reddit_scraper.py                           # live
    python src/reddit_scraper.py --fixture-dir tests/fixtures
    python src/reddit_scraper.py --depth 2 --limit 5
"""

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup

from http_utils import create_session, get as http_get
from recursive_discovery import (
    RobotsCache,
    VisitedSet,
    extract_outbound_links,
    normalize_url,
    polite_sleep,
    url_hash,
)

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize

VISITED_PATH = POSTS_DIR / ".seen_reddit_hashes.json"
DEFAULT_UA = "ContentPrinter/1.0 (+https://centralstrengthgyms.com)"


@dataclass
class ScrapeContext:
    session: object
    visited: VisitedSet
    allowlist: list[str]
    blocklist: list[str]
    max_outbound: int
    delay: float
    recursion_depth: int
    robots: RobotsCache | None = None
    respect_robots: bool = True
    fixture_dir: Path | None = None
    results: list[dict] = field(default_factory=list)


def load_reddit_config() -> dict:
    with open(CONFIG_DIR / "reddit_sources.json", encoding="utf-8") as f:
        return json.load(f)


def _fixture_path_for_url(fixture_dir: Path, url: str) -> Path:
    h = hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:16]
    return fixture_dir / "html" / f"{h}.html"


def _fetch_text(ctx: ScrapeContext, url: str) -> str:
    if ctx.fixture_dir is not None:
        fp = _fixture_path_for_url(ctx.fixture_dir, url)
        if fp.exists():
            return fp.read_text(encoding="utf-8")
        return ""
    if ctx.respect_robots and ctx.robots is not None and not ctx.robots.can_fetch(url):
        print(f"  [ROBOTS] disallowed: {url}")
        return ""
    polite_sleep(ctx.delay)
    try:
        resp = http_get(ctx.session, url)
        return resp.text
    except Exception as e:
        print(f"  [WARN] fetch failed: {url} ({e})")
        return ""


def _load_subreddit_json(ctx: ScrapeContext, subreddit: str, listing: str, window: str) -> dict | None:
    if ctx.fixture_dir is not None:
        fp = ctx.fixture_dir / "reddit" / f"{subreddit}_{listing}.json"
        if not fp.exists():
            print(f"  [WARN] fixture missing: {fp}")
            return None
        return json.loads(fp.read_text(encoding="utf-8"))

    url = f"https://old.reddit.com/r/{subreddit}/{listing}.json?t={window}&limit=25"
    if ctx.respect_robots and ctx.robots is not None and not ctx.robots.can_fetch(url):
        print(f"  [ROBOTS] disallowed: {url}")
        return None
    polite_sleep(ctx.delay)
    try:
        resp = http_get(ctx.session, url)
        return resp.json()
    except Exception as e:
        print(f"  [ERROR] failed to load r/{subreddit} {listing}: {e}")
        return None


def _load_post_comments_json(ctx: ScrapeContext, permalink: str) -> list | None:
    if ctx.fixture_dir is not None:
        h = hashlib.sha1(permalink.encode()).hexdigest()[:16]
        fp = ctx.fixture_dir / "reddit" / f"comments_{h}.json"
        if not fp.exists():
            return None
        return json.loads(fp.read_text(encoding="utf-8"))
    url = f"https://old.reddit.com{permalink}.json?limit=5"
    if ctx.respect_robots and ctx.robots is not None and not ctx.robots.can_fetch(url):
        return None
    polite_sleep(ctx.delay)
    try:
        resp = http_get(ctx.session, url)
        return resp.json()
    except Exception:
        return None


def _extract_post_text(post_data: dict) -> str:
    return post_data.get("selftext", "") or post_data.get("title", "") or ""


def _extract_top_comment_texts(comments_payload) -> list[str]:
    """Dig into reddit's nested `t1` comment format and return top-level comment bodies."""
    return [c["body"] for c in _extract_top_callouts(comments_payload)]


def _extract_top_callouts(comments_payload, max_callouts: int = 4) -> list[dict]:
    """Return structured top-level comments for the sidecar `reddit_callouts` field.

    Each entry matches `config/source_format_design.md` §3.2 schema:
      author, score, body, permalink, is_op_reply, flair
    Ranked by reddit's native sort order (the JSON listing is already
    sorted; we trust it and cap at `max_callouts` per frontend-writer's ask).
    """
    if not isinstance(comments_payload, list) or len(comments_payload) < 2:
        return []
    listing = comments_payload[1].get("data", {}).get("children", [])
    op_author = None
    if isinstance(comments_payload[0], dict):
        op_children = comments_payload[0].get("data", {}).get("children", [])
        if op_children:
            op_author = op_children[0].get("data", {}).get("author")

    callouts: list[dict] = []
    for child in listing:
        if child.get("kind") != "t1":
            continue
        data = child.get("data", {})
        body = data.get("body", "")
        if not body:
            continue
        author = data.get("author", "") or ""
        callouts.append({
            "author": f"u/{author}" if author and not author.startswith("u/") else (author or "u/unknown"),
            "score": int(data.get("score", 0) or 0),
            "body": body[:500],
            "permalink": (
                f"https://old.reddit.com{data.get('permalink', '')}"
                if data.get("permalink") else ""
            ),
            "is_op_reply": bool(op_author and data.get("author") == op_author),
            "flair": _sanitize_flair(data.get("author_flair_text")),
        })
        if len(callouts) >= max_callouts:
            break
    return callouts


_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF"
    r"\U00002600-\U000027BF"
    r"\U0001F000-\U0001F2FF"
    r"\U0001F1E6-\U0001F1FF"
    r"\U0000FE00-\U0000FE0F"
    r"\U0000200D]",
    flags=re.UNICODE,
)


def _sanitize_flair(flair: str | None, max_chars: int = 20) -> str | None:
    """Strip emoji, trim whitespace, cap length, discard punctuation-only strings.

    Returns None if the cleaned value is empty. Matches the rule set I agreed
    with frontend-writer re: §7.4 of source_format_design.md — scraper owns
    sanitization so the renderer stays ignorant of subreddit-specific quirks.
    """
    if not flair:
        return None
    cleaned = _EMOJI_RE.sub("", flair).strip()
    if not cleaned or not any(ch.isalnum() for ch in cleaned):
        return None
    return cleaned[:max_chars]


def _html_to_text(html: str) -> tuple[str, str]:
    """Return (title, cleaned_text) from raw HTML."""
    if not html:
        return "", ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "form", "iframe", "noscript"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    article = (soup.find("article") or soup.find("main") or soup)
    text = article.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return title, "\n".join(lines)


def _process_outbound(ctx: ScrapeContext, link: str, depth: int, parent: dict) -> None:
    """Fetch a discovered outbound link and add a result record."""
    if depth > ctx.recursion_depth:
        return
    if not ctx.visited.add(link):
        return

    html = _fetch_text(ctx, link)
    if not html:
        return
    title, text = _html_to_text(html)
    if len(text) < 200:
        return

    record = {
        "title": title or link,
        "url": link,
        "source": f"outbound-from-{parent.get('source', 'reddit')}",
        "topic": parent.get("topic", "general"),
        "summary": text[:500],
        "full_text": text[:20000],
        "scraped_at": datetime.now().isoformat(),
        "hash": url_hash(link),
        "discovery_depth": depth,
        "parent_url": parent.get("url", ""),
        "source_type": "outbound",
    }
    ctx.results.append(record)
    print(f"    [+] d{depth} {link[:80]}")

    if depth < ctx.recursion_depth:
        next_links = extract_outbound_links(
            html, link,
            allowlist=ctx.allowlist,
            blocklist=ctx.blocklist,
            max_links=ctx.max_outbound,
        )
        for nl in next_links:
            _process_outbound(ctx, nl, depth + 1, record)


def _process_post(ctx: ScrapeContext, post_data: dict, subreddit: str, min_score: int, min_comments: int) -> None:
    score = post_data.get("score", 0)
    num_comments = post_data.get("num_comments", 0)
    if score < min_score or num_comments < min_comments:
        return

    permalink = post_data.get("permalink", "")
    post_url = f"https://old.reddit.com{permalink}" if permalink else post_data.get("url", "")
    if not post_url or not ctx.visited.add(post_url):
        return

    title = post_data.get("title", "")
    selftext = _extract_post_text(post_data)

    op_author = post_data.get("author", "") or ""
    record = {
        "title": title,
        "url": post_url,
        "source": f"r/{subreddit}",
        "topic": "reddit",
        "summary": selftext[:500] if selftext else title,
        "full_text": selftext[:20000] if selftext else title,
        "score": score,
        "num_comments": num_comments,
        "scraped_at": datetime.now().isoformat(),
        "hash": url_hash(post_url),
        "discovery_depth": 0,
        "source_type": "reddit",
        "subreddit": subreddit,
        "thread_title": title,
        "thread_score": score,
        "thread_permalink": post_url,
        "op_author": f"u/{op_author}" if op_author and not op_author.startswith("u/") else (op_author or "u/unknown"),
        "op_body": selftext[:600],
        "reddit_callouts": [],
        "evidence_info": {},
    }
    ctx.results.append(record)
    print(f"  [POST {score}↑ {num_comments}c] {title[:70]}")

    aggregate_text = selftext + "\n" + (post_data.get("url_overridden_by_dest", "") or "")
    comments_payload = _load_post_comments_json(ctx, permalink) if permalink else None
    if comments_payload:
        record["reddit_callouts"] = _extract_top_callouts(comments_payload, max_callouts=4)
        for body in _extract_top_comment_texts(comments_payload):
            aggregate_text += "\n" + body

    outbound = extract_outbound_links(
        aggregate_text, post_url,
        allowlist=ctx.allowlist,
        blocklist=ctx.blocklist,
        max_links=ctx.max_outbound,
    )
    for link in outbound:
        _process_outbound(ctx, link, depth=1, parent=record)


def scrape_reddit(
    fixture_dir: Path | None = None,
    depth_override: int | None = None,
    per_sub_limit: int | None = None,
) -> list[dict]:
    cfg = load_reddit_config()
    settings = cfg["settings"]

    session = create_session()
    ua = settings.get("user_agent", DEFAULT_UA)
    session.headers["User-Agent"] = ua

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    visited = VisitedSet(VISITED_PATH)

    respect_robots = bool(settings.get("respect_robots_txt", True))
    robots = RobotsCache(session, ua, fail_closed=False) if fixture_dir is None else None

    ctx = ScrapeContext(
        session=session,
        visited=visited,
        allowlist=cfg.get("outbound_link_allowlist", []),
        blocklist=cfg.get("outbound_link_blocklist", []),
        max_outbound=settings.get("max_outbound_links_per_post", 5),
        delay=float(settings.get("request_delay_seconds", 3)),
        recursion_depth=depth_override if depth_override is not None else int(settings.get("recursion_depth", 2)),
        robots=robots,
        respect_robots=respect_robots,
        fixture_dir=fixture_dir,
    )

    print(f"\n{'='*60}")
    print(f"  REDDIT SCRAPER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Subs: {len(cfg['subreddits'])} | depth: {ctx.recursion_depth}")
    print(f"  Mode: {'FIXTURE' if fixture_dir else 'LIVE'}")
    print(f"{'='*60}\n")

    min_score = settings.get("min_score", 25)
    min_comments = settings.get("min_comments", 10)
    max_posts = per_sub_limit or settings.get("max_posts_per_subreddit", 10)

    for sub_cfg in cfg["subreddits"]:
        name = sub_cfg["name"]
        listing = sub_cfg.get("listing", "top")
        window = sub_cfg.get("window", "week")
        print(f"[SUB] r/{name} ({listing}/{window})")

        payload = _load_subreddit_json(ctx, name, listing, window)
        if not payload:
            continue

        children = payload.get("data", {}).get("children", [])[:max_posts]
        print(f"  found {len(children)} listing entries")

        for child in children:
            post_data = child.get("data", {})
            if post_data.get("stickied"):
                continue
            _process_post(ctx, post_data, name, min_score, min_comments)

        print()

    visited.save()

    if ctx.results and fixture_dir is None:
        raw_dir = POSTS_DIR / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = raw_dir / f"reddit_{ts}.json"
        out.write_text(json.dumps(ctx.results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[SAVED] {len(ctx.results)} records → {out}")

        try:
            from source_promoter import promote_records
            reddit_records = [r for r in ctx.results if r.get("source_type") == "reddit"]
            summary = promote_records(reddit_records)
            print(f"[PROMOTE] {summary['created']} created, "
                  f"{summary['updated']} updated, {summary['skipped']} skipped")
        except Exception as e:
            print(f"[PROMOTE] promotion step failed (non-fatal): {e}")
    else:
        print(f"[INFO] {len(ctx.results)} records (not saved — fixture or empty)")

    return ctx.results


def main():
    parser = argparse.ArgumentParser(description="Recursive Reddit scraper")
    parser.add_argument("--fixture-dir", type=Path, default=None,
                        help="Read from local fixtures instead of live HTTP (for CI smoke tests)")
    parser.add_argument("--depth", type=int, default=None,
                        help="Override recursion depth (default from config)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Override max posts per subreddit")
    args = parser.parse_args()
    results = scrape_reddit(
        fixture_dir=args.fixture_dir,
        depth_override=args.depth,
        per_sub_limit=args.limit,
    )
    sys.exit(0 if results is not None else 1)


if __name__ == "__main__":
    main()
