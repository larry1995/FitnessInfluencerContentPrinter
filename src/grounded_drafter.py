"""Grounded LLM drafter — produces draft.txt files whose REFERENCES blocks
contain ONLY citations extractable from the scraped source article.

Background: on 2026-04-12 researcher's #21 audit caught an earlier
ungrounded polish workflow that had produced 38% hallucinated citations
across 31 posts (the offending code path has since been removed). Root
cause (#30 investigation): the LLM was given a draft caption + the
editorial spec mandating "2-5 DOI-bearing citations" but never the actual
source article's citation metadata, so it confabulated from training memory.

This module is Layer 1 of the three-layer fix (Layer 2 = `verify_citations`,
Layer 3 = `audit_meta_writer`). It builds an explicit allow-list of verified
citations from the scraped article, passes them to the LLM as a hard
constraint ("you may only cite from this list"), and rejects any LLM output
that contains a non-allow-listed citation. Layer A check is a fast local
byte-comparison; Layer B is a full `verify_citations` defense-in-depth pass.

Design doc: `audits/grounded_drafter_design.md` (v2 APPROVED 2026-04-12).
The implementation deliberately does not deviate from the design doc — any
changes must surface in code review against the doc, not silently in code.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

import llm_client

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize
NEEDS_RESEARCH_DIR = POSTS_DIR / ".needs_research"

# Hoist `_citation_audit` import to module scope (same pattern as
# `contentprinter/verify.py`). The audit module lives in `audits/`, not
# `src/`, so it's not on sys.path by default. We add the directory once
# at import time and never mutate sys.path again — previously the byte-
# check did this on every retry inside a hot loop, which was wasted
# cycles AND a sys.path mutation footgun for any test that imports
# grounded_drafter and then expects a clean sys.path on the way out.
_AUDITS_DIR = PROJECT_ROOT / "audits"
if _AUDITS_DIR.is_dir() and str(_AUDITS_DIR) not in sys.path:
    sys.path.insert(0, str(_AUDITS_DIR))
import _citation_audit as _ca  # noqa: E402

PROMPT_TEMPLATE_PATH = CONFIG_DIR / "grounded_drafter_prompt.md"

DEFAULT_TEMPERATURE = 0.5
RETRY_TEMPERATURE = 0.3
MAX_BODY_CHARS = 4000
MAX_ALLOWED_CITATIONS = 8

INSUFFICIENT_MARKER = "[INSUFFICIENT_SOURCE_DATA]"

# Inline citation regex patterns. Regex is intentionally lenient — false
# negatives shorten the allow-list (a real citation is missed); false
# positives are caught by the per-candidate verify_citations call below.
# DOIs can contain `.` (e.g. "10.1519/JSC.0000000000002491"), so the body
# class must keep `.` as a valid char. Trailing punctuation is stripped
# in post-processing instead of via the boundary lookahead.
_INLINE_DOI = re.compile(
    r"(?:doi[:\s]*|doi\.org/|dx\.doi\.org/)(10\.\d{4,9}/[^\s)\]]+)",
    re.IGNORECASE,
)
_INLINE_PMID = re.compile(r"PMID[:\s]+(\d{5,9})", re.IGNORECASE)


class Citation(TypedDict, total=False):
    citation_text: str
    doi: str | None
    pmid: str | None
    first_author: str
    year: int
    journal: str | None
    title: str
    source: str  # "pubmed_scraper" | "rss_inline_doi" | "rss_inline_pmid"


# ── Allow-list extraction ─────────────────────────────────────────────────


def _format_citation_text(
    *,
    first_author: str,
    year: int,
    title: str,
    journal: str | None,
    doi: str | None,
    pmid: str | None,
) -> str:
    """Format a Citation record into the canonical REFERENCES line.

    The shape matches what `audits/_citation_audit.py::parse_refs_block`
    expects to round-trip cleanly: `Author et al. (Year). Title. Journal. doi:X PMID:Y`
    """
    pieces = [f"{first_author} et al. ({year}). {title}."]
    if journal:
        pieces.append(f"{journal}.")
    if doi:
        pieces.append(f"doi:{doi}")
    if pmid:
        pieces.append(f"PMID:{pmid}")
    return " ".join(pieces)


def _structured_to_citation(article: dict[str, Any]) -> Citation | None:
    """Source 1: build a Citation from PubMed-sourced structured_content."""
    structured = article.get("structured_content") or {}
    if not isinstance(structured, dict):
        return None
    pmid = structured.get("pmid")
    doi = structured.get("doi")
    if not (pmid or doi):
        return None
    authors = structured.get("authors") or []
    if not authors:
        return None
    first_author = authors[0] if isinstance(authors[0], str) else str(authors[0])
    year_raw = structured.get("year")
    try:
        year = int(year_raw) if year_raw else None
    except (ValueError, TypeError):
        year = None
    title = article.get("title")
    journal = structured.get("journal")
    if not (first_author and year and title):
        return None
    return {
        "citation_text": _format_citation_text(
            first_author=first_author,
            year=year,
            title=title,
            journal=journal,
            doi=doi or None,
            pmid=str(pmid) if pmid else None,
        ),
        "doi": doi or None,
        "pmid": str(pmid) if pmid else None,
        "first_author": first_author,
        "year": year,
        "journal": journal,
        "title": title,
        "source": "pubmed_scraper",
    }


def _verify_inline_candidate(
    raw_line: str, verify_fn,
) -> dict[str, Any] | None:
    """Run verify_citations on a synthetic single-ref draft, return the row
    if it came back OK. Returns None for any blocking, soft-flag, or
    unavailable severity — we don't trust author-typed inline DOIs without
    independent verification.

    The `raw_line` we synthesize here uses a placeholder author/year/title
    triplet (e.g. `"Author X et al. (2024). Title. Journal. doi:<DOI>"`)
    that is INTENTIONALLY not the real citation. The audit module's
    classify pass would normally flag the synthetic stub as TITLE_MISMATCH
    because the placeholder title doesn't match what Crossref returns —
    BUT verify_citations does the Crossref lookup BEFORE classify, and the
    fetched record (real author, year, title, journal) is what we actually
    care about. The caller (`extract_allowed_citations` → `_row_to_citation`)
    builds the real Citation record from the row's `fetched` field, never
    from the synthetic stub.

    The reason we use a stub at all (instead of just calling Crossref
    directly): keeping the bootstrap inside `verify_citations` means we
    inherit the network-failure normalization, the soft/hard severity
    classification, and any future audit-module improvements without
    duplicating logic here. This function is essentially "use the audit
    module as a Crossref client with built-in classification".

    DO NOT try to "fix" the placeholder triplet to match the fetched
    paper — it's load-bearing as a placeholder. A test asserting we use
    the fetched fields not the stub fields lives in test_grounded_drafter.
    """
    synthetic = f"REFERENCES:\n1. {raw_line}\n"
    try:
        rows = verify_fn(synthetic)
    except Exception:
        return None
    if not rows:
        return None
    row = rows[0]
    if row.get("severity") != "OK":
        return None
    return row


def _row_to_citation(row: dict[str, Any], *, source: str) -> Citation | None:
    """Convert a verify_citations OK row into a Citation record."""
    fetched = row.get("fetched") or {}
    draft = row.get("draft") or {}
    first_author = fetched.get("first_author") or draft.get("first_author")
    year = fetched.get("year") or draft.get("year")
    title = fetched.get("title") or draft.get("title")
    journal = fetched.get("journal") or draft.get("journal")
    doi = draft.get("doi")
    pmid = fetched.get("pmid") or draft.get("pmid")
    if not (first_author and year and title):
        return None
    try:
        year_int = int(year)
    except (ValueError, TypeError):
        return None
    return {
        "citation_text": _format_citation_text(
            first_author=first_author,
            year=year_int,
            title=title,
            journal=journal,
            doi=doi,
            pmid=str(pmid) if pmid else None,
        ),
        "doi": doi,
        "pmid": str(pmid) if pmid else None,
        "first_author": first_author,
        "year": year_int,
        "journal": journal,
        "title": title,
        "source": source,
    }


def extract_allowed_citations(
    article: dict[str, Any],
    *,
    verify_fn=None,
) -> list[Citation]:
    """Build the allow-list of verified citations from a scraped article.

    Walks three sources in priority order:
      1. `article["structured_content"]` — PubMed-sourced, 100% trustworthy.
      2. Inline DOIs in `article["full_text"]`, verified via Crossref.
      3. Inline PMIDs in `article["full_text"]`, verified via PubMed.

    Dedupes by (doi, pmid) tuple, prefers source 1, caps at
    `MAX_ALLOWED_CITATIONS` entries.

    `verify_fn` is `contentprinter.verify_citations` by default; tests
    inject a stub to avoid network I/O.
    """
    if verify_fn is None:
        from contentprinter.verify import verify_citations as verify_fn

    candidates: list[Citation] = []
    seen_keys: set[tuple[str | None, str | None]] = set()

    structured_cit = _structured_to_citation(article)
    if structured_cit:
        key = (structured_cit.get("doi"), structured_cit.get("pmid"))
        seen_keys.add(key)
        candidates.append(structured_cit)

    full_text = article.get("full_text") or ""
    if isinstance(full_text, str) and full_text:
        for match in _INLINE_DOI.finditer(full_text):
            # Strip trailing sentence/list punctuation that the lenient
            # body class allows in (`.`, `,`, `;`, `)`).
            doi = match.group(1).rstrip(".,;)")
            key = (doi, None)
            if any(doi == c.get("doi") for c in candidates):
                continue
            row = _verify_inline_candidate(f"Author X et al. (2024). Title. Journal. doi:{doi}", verify_fn)
            if not row:
                continue
            cit = _row_to_citation(row, source="rss_inline_doi")
            if not cit:
                continue
            cit_key = (cit.get("doi"), cit.get("pmid"))
            if cit_key in seen_keys:
                continue
            seen_keys.add(cit_key)
            candidates.append(cit)
            if len(candidates) >= MAX_ALLOWED_CITATIONS:
                return candidates

        for match in _INLINE_PMID.finditer(full_text):
            pmid = match.group(1)
            if any(pmid == c.get("pmid") for c in candidates):
                continue
            row = _verify_inline_candidate(f"Author X et al. (2024). Title. Journal. PMID:{pmid}", verify_fn)
            if not row:
                continue
            cit = _row_to_citation(row, source="rss_inline_pmid")
            if not cit:
                continue
            cit_key = (cit.get("doi"), cit.get("pmid"))
            if cit_key in seen_keys:
                continue
            seen_keys.add(cit_key)
            candidates.append(cit)
            if len(candidates) >= MAX_ALLOWED_CITATIONS:
                return candidates

    return candidates


# ── Prompt building ───────────────────────────────────────────────────────


def _excerpt(full_text: str, *, max_chars: int = MAX_BODY_CHARS) -> str:
    """Truncate article body at the nearest paragraph boundary before
    `max_chars`, append a `[...truncated...]` marker. Pseudocode in
    grounded_drafter_design.md §4.4."""
    if not isinstance(full_text, str):
        return ""
    if len(full_text) <= max_chars:
        return full_text
    cut = full_text[:max_chars]
    last_para = cut.rfind("\n\n")
    if last_para > max_chars // 2:
        cut = cut[:last_para]
    return cut.rstrip() + "\n\n[...truncated, see source URL for full article]"


def _load_prompt_template() -> str:
    """Load the prompt body between <<<PROMPT_START>>> / <<<PROMPT_END>>>."""
    text = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    m = re.search(
        r"<<<PROMPT_START>>>\s*\n(.*?)\n\s*<<<PROMPT_END>>>",
        text,
        re.DOTALL,
    )
    if not m:
        raise ValueError(
            f"Prompt template at {PROMPT_TEMPLATE_PATH} is missing the "
            f"<<<PROMPT_START>>> / <<<PROMPT_END>>> markers."
        )
    return m.group(1)


def _format_allowed_block(allowed: list[Citation]) -> str:
    if not allowed:
        return "[NO VERIFIED CITATIONS AVAILABLE FROM THIS SOURCE]"
    lines = []
    for i, cit in enumerate(allowed, 1):
        lines.append(f"{i}. {cit['citation_text']}")
    return "\n".join(lines)


def _format_references_instruction(allowed: list[Citation]) -> str:
    if not allowed:
        return INSUFFICIENT_MARKER
    return (
        "Use the citations from the verified list above, in the order they "
        "support claims in the body. Number them 1, 2, 3, ... and copy each "
        "citation verbatim from the list above. Do not modify any character."
    )


def build_grounded_prompt(
    article: dict[str, Any],
    allowed: list[Citation],
) -> str:
    """Substitute the prompt template with article + allow-list values."""
    template = _load_prompt_template()
    body = _excerpt(article.get("full_text") or "")
    return (
        template
        .replace("{allowed_citations_block}", _format_allowed_block(allowed))
        .replace("{article_title}", article.get("title") or "")
        .replace("{article_source}", article.get("source") or "")
        .replace("{article_url}", article.get("url") or article.get("source_url") or "")
        .replace("{article_body_excerpt}", body)
        .replace("{references_block_instruction}", _format_references_instruction(allowed))
    )


# ── Layer A byte-check ────────────────────────────────────────────────────


def _all_refs_in_allowlist(draft_text: str, allowed: list[Citation]) -> bool:
    """Fast local check: every REFERENCES entry in `draft_text` must be
    byte-equivalent (after .strip()) to one of the allow-list entries.

    Uses the module-level `_ca` import (`_citation_audit`) hoisted at
    grounded_drafter load time — see the import block at the top of this
    module. Each call is now a bare function dispatch with no sys.path
    mutation, even on retry-loop hot paths.
    """
    refs = _ca.parse_refs_block(draft_text)
    if not refs:
        return True
    allowed_texts = {c["citation_text"].strip() for c in allowed}
    for _idx, raw in refs:
        if raw.strip() not in allowed_texts:
            return False
    return True


# ── needs-research signal file ────────────────────────────────────────────


def _write_needs_research_signal(
    article: dict[str, Any],
    *,
    slug: str,
    extraction_breakdown: dict[str, Any],
) -> None:
    """Emit `work/.needs_research/<slug>.json` for operational triage."""
    NEEDS_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "slug": slug,
        "source_url": article.get("url") or article.get("source_url") or "",
        "source_type": article.get("source_type") or "",
        "article_title": article.get("title") or "",
        "extracted_refs_attempted": extraction_breakdown.get("total_attempted", 0),
        "extraction_breakdown": extraction_breakdown,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (NEEDS_RESEARCH_DIR / f"{slug}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Main entry point ──────────────────────────────────────────────────────


def generate_grounded_draft(
    article: dict[str, Any],
    *,
    max_retries: int = 1,
    verify_fn=None,
    llm_complete=None,
    llm_is_configured=None,
    slug: str | None = None,
) -> str | None:
    """Produce a draft.txt body whose citations are grounded in the source.

    Returns the draft text on success. Returns `None` and emits a log line
    + signal file when:
      - the source article has zero extractable citations (INSUFFICIENT_SOURCE_DATA),
      - the LLM is not configured (no ANTHROPIC_API_KEY),
      - all retries failed allow-list or verify_citations checks (DROP).

    The caller is responsible for writing the returned text to disk and
    updating meta.json. This function does not touch the filesystem
    except to write the `.needs_research/<slug>.json` signal on the
    INSUFFICIENT_SOURCE_DATA path.
    """
    if not isinstance(article, dict) or not article.get("title"):
        raise ValueError("article must be a dict with a non-empty 'title'")

    if verify_fn is None:
        from contentprinter.verify import verify_citations as verify_fn
    if llm_complete is None:
        llm_complete = llm_client.complete
    if llm_is_configured is None:
        llm_is_configured = llm_client.is_configured

    slug_label = slug or article.get("slug") or article.get("topic") or ""

    allowed = extract_allowed_citations(article, verify_fn=verify_fn)

    if not allowed:
        # `total_attempted` is hardcoded to 0 in the INSUFFICIENT path on
        # purpose: we only reach this branch when the post-verification
        # allow-list is empty, which means every regex match either failed
        # Crossref/PubMed verification or was filtered out at extract time.
        # The "structured + inline_doi + inline_pmid" sub-counts above are
        # the RAW match counts (pre-verification), useful for an operator
        # who needs to triage "we tried but verification rejected them"
        # vs "the regex didn't match anything at all". A non-zero
        # `total_attempted` would shadow that distinction. Schema preserved
        # for forward-compat — a future signal-file consumer may want a
        # post-verification count and the field is the natural place.
        breakdown = {
            "structured_content_doi": bool(
                (article.get("structured_content") or {}).get("doi")
                or (article.get("structured_content") or {}).get("pmid")
            ),
            "inline_doi_matches": len(_INLINE_DOI.findall(article.get("full_text") or "")),
            "inline_pmid_matches": len(_INLINE_PMID.findall(article.get("full_text") or "")),
            "total_attempted": 0,
        }
        print(
            f"[INSUFFICIENT_SOURCE_DATA] {slug_label}: no extractable citations "
            f"(structured={breakdown['structured_content_doi']}, "
            f"inline_doi={breakdown['inline_doi_matches']}, "
            f"inline_pmid={breakdown['inline_pmid_matches']})"
        )
        if slug_label:
            _write_needs_research_signal(
                article, slug=slug_label, extraction_breakdown=breakdown
            )
        return None

    if not llm_is_configured():
        print(
            f"[SKIP] {slug_label}: ANTHROPIC_API_KEY not configured; "
            f"grounded drafter skipped (graceful degradation)"
        )
        return None

    prompt = build_grounded_prompt(article, allowed)
    from contentprinter.verify import is_blocking

    for attempt in range(max_retries + 1):
        temp = DEFAULT_TEMPERATURE if attempt == 0 else RETRY_TEMPERATURE
        text = llm_complete(prompt, temperature=temp)
        if text is None:
            print(f"[RETRY] {slug_label}: LLM returned None on attempt {attempt + 1}")
            continue

        if not _all_refs_in_allowlist(text, allowed):
            print(
                f"[REJECT] {slug_label}: LLM output contained refs not in "
                f"allow-list (attempt {attempt + 1}/{max_retries + 1})"
            )
            continue

        try:
            rows = verify_fn(text, slug=slug_label)
        except Exception as e:
            print(f"[REJECT] {slug_label}: verify_citations raised: {e}")
            continue
        blocking = [r for r in rows if is_blocking(r.get("severity", ""))]
        if blocking:
            print(
                f"[REJECT] {slug_label}: verify_citations found "
                f"{len(blocking)} blocking issues (attempt {attempt + 1}/{max_retries + 1})"
            )
            continue

        print(f"[OK] {slug_label}: grounded draft passed Layer A + Layer B")
        return text

    print(f"[DROP] {slug_label}: all {max_retries + 1} attempts failed, no draft produced")
    return None
