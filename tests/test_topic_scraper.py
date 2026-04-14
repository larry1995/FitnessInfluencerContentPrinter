"""Unit tests for the on-demand topic scraper (task #43).

v1 is PubMed-only by design — see task #42 scope for the reasoning. These
tests monkeypatch ``pubmed_scraper.search_pubmed`` and ``fetch_article_details``
so no network I/O happens. The live smoke test against real PubMed lives in
task #45.
"""

import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))


def _make_pm_article(pmid: str, *, title: str = "Test Article") -> dict:
    """Shape that ``pubmed_scraper.fetch_article_details`` returns (see the
    parse_pubmed_xml return statement in src/pubmed_scraper.py)."""
    return {
        "pmid": pmid,
        "title": title,
        "authors": ["Smith J", "Doe A"],
        "journal": "J Strength Cond Res",
        "year": "2024",
        "doi": f"10.1519/JSC.{pmid}",
        "abstract": (
            "Background: This study examined creatine supplementation. "
            "Methods: RCT with 30 trained lifters. Results: +5kg 1RM gain."
        ),
        "mesh_terms": ["Creatine", "Resistance Training"],
    }


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Skip the NCBI rate-limit sleep so unit tests stay fast."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)


def test_scrape_for_topic_returns_canonical_article_shape(monkeypatch):
    """Happy path: mocked PubMed returns 3 records, we ask for 3, get 3."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic

    pmids = ["40000001", "40000002", "40000003"]
    monkeypatch.setattr(
        pubmed_scraper, "search_pubmed", lambda query, max_results=20: pmids
    )
    monkeypatch.setattr(
        pubmed_scraper,
        "fetch_article_details",
        lambda ids: [_make_pm_article(p) for p in ids],
    )

    results = scrape_for_topic("creatine supplementation", max_sources=3)

    assert len(results) == 3
    for r in results:
        # Canonical shape consumed by grounded_drafter._structured_to_citation.
        assert r["source_type"] == "pubmed"
        assert r["title"]
        assert r["url"].startswith("https://pubmed.ncbi.nlm.nih.gov/")
        sc = r["structured_content"]
        assert sc["pmid"]
        assert sc["doi"].startswith("10.")
        assert sc["authors"]
        assert sc["year"] == "2024"
        assert sc["journal"]
        assert r["full_text"]
        assert r["summary"]
        assert r["hash"]


def test_scrape_for_topic_slices_to_max_sources(monkeypatch):
    """Overfetch is invisible to callers — return exactly max_sources."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic

    pmids = [f"4000{i:04d}" for i in range(20)]
    monkeypatch.setattr(
        pubmed_scraper, "search_pubmed", lambda query, max_results=20: pmids[:max_results]
    )
    monkeypatch.setattr(
        pubmed_scraper,
        "fetch_article_details",
        lambda ids: [_make_pm_article(p) for p in ids],
    )

    results = scrape_for_topic("test", max_sources=5)
    assert len(results) == 5


def test_scrape_for_topic_empty_esearch_returns_empty_list(monkeypatch):
    """Zero results is not an error — return [] so caller can fail fast."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic

    monkeypatch.setattr(pubmed_scraper, "search_pubmed", lambda query, max_results=20: [])
    # fetch_article_details should NOT be called — assert it via a sentinel.
    def _should_not_be_called(_ids):
        raise AssertionError("fetch_article_details called despite empty PMID list")
    monkeypatch.setattr(pubmed_scraper, "fetch_article_details", _should_not_be_called)

    results = scrape_for_topic("obscure topic with no results", max_sources=5)
    assert results == []


def test_scrape_for_topic_partial_results_ok(monkeypatch):
    """If efetch returns fewer records than requested, return the partial list."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic

    monkeypatch.setattr(
        pubmed_scraper, "search_pubmed", lambda query, max_results=20: ["1", "2", "3", "4", "5"]
    )
    # Simulate 2/5 records failing to parse (e.g. missing title).
    monkeypatch.setattr(
        pubmed_scraper,
        "fetch_article_details",
        lambda ids: [_make_pm_article(p) for p in ids[:3]],
    )

    results = scrape_for_topic("creatine", max_sources=5)
    assert len(results) == 3


def test_scrape_for_topic_drops_records_without_title(monkeypatch):
    """Records that survive efetch but have empty titles are not Article-shaped."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic

    monkeypatch.setattr(
        pubmed_scraper, "search_pubmed", lambda query, max_results=20: ["1", "2", "3"]
    )

    def _fetch(ids):
        out = []
        for i, pmid in enumerate(ids):
            art = _make_pm_article(pmid)
            if i == 1:
                art["title"] = ""  # Corrupt one record.
            out.append(art)
        return out

    monkeypatch.setattr(pubmed_scraper, "fetch_article_details", _fetch)

    results = scrape_for_topic("test", max_sources=3)
    assert len(results) == 2  # One dropped.
    assert all(r["title"] for r in results)


def test_scrape_for_topic_dedupes_by_pmid(monkeypatch):
    """Duplicate PMIDs in efetch output should be deduped in the returned list."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic

    monkeypatch.setattr(
        pubmed_scraper, "search_pubmed", lambda query, max_results=20: ["1", "2", "1", "3"]
    )
    monkeypatch.setattr(
        pubmed_scraper,
        "fetch_article_details",
        lambda ids: [_make_pm_article(p) for p in ids],
    )

    results = scrape_for_topic("test", max_sources=10)
    pmids = [r["structured_content"]["pmid"] for r in results]
    assert len(pmids) == len(set(pmids))
    assert set(pmids) == {"1", "2", "3"}


def test_scrape_for_topic_esearch_network_failure_raises(monkeypatch):
    """Network errors should raise TopicScraperError, not return []."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic, TopicScraperError

    def _boom(*args, **kwargs):
        raise ConnectionError("NCBI is down")

    monkeypatch.setattr(pubmed_scraper, "search_pubmed", _boom)

    with pytest.raises(TopicScraperError) as exc_info:
        scrape_for_topic("creatine", max_sources=5)
    assert "esearch" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ConnectionError)


def test_scrape_for_topic_efetch_network_failure_raises(monkeypatch):
    """An efetch failure after a successful esearch is still a TopicScraperError."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic, TopicScraperError

    monkeypatch.setattr(
        pubmed_scraper, "search_pubmed", lambda query, max_results=20: ["1", "2"]
    )

    def _boom(_ids):
        raise TimeoutError("PubMed efetch timed out")

    monkeypatch.setattr(pubmed_scraper, "fetch_article_details", _boom)

    with pytest.raises(TopicScraperError) as exc_info:
        scrape_for_topic("creatine", max_sources=5)
    assert "efetch" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, TimeoutError)


def test_scrape_for_topic_rejects_empty_topic():
    from contentprinter import scrape_for_topic

    for bad in ("", "   ", "\n\t"):
        with pytest.raises(ValueError, match="non-empty string"):
            scrape_for_topic(bad, max_sources=5)


def test_scrape_for_topic_rejects_non_string_topic():
    from contentprinter import scrape_for_topic

    for bad in (None, 42, ["creatine"]):
        with pytest.raises(ValueError, match="non-empty string"):
            scrape_for_topic(bad, max_sources=5)  # type: ignore[arg-type]


def test_scrape_for_topic_rejects_non_positive_max_sources(monkeypatch):
    from contentprinter import scrape_for_topic

    for bad in (0, -1, 1.5, "5"):
        with pytest.raises(ValueError, match="positive int"):
            scrape_for_topic("creatine", max_sources=bad)  # type: ignore[arg-type]


def test_scrape_for_topic_category_is_metadata_only(monkeypatch):
    """category stamps into the 'topic' field but is not used as a search filter."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic

    captured_query: list[str] = []

    def _search(query, max_results=20):
        captured_query.append(query)
        return ["1"]

    monkeypatch.setattr(pubmed_scraper, "search_pubmed", _search)
    monkeypatch.setattr(
        pubmed_scraper, "fetch_article_details", lambda ids: [_make_pm_article(ids[0])]
    )

    results = scrape_for_topic("creatine", category="supplements", max_sources=1)
    assert len(results) == 1
    assert results[0]["topic"] == "supplements"
    # Query string passed to NCBI is unchanged by category.
    assert captured_query == ["creatine"]


def test_scrape_for_topic_default_topic_label_when_no_category(monkeypatch):
    """When category is None, the stamped topic falls back to 'training'."""
    import pubmed_scraper
    from contentprinter import scrape_for_topic

    monkeypatch.setattr(pubmed_scraper, "search_pubmed", lambda query, max_results=20: ["1"])
    monkeypatch.setattr(
        pubmed_scraper, "fetch_article_details", lambda ids: [_make_pm_article(ids[0])]
    )

    results = scrape_for_topic("creatine", max_sources=1)
    assert results[0]["topic"] == "training"


# ── Regression: existing batch pipeline still works ─────────────────────────


def test_pubmed_scraper_build_entry_from_article_matches_legacy_shape():
    """The extracted helper must produce the same dict shape the old inline
    loop produced. If this test breaks, the grounded drafter's allow-list
    construction will silently break too — the shape is load-bearing."""
    import pubmed_scraper

    art = _make_pm_article("12345")
    entry = pubmed_scraper.build_entry_from_article(art, "nutrition")

    assert entry["title"] == "Test Article"
    assert entry["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert entry["source"] == "PubMed (J Strength Cond Res)"
    assert entry["source_type"] == "pubmed"
    assert entry["topic"] == "nutrition"
    assert entry["summary"].startswith("Background:")
    assert len(entry["summary"]) <= 500
    assert entry["full_text"].startswith("Background:")
    sc = entry["structured_content"]
    assert sc["pmid"] == "12345"
    assert sc["doi"] == "10.1519/JSC.12345"
    assert sc["authors"] == ["Smith J", "Doe A"]
    assert sc["year"] == "2024"
    assert sc["journal"] == "J Strength Cond Res"
    assert sc["mesh_terms"] == ["Creatine", "Resistance Training"]
    assert entry["scraped_at"]
    assert len(entry["hash"]) == 12


def test_pubmed_scraper_build_entry_handles_missing_journal():
    """Articles without a journal field still get a sensible source string."""
    import pubmed_scraper

    art = _make_pm_article("99999")
    art["journal"] = ""
    entry = pubmed_scraper.build_entry_from_article(art, "training")
    assert entry["source"] == "PubMed"
