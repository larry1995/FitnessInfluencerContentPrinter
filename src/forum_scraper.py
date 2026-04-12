"""
Strength-sport forum scraper for ContentPrinter.

Iterates the forums listed in config/forum_sources.json (disabled by default
until each forum's robots.txt and landing-page structure has been verified by
the researcher). For each enabled forum, fetches a thread index page, follows
up to N threads, and recursively expands outbound article links (depth 2).

This module is deliberately thin — the forum-specific DOM walking is handled
per-platform (Discourse, vBulletin) via small extractor functions. The
recursive link-expansion + visited-set + robots handling comes from
src/recursive_discovery.py.

Run:
    python src/forum_scraper.py
    python src/forum_scraper.py --fixture-dir tests/fixtures
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

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
POSTS_DIR = PROJECT_ROOT / "Posts"

VISITED_PATH = POSTS_DIR / ".seen_forum_hashes.json"
DEFAULT_UA = "ContentPrinter/1.0 (+https://centralstrengthgyms.com)"


@dataclass
class ForumCtx:
    session: object
    visited: VisitedSet
    robots: RobotsCache
    delay: float
    max_threads: int
    max_outbound: int
    recursion_depth: int
    respect_robots: bool
    fixture_dir: Path | None = None
    results: list[dict] = field(default_factory=list)


def load_forum_config() -> dict:
    with open(CONFIG_DIR / "forum_sources.json", encoding="utf-8") as f:
        return json.load(f)


def _fetch_html(ctx: ForumCtx, url: str) -> str:
    if ctx.fixture_dir is not None:
        import hashlib
        h = hashlib.sha1(normalize_url(url).encode()).hexdigest()[:16]
        fp = ctx.fixture_dir / "html" / f"{h}.html"
        if fp.exists():
            return fp.read_text(encoding="utf-8")
        return ""
    if ctx.respect_robots and not ctx.robots.can_fetch(url):
        print(f"  [ROBOTS] disallowed: {url}")
        return ""
    polite_sleep(ctx.delay)
    try:
        resp = http_get(ctx.session, url)
        return resp.text
    except Exception as e:
        print(f"  [WARN] fetch failed: {url} ({e})")
        return ""


def _discourse_latest_threads(ctx: ForumCtx, base_url: str) -> list[str]:
    """Discourse forums expose /latest.json — parse and return absolute topic URLs."""
    latest_url = urljoin(base_url.rstrip("/") + "/", "latest.json")
    if ctx.fixture_dir is not None:
        import hashlib
        h = hashlib.sha1(normalize_url(latest_url).encode()).hexdigest()[:16]
        fp = ctx.fixture_dir / "html" / f"{h}.html"
        if not fp.exists():
            return []
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    else:
        if ctx.respect_robots and not ctx.robots.can_fetch(latest_url):
            return []
        polite_sleep(ctx.delay)
        try:
            resp = http_get(ctx.session, latest_url)
            data = resp.json()
        except Exception:
            return []

    urls: list[str] = []
    for topic in data.get("topic_list", {}).get("topics", [])[: ctx.max_threads]:
        slug = topic.get("slug", "")
        tid = topic.get("id")
        if slug and tid:
            urls.append(urljoin(base_url.rstrip("/") + "/", f"t/{slug}/{tid}"))
    return urls


def _vbulletin_thread_links(ctx: ForumCtx, index_url: str) -> list[str]:
    """Generic vBulletin-ish scraper: pull the first N <a class='title'> or thread-like anchors."""
    html = _fetch_html(ctx, index_url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.select("a.title, a.threadtitle, a[href*='showthread']"):
        href = a.get("href", "")
        if not href:
            continue
        urls.append(urljoin(index_url, href))
        if len(urls) >= ctx.max_threads:
            break
    return urls


def _thread_to_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    main = soup.find("article") or soup.find("main") or soup
    text = main.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return title, "\n".join(lines)


def _process_outbound(ctx: ForumCtx, link: str, depth: int, parent: dict, allow: list[str], block: list[str]) -> None:
    if depth > ctx.recursion_depth:
        return
    if not ctx.visited.add(link):
        return
    html = _fetch_html(ctx, link)
    if not html:
        return
    title, text = _thread_to_text(html)
    if len(text) < 200:
        return
    record = {
        "title": title or link,
        "url": link,
        "source": f"outbound-from-{parent.get('source', 'forum')}",
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
        for nl in extract_outbound_links(html, link, allow, block, ctx.max_outbound):
            _process_outbound(ctx, nl, depth + 1, record, allow, block)


def scrape_forums(fixture_dir: Path | None = None) -> list[dict]:
    cfg = load_forum_config()
    settings = cfg["settings"]

    session = create_session()
    session.headers["User-Agent"] = DEFAULT_UA

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    visited = VisitedSet(VISITED_PATH)
    robots = RobotsCache(session, DEFAULT_UA, fail_closed=False)

    ctx = ForumCtx(
        session=session,
        visited=visited,
        robots=robots,
        delay=float(settings.get("request_delay_seconds", 3)),
        max_threads=int(settings.get("max_threads_per_forum", 10)),
        max_outbound=int(settings.get("max_outbound_links_per_thread", 5)),
        recursion_depth=int(settings.get("recursion_depth", 2)),
        respect_robots=bool(settings.get("respect_robots_txt", True)),
        fixture_dir=fixture_dir,
    )

    print(f"\n{'='*60}")
    print(f"  FORUM SCRAPER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Forums configured: {len(cfg['forums'])} (enabled: {sum(1 for f in cfg['forums'] if f.get('enabled'))})")
    print(f"  Mode: {'FIXTURE' if fixture_dir else 'LIVE'}")
    print(f"{'='*60}\n")

    allow: list[str] = cfg.get("outbound_link_allowlist", [])
    block: list[str] = cfg.get("outbound_link_blocklist", [])

    for forum in cfg["forums"]:
        name = forum["name"]
        if not forum.get("enabled"):
            print(f"[SKIP] {name} (disabled in config)")
            continue

        print(f"[FORUM] {name}")
        platform = forum.get("platform", "").lower()
        base = forum["base_url"]
        index = forum.get("thread_index_url", base)

        if platform == "discourse":
            thread_urls = _discourse_latest_threads(ctx, base)
        else:
            thread_urls = _vbulletin_thread_links(ctx, index)

        print(f"  discovered {len(thread_urls)} thread(s)")
        for turl in thread_urls:
            if not visited.add(turl):
                continue
            html = _fetch_html(ctx, turl)
            if not html:
                continue
            title, text = _thread_to_text(html)
            if len(text) < 200:
                continue
            record = {
                "title": title or turl,
                "url": turl,
                "source": name,
                "topic": "forum",
                "summary": text[:500],
                "full_text": text[:20000],
                "scraped_at": datetime.now().isoformat(),
                "hash": url_hash(turl),
                "discovery_depth": 0,
                "source_type": "forum",
            }
            ctx.results.append(record)
            print(f"  [THREAD] {title[:70]}")
            for link in extract_outbound_links(html, turl, allow, block, ctx.max_outbound):
                _process_outbound(ctx, link, 1, record, allow, block)

        print()

    visited.save()

    if ctx.results and fixture_dir is None:
        raw_dir = POSTS_DIR / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = raw_dir / f"forum_{ts}.json"
        out.write_text(json.dumps(ctx.results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[SAVED] {len(ctx.results)} records → {out}")

        try:
            from source_promoter import promote_records
            forum_records = [r for r in ctx.results if r.get("source_type") == "forum"]
            summary = promote_records(forum_records)
            print(f"[PROMOTE] {summary['created']} created, "
                  f"{summary['updated']} updated, {summary['skipped']} skipped")
        except Exception as e:
            print(f"[PROMOTE] promotion step failed (non-fatal): {e}")
    else:
        print(f"[INFO] {len(ctx.results)} records (not saved — fixture, empty, or all forums disabled)")

    return ctx.results


def main():
    parser = argparse.ArgumentParser(description="Recursive forum scraper")
    parser.add_argument("--fixture-dir", type=Path, default=None)
    args = parser.parse_args()
    scrape_forums(fixture_dir=args.fixture_dir)


if __name__ == "__main__":
    main()
