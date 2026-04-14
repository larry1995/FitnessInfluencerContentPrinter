"""On-demand topic-driven scraper for the ContentPrinter library.

Existing scrapers in ``src/*_scraper.py`` are batch entry points that walk
config files (``config/sources.json``, ``config/reddit_sources.json``, etc.)
and produce ``work/raw/*.json`` dumps. That shape doesn't fit an on-demand
request handler that needs to say "give me N articles about creatine
supplementation, now."

This module exposes a single public function, ``scrape_for_topic``, that
takes a free-text topic and returns a list of canonical Article dicts
consumable by ``contentprinter.generate_grounded_draft``. v1 is PubMed-only
by design — only PubMed yields ``structured_content`` with DOI/PMID/authors/
year, which is the only path that gives the grounded drafter a non-empty
allow-list deterministically. bioRxiv/RSS/YouTube/Reddit handlers are
deferred because they don't produce citable structured content; adding them
would just push more jobs into ``INSUFFICIENT_SOURCE_DATA`` without
improving drafter output. See task #42 scope message for the full trade-off.

F-0 interaction: this module does NOT call ``verify_citations`` on the
sources it returns. Verification happens at the drafter allow-list layer
(``grounded_drafter.extract_allowed_citations``), which is the single
chokepoint for what gets cited. A topic query that yields PubMed records
with unverifiable DOIs will produce an empty allow-list downstream and the
job will drop to ``INSUFFICIENT_SOURCE_DATA`` cleanly.
"""

from __future__ import annotations

import time
from typing import Any

import pubmed_scraper as _pm

__all__ = ["scrape_for_topic", "TopicScraperError"]


class TopicScraperError(RuntimeError):
    """Raised when a topic query itself fails (network down, upstream 5xx).

    NOT raised on zero results — ``scrape_for_topic`` returns ``[]`` in that
    case so the caller can land a job in a deterministic ``failed`` state
    with a useful message rather than catching an exception.
    """


def scrape_for_topic(
    topic: str,
    *,
    category: str | None = None,
    max_sources: int = 5,
    languages: list[str] | None = None,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    """Return up to ``max_sources`` Article dicts for an on-demand topic query.

    Shape of the returned dicts matches what
    ``contentprinter.generate_grounded_draft`` consumes; see
    ``src/pubmed_scraper.build_entry_from_article`` for the canonical
    definition. Fields include ``title``, ``url``, ``source``,
    ``source_type="pubmed"``, ``topic``, ``summary``, ``full_text``,
    ``structured_content`` (with ``pmid``, ``doi``, ``authors``, ``year``,
    ``journal``, ``mesh_terms``), ``scraped_at``, and ``hash``.

    Args:
        topic: Free-text search query. Passed verbatim to NCBI's esearch.
        category: Accepted for caller record-keeping. Not used as a search
            filter in v1 — PubMed relevance ranking is good enough and
            wiring category→query-prefix is premature until we see real
            usage data. Stamped into each returned dict's ``topic`` field.
        max_sources: Upper bound on returned articles. Overfetched 2x at
            the esearch layer to leave room for efetch parse failures,
            then sliced to exactly ``max_sources``.
        languages: Reserved for future use. Ignored in v1.
        timeout_seconds: Per-request network timeout. Currently advisory —
            the underlying ``http_utils`` session uses its own default.

    Returns:
        A list of Article dicts, length ≤ ``max_sources``. Empty list on
        zero results (not an error).

    Raises:
        ValueError: if ``topic`` is empty or not a string, or
            ``max_sources`` is not a positive int.
        TopicScraperError: if the PubMed esearch or efetch call fails
            (network down, NCBI 5xx, etc.). The ``__cause__`` of the raised
            exception is the original transport error.

    Side effects: Two outbound HTTPS requests to eutils.ncbi.nlm.nih.gov per
    call (one esearch, one efetch), with a 1-second rate-limit sleep between
    them per NCBI's unauthenticated request guidance. No disk writes.
    """
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("topic must be a non-empty string")
    if not isinstance(max_sources, int) or max_sources <= 0:
        raise ValueError("max_sources must be a positive int")

    topic_label = category or "training"
    # Overfetch 2x so that efetch parse failures or missing titles still
    # leave us with enough records to slice down to max_sources.
    fetch_count = max(max_sources * 2, max_sources + 2)

    try:
        pmids = _pm.search_pubmed(topic, max_results=fetch_count)
    except Exception as e:
        raise TopicScraperError(f"PubMed esearch failed for {topic!r}: {e}") from e

    if not pmids:
        return []

    time.sleep(1)  # NCBI rate limit for unauthenticated clients

    try:
        articles = _pm.fetch_article_details(pmids)
    except Exception as e:
        raise TopicScraperError(f"PubMed efetch failed for {topic!r}: {e}") from e

    entries: list[dict[str, Any]] = []
    seen_pmids: set[str] = set()
    for article in articles:
        pmid = article.get("pmid")
        if not pmid or pmid in seen_pmids:
            continue
        if not article.get("title"):
            continue
        seen_pmids.add(pmid)
        entries.append(_pm.build_entry_from_article(article, topic_label))
        if len(entries) >= max_sources:
            break

    return entries
