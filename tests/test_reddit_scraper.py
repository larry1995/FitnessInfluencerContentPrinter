"""Fixture-based smoke test for the Reddit recursive scraper."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VISITED_FILE = Path(__file__).resolve().parent.parent / "work" / ".seen_reddit_hashes.json"


def _reset_visited():
    if VISITED_FILE.exists():
        VISITED_FILE.unlink()


def test_reddit_scraper_recursive_discovery():
    _reset_visited()
    import reddit_scraper

    results = reddit_scraper.scrape_reddit(
        fixture_dir=FIXTURES,
        depth_override=2,
    )

    # Top post (420↑, 137c) passes threshold; low-score and stickied are filtered.
    by_source = {r["source"] for r in results}
    assert "r/powerlifting" in by_source, "top reddit post missing"

    reddit_records = [r for r in results if r["source_type"] == "reddit"]
    assert len(reddit_records) == 1, f"expected 1 reddit post, got {len(reddit_records)}"
    assert reddit_records[0]["score"] == 420

    outbound = [r for r in results if r["source_type"] == "outbound"]
    depths = sorted(r["discovery_depth"] for r in outbound)
    assert 1 in depths, "no depth-1 outbound discovery"
    assert 2 in depths, "no depth-2 outbound discovery (cycle guard over-strict?)"

    _reset_visited()


def test_reddit_scraper_cycle_guard():
    """Second scrape pass should surface 0 records — visited set prevents cycles."""
    _reset_visited()
    import reddit_scraper

    first = reddit_scraper.scrape_reddit(fixture_dir=FIXTURES, depth_override=2)
    second = reddit_scraper.scrape_reddit(fixture_dir=FIXTURES, depth_override=2)

    assert len(first) > 0
    assert len(second) == 0, f"cycle guard failed — second pass returned {len(second)} records"

    _reset_visited()


def test_recursive_discovery_helpers():
    from recursive_discovery import extract_outbound_links, normalize_url, url_hash

    assert normalize_url("HTTPS://Example.COM/foo/#frag") == "https://example.com/foo"
    assert url_hash("https://example.com/a") == url_hash("https://example.com/a/")

    links = extract_outbound_links(
        '<a href="https://strongerbyscience.com/x">sbs</a> '
        '<a href="https://reddit.com/spam">r</a> '
        '<a href="https://example.com/y">ok</a>',
        base_url="https://old.reddit.com/r/x/",
        allowlist=["strongerbyscience.com", "example.com"],
        blocklist=["reddit.com"],
        max_links=5,
    )
    assert any("strongerbyscience.com" in l for l in links)
    assert any("example.com" in l for l in links)
    assert not any("reddit.com" in l for l in links)
