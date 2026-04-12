"""Library surface for grounded LLM draft generation.

Wraps `src/grounded_drafter.py::generate_grounded_draft` with a stable
signature. Unlike `contentprinter.drafter.generate_draft` (the pure-Python
template path), this function calls Anthropic's Messages API and is
runtime-bounded by the network round-trip — see API_SURFACE.md §11 for the
30-60 second budget and the "job-runner only, not request-handler" rule.

Graceful degradation: if `ANTHROPIC_API_KEY` is not configured, returns
`None` after a clear log line. Same pattern as `generate_chinese_from_english`.
Callers MUST handle the `None` case.
"""

from __future__ import annotations

from typing import Any

import grounded_drafter as _gd


def generate_grounded_draft(
    article: dict[str, Any],
    *,
    max_retries: int = 1,
    slug: str | None = None,
) -> str | None:
    """Produce a draft.txt body whose REFERENCES block is grounded in
    citations extracted (and verified) from the source article.

    Args:
        article: A scraped-article dict. Must contain `title`. Recognized
            optional fields: `full_text`, `structured_content` (PubMed
            shape — `pmid`, `doi`, `authors`, `journal`, `year`),
            `source`, `url` / `source_url`, `topic`, `slug`, `source_type`.
        max_retries: Retries after the first attempt fails Layer A
            (allow-list byte-check) or Layer B (`verify_citations` defense
            -in-depth). Default `1` (one retry at lower temperature).
        slug: Optional topic slug for log lines and the `.needs_research`
            signal file. Defaults to `article.get("slug")` /
            `article.get("topic")` / "".

    Returns:
        The draft.txt text body on success — caption + REFERENCES block,
        ready to write to disk. **Returns `None` on three distinct paths**:

        - `INSUFFICIENT_SOURCE_DATA` — the source article had zero
          extractable verified citations. A signal file is written to
          `Posts/.needs_research/<slug>.json` for operational triage.
        - LLM not configured — `is_llm_configured()` returned False
          (no `ANTHROPIC_API_KEY`).
        - `DROP` — the LLM produced output that failed allow-list or
          `verify_citations` on every retry. The post is not saved.

        Callers cannot distinguish the three None paths from the return
        value alone — log lines on stdout describe which path was taken.
        For programmatic disambiguation, call `is_llm_configured()` first.

    Raises:
        `ValueError` if `article` is not a dict or has no `title`.

    Side effects:
        - One or more outbound HTTPS requests to `api.anthropic.com`
          (LLM call, retried at most `max_retries + 1` times).
        - Crossref / PubMed lookups via `verify_citations` — one Layer B
          re-verification pass on success.
        - May write a single file under `Posts/.needs_research/<slug>.json`
          on the INSUFFICIENT_SOURCE_DATA path. No other filesystem writes.

    Stability: signature and return-type frozen at 0.3.0. Behavior of the
    three None paths is part of the contract — see API_SURFACE.md §6 #7.
    Runtime budget (30-60s end-to-end) is documented but not enforced;
    callers must run this in a background worker, not a request handler.
    """
    if not isinstance(article, dict) or not article.get("title"):
        raise ValueError("article must be a dict with a non-empty 'title'")
    return _gd.generate_grounded_draft(
        article,
        max_retries=max_retries,
        slug=slug,
    )
