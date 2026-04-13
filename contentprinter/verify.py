"""Library surface for citation verification (the F-0 gate).

Wraps `audits/_citation_audit.py::audit_draft` as a stable public function
that the CSKB iOS app's FastAPI job runner can call to determine whether
a generated draft is safe to publish.

Background: on 2026-04-12 researcher's #21 audit caught an earlier manual
polish workflow that had produced 38% hallucinated citations across the
31 existing posts (the offending code path has since been removed). The
drafter library function (`generate_draft`) is safe — it doesn't produce
citations at all. The hallucination path is any pipeline operation that
passes drafts through an ungrounded LLM. This verification gate is the
structural safety net that catches hallucinations regardless of how they
entered the draft.

The blocking severity set is **forward-compatible**: it includes the four
severities currently observed in production data plus three more code-path
severities that the audit module emits but that didn't fire in the
2026-04-12 dataset. A future audit run on different data may emit any of
the seven; the gate must block them all.

Usage in a CSKB job runner:

    from contentprinter import verify_citations, is_blocking

    issues = verify_citations(draft_text)
    blocking = [i for i in issues if is_blocking(i["severity"])]
    if blocking:
        job.status = "verification_failed"
        job.reasons = blocking
    else:
        job.status = "verified"
"""

from __future__ import annotations

import re
import sys as _sys
from pathlib import Path as _Path
from typing import Any, TypedDict, Union

# The audit module is in audits/_citation_audit.py at the repo root, not in
# src/. Add audits/ to sys.path so the bare `import _citation_audit` works
# in both dev mode and after `pip install -e .` (in install mode the
# audits/ directory is bundled at the repo root and stays accessible
# relative to this file's resolved location).
_AUDITS_DIR = _Path(__file__).resolve().parent.parent / "audits"
if _AUDITS_DIR.is_dir() and str(_AUDITS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_AUDITS_DIR))

import _citation_audit as _ca  # noqa: E402


# ── Severity classification ────────────────────────────────────────────────

#: Severities that mean a draft contains a publication-blocking citation
#: error. The seven entries here cover all known hallucination patterns the
#: underlying audit module can detect — including code paths that did not
#: fire in the 2026-04-12 dataset but exist in `audits/_citation_audit.py`
#: and may emit on future drafts. Defense-in-depth: when in doubt on a
#: publication gate, over-block.
#:
#: Consumers (e.g. the CSKB job runner) MAY override this set by passing
#: their own collection to `is_blocking(severity, allowed=...)`. The
#: default is the safe maximum-block set.
BLOCKING_SEVERITIES: frozenset[str] = frozenset({
    # Observed in 2026-04-12 audit data
    "DOI_FABRICATED",      # DOI doesn't exist anywhere
    "DOI_WRONG",           # DOI resolves to an unrelated paper
    "DOI_MISATTRIBUTED",   # title matches but author is fake (title theft)
    "NO_VERIFIABLE_SOURCE",  # no DOI, no PMID, PubMed search empty
    # Code paths exist in _citation_audit.py but didn't fire in 2026-04-12
    "PMID_NOT_FOUND",      # PMID lookup returned empty record
    "AUTHOR_WRONG",        # DOI resolves, partial title match, author mismatch
    "TITLE_MISMATCH",      # author + year match, title overlap < 25%
})

#: Severities that warn but do not block publication. These represent
#: minor errors a human reviewer should glance at before posting, but
#: don't indicate hallucination — usually a real paper with a wrong
#: ancillary field, or a non-academic source the audit can't verify.
SOFT_FLAG_SEVERITIES: frozenset[str] = frozenset({
    "JOURNAL_MISMATCH",    # right paper, wrong journal name in draft
    "YEAR_WRONG",          # right paper, year off by >1
    "NOT_PUBMED_INDEXED",  # textbook / blog / video — verify by hand
    "DOI_UNRESOLVABLE",    # Crossref 404 but doi.org accepts; rare
})

#: Special severity emitted by THIS wrapper (not the underlying audit
#: module) when Crossref or PubMed are unreachable at verification time.
#: Consumers should treat this as "unknown, escalate to human" rather
#: than as either pass or fail. NOT in BLOCKING_SEVERITIES — a network
#: outage shouldn't block publication, but a human should look at the
#: draft before it goes live.
VERIFICATION_UNAVAILABLE = "VERIFICATION_UNAVAILABLE"

_OK_SEVERITY = "OK"


# ── Network-failure normalization ──────────────────────────────────────────
#
# `audits/_citation_audit.py` traps its own network exceptions inside the
# Crossref / PubMed lookup branches. When a network failure occurs, the
# audit row comes back with a misleading severity label that looks like
# a classification result but is actually an outage:
#
#   - DOI branch (audit:327-335): on Crossref _get() failure, the audit
#     module falls back to doi_exists() (a HEAD against doi.org). If
#     doi.org also fails (network), `_head` returns None, `doi_exists`
#     returns False, and the row is labeled `DOI_FABRICATED` — even
#     though the citation may be a real paper that the verifier simply
#     couldn't reach. The Crossref exception message is recorded in
#     `fetch_error` on line 329 unconditionally.
#
#   - PMID branch (audit:357-359): on PubMed _get() failure, the row is
#     labeled `PMID_FETCH_ERROR` (a severity not in any of the documented
#     blocking/soft/OK sets, so it falls through to is_blocking()'s
#     unknown_blocks=True over-block path).
#
# Both are SAFE-DIRECTION failures (over-block on outage), but the labels
# are wrong and create false-positive noise during remediation. A
# remediation operator (Task #31) seeing `DOI_FABRICATED` on a real
# citation would burn lookup time chasing a non-problem.
#
# `verify_citations` post-processes audit rows to detect these network
# leaks and normalize them to `VERIFICATION_UNAVAILABLE`, while preserving
# the original audit-module label in `original_severity` for traceability.
#
# Disambiguation rule: a DOI_FABRICATED row is a REAL fabrication if and
# only if the recorded fetch_error indicates an HTTP 4xx response from
# Crossref (the actual "DOI does not exist" signal). Any other error
# pattern — URLError, timeout, DNS failure, 5xx, 429 rate limit — is a
# network outage and gets normalized to VERIFICATION_UNAVAILABLE.

# urllib.error.HTTPError formats as "HTTP Error <code>: <reason>". A real
# Crossref "DOI not found" comes through as "HTTP Error 404: Not Found".
# Other 4xx codes (400 Bad Request, 410 Gone, etc.) are also real
# Crossref responses — the DOI is malformed or withdrawn but the verifier
# successfully reached the server. 429 (rate limit) and 5xx are server-
# side failures, not citation-side.
_HTTP_4XX_REAL_FAILURE = re.compile(r"HTTP Error 4(?!29)\d{2}\b")

_NETWORK_ERROR_PATTERNS = (
    "urlopen error",          # urllib.error.URLError wrapper
    "Name or service not",    # DNS failure
    "Temporary failure",      # DNS resolver hiccup
    "Connection refused",     # service down
    "Connection reset",       # mid-stream drop
    "Network is unreachable", # routing failure
    "No route to host",       # routing failure
    "timed out",              # socket.timeout
    "timeout",                # generic timeout
    "HTTP Error 5",           # 5xx server errors (502, 503, 504)
    "HTTP Error 429",         # rate limit
)

#: Severities the audit module emits ONLY on network failure. These have
#: no legitimate non-network meaning, so any row carrying one of these
#: severities is unconditionally normalized to VERIFICATION_UNAVAILABLE
#: regardless of the fetch_error text.
_PURE_NETWORK_SEVERITIES = frozenset({"PMID_FETCH_ERROR"})

#: Severities the audit module emits BOTH on network failure AND on real
#: classification. These need fetch_error text inspection to disambiguate
#: (see `_is_network_disguised_as_classification`).
_AMBIGUOUS_NETWORK_SEVERITIES = frozenset({"DOI_FABRICATED"})


def _is_network_disguised_as_classification(row: dict) -> bool:
    """Return True if a row's severity label is a misleading network failure.

    Examines `fetch_error` text to distinguish between:
      - Real Crossref/PubMed 4xx (not 429) → genuine classification result, preserve.
      - URLError / timeout / DNS / 5xx / 429 → network outage, normalize.

    A row with severity in `_PURE_NETWORK_SEVERITIES` always returns True
    regardless of fetch_error content. A row in `_AMBIGUOUS_NETWORK_SEVERITIES`
    returns True only if the fetch_error matches a network pattern AND
    does NOT match a real-4xx pattern.
    """
    severity = row.get("severity", "")
    if severity in _PURE_NETWORK_SEVERITIES:
        return True
    if severity not in _AMBIGUOUS_NETWORK_SEVERITIES:
        return False
    fetch_error = row.get("fetch_error") or ""
    if not fetch_error:
        return False
    if _HTTP_4XX_REAL_FAILURE.search(fetch_error):
        return False
    return any(pat in fetch_error for pat in _NETWORK_ERROR_PATTERNS)


def _normalize_network_failure(row: dict) -> dict:
    """Rewrite a network-disguised-as-classification row to VERIFICATION_UNAVAILABLE.

    Preserves the original severity in `original_severity` for traceability,
    rewrites `notes` to explain the normalization, leaves `fetch_error`
    untouched so operators can see the underlying error.
    """
    original = row.get("severity", "")
    fetch_error = row.get("fetch_error") or ""
    new_row = dict(row)
    new_row["severity"] = VERIFICATION_UNAVAILABLE
    new_row["original_severity"] = original
    new_row["notes"] = (
        f"Network failure during verification (audit module reported "
        f"`{original}` but the underlying error indicates an outage, not a "
        f"classification result). Citation may still be valid — a human "
        f"reviewer should retry or check the source by hand. "
        f"Underlying error: {fetch_error[:140]}"
    )
    return new_row


# ── Result shape ───────────────────────────────────────────────────────────


class _DraftFields(TypedDict, total=False):
    first_author: str | None
    year: int | None
    title: str | None
    journal: str | None
    doi: str | None
    pmid: str | None


class _FetchedFields(TypedDict, total=False):
    title: str | None
    first_author: str | None
    year: int | None
    journal: str | None
    pmid: str  # only set when fetched via PubMed search


class _VerifyFields(TypedDict, total=False):
    author_match: bool | None
    year_match: bool | None
    title_overlap: float
    journal_match: bool


class CitationIssue(TypedDict, total=False):
    """One row from a citation verification pass.

    Schema mirrors `audits/_citation_audit.py::audit_draft` row dicts.
    All fields except `severity` and `ref_idx` may be missing or None
    depending on which audit code path produced the row.

    Stable fields (consumers can rely on these):
        slug: str — topic slug passed to verify_citations, or "" if a raw
            draft_text was supplied without a slug.
        ref_idx: int — 1-based index within the draft's REFERENCES block.
        raw: str — the original citation line from the draft.
        severity: str — one of the labels documented in API_SURFACE.md §10.
        draft: dict — what was parsed from the draft (author/year/title/doi/pmid).
        fetched: dict | None — what Crossref/PubMed returned, if anything.
        verify: dict — boolean match flags + title_overlap fraction.
        notes: str | None — human-readable explanation when severity != OK.

    Optional fields (may or may not be present):
        fetch_error: str — if Crossref/PubMed raised, the truncated error message.
    """
    slug: str
    ref_idx: int
    raw: str
    severity: str
    draft: _DraftFields
    fetched: _FetchedFields | None
    verify: _VerifyFields
    notes: str | None
    fetch_error: str


# ── Core API ───────────────────────────────────────────────────────────────


def verify_citations(
    draft: Union[str, "_Path"],
    *,
    slug: str = "",
) -> list[CitationIssue]:
    """Verify every REFERENCES entry in a draft against Crossref + PubMed.

    Args:
        draft: Either the draft.txt **contents** as a string, or a `Path`
            (or path-like string that exists on disk) pointing to a
            `draft.txt` file. Strings that look like paths but don't exist
            on disk are treated as draft text — same disambiguation rule
            as `parse_draft_text`.
        slug: Optional topic slug for traceability in the returned rows.
            Defaults to "" if the caller is verifying a free-floating
            draft text. Pass the topic slug if available so downstream
            consumers (e.g. the CSKB UI) can group issues by post.

    Returns:
        A list of `CitationIssue` dicts, one per REFERENCES entry in the
        draft. Empty list if the draft has no REFERENCES block. Order
        matches the draft's reference numbering (1-based `ref_idx`).

        Severities follow the ladder documented in API_SURFACE.md §10.
        Use `is_blocking(severity)` to determine which rows should fail
        an F-0 gate vs. surface as soft warnings.

    Raises:
        ValueError: if `draft` is empty or not a string/Path.
        FileNotFoundError: if `draft` is a Path that doesn't exist.

    **Network behavior:** this function makes outbound HTTPS calls to
    `api.crossref.org`, `doi.org`, and `eutils.ncbi.nlm.nih.gov`. Each
    REFERENCES entry triggers 1-3 lookups depending on whether it has a
    DOI / PMID / neither. Total runtime is roughly **1-2 seconds per
    citation**, so a 5-ref draft takes ~10s. **Run this in a background
    job, not a request handler.**

    **Graceful degradation:** if Crossref or PubMed are unreachable
    (network failure, rate limit, DNS, timeout), the affected row is
    returned with `severity = "VERIFICATION_UNAVAILABLE"` and a `notes`
    field explaining the failure. The function does NOT raise on
    network errors — it lets the caller decide whether to retry or
    surface to a human. `VERIFICATION_UNAVAILABLE` is NOT in
    `BLOCKING_SEVERITIES` — treat it as "unknown, escalate to human"
    rather than as pass or fail.

    Stability: signature and return-row schema are part of the public
    surface. New severities may be added without a major version bump
    (consumers should default to "block on unknown severity" — see
    `is_blocking`'s `unknown_blocks` parameter).
    """
    text = _coerce_draft_to_text(draft)
    if not text.strip():
        raise ValueError("verify_citations requires a non-empty draft text or path")

    rows: list[CitationIssue] = []
    for ref_idx, raw in _ca.parse_refs_block(text):
        try:
            single = _ca.audit_draft(_synthetic_draft_with_one_ref(raw, ref_idx), slug)
        except Exception as e:
            # The audit module's network calls bubble up; trap them here
            # and emit a VERIFICATION_UNAVAILABLE row instead of crashing
            # the whole verify pass. The CSKB UI escalates this to a human.
            rows.append(_build_verification_unavailable_row(
                slug, ref_idx, raw,
                notes=(
                    "Crossref or PubMed lookup failed at verification time. "
                    "This is NOT a hallucination signal — the citation may "
                    "still be valid. A human reviewer should retry or check "
                    f"the source by hand. Raw error: {str(e)[:140]}"
                ),
                fetch_error=str(e)[:140],
            ))
            continue

        if single:
            row = single[0]
            # Code-reviewer's #36 finding: the audit module catches its own
            # network errors internally and produces misleading severity
            # labels (PMID_FETCH_ERROR or DOI_FABRICATED with a network
            # error in fetch_error). Detect those and normalize to
            # VERIFICATION_UNAVAILABLE before handing to consumers, so
            # remediation operators don't chase ghost fabrications.
            if _is_network_disguised_as_classification(row):
                row = _normalize_network_failure(row)
            rows.append(row)
        else:
            # parse_refs_block returned a hit but audit_draft produced no
            # row — should not happen with the current audit module, but
            # treat it as VERIFICATION_UNAVAILABLE for forward compat.
            rows.append(_build_verification_unavailable_row(
                slug, ref_idx, raw,
                notes="Audit module returned no verification row for this reference.",
            ))

    return rows


def _build_verification_unavailable_row(
    slug: str,
    ref_idx: int,
    raw: str,
    *,
    notes: str,
    fetch_error: str | None = None,
) -> dict:
    """Build a VERIFICATION_UNAVAILABLE row with the full draft schema.

    Code-reviewer's #36 finding: the prior implementation built `draft`
    from `_ca.extract_fields(raw)` which only returns 5 keys (no `journal`).
    API_SURFACE.md §10.2 documents 6 keys including `journal`. Consumers
    doing `issue["draft"]["journal"]` would KeyError on the exception path.
    Fix: also call `_ca.draft_journal_of(raw, fields["title"])` to populate
    the journal field, matching the happy-path schema exactly.
    """
    fields = _ca.extract_fields(raw)
    fields["journal"] = _ca.draft_journal_of(raw, fields.get("title"))
    row: dict = {
        "slug": slug,
        "ref_idx": ref_idx,
        "raw": raw,
        "severity": VERIFICATION_UNAVAILABLE,
        "draft": fields,
        "fetched": None,
        "verify": {},
        "notes": notes,
    }
    if fetch_error is not None:
        row["fetch_error"] = fetch_error
    return row


def is_blocking(
    severity: str,
    *,
    allowed: frozenset[str] | set[str] | None = None,
    unknown_blocks: bool = True,
) -> bool:
    """Return True iff `severity` indicates a publication-blocking citation issue.

    Args:
        severity: A severity string from a `CitationIssue.severity` field.
        allowed: Optional override for the blocking set. Pass your own
            collection to use a stricter or looser policy than
            `BLOCKING_SEVERITIES`. Default uses `BLOCKING_SEVERITIES`.
        unknown_blocks: When True (default), severities not in either
            `BLOCKING_SEVERITIES` or `SOFT_FLAG_SEVERITIES` and not equal
            to `"OK"` are treated as blocking. This is the safer default
            for forward-compat: if a future audit module rev adds a new
            severity that this wrapper doesn't recognize, the gate
            over-blocks rather than silently letting it through.

    Returns:
        bool — True if the severity should fail an F-0 publication gate.

    The default behavior makes this safe to call from any consumer
    without re-reading the docs:

        from contentprinter import verify_citations, is_blocking
        issues = verify_citations(draft_text)
        blocked = any(is_blocking(i["severity"]) for i in issues)
    """
    block_set = allowed if allowed is not None else BLOCKING_SEVERITIES
    if severity in block_set:
        return True
    if severity == _OK_SEVERITY:
        return False
    if severity in SOFT_FLAG_SEVERITIES:
        return False
    if severity == VERIFICATION_UNAVAILABLE:
        return False  # escalate-to-human, not block
    return unknown_blocks


# ── Internal helpers ───────────────────────────────────────────────────────


def _coerce_draft_to_text(draft) -> str:
    if draft is None:
        raise ValueError("verify_citations requires a draft text or path, got None")
    if isinstance(draft, _Path):
        return draft.read_text(encoding="utf-8")
    if isinstance(draft, str):
        # Disambiguate path-like strings: if it exists on disk and is a
        # file, treat as a path. Otherwise treat as draft text. This is
        # the same rule used by `parse_draft_text`.
        try:
            candidate = _Path(draft)
            if candidate.exists() and candidate.is_file() and len(draft) < 4096:
                return candidate.read_text(encoding="utf-8")
        except (OSError, ValueError):
            pass
        return draft
    raise ValueError(
        f"verify_citations requires str or Path, got {type(draft).__name__}"
    )


def _synthetic_draft_with_one_ref(raw_ref: str, ref_idx: int) -> str:
    """Wrap a single raw reference line in the minimal draft.txt scaffold
    that `audit_draft` expects, so we can verify one ref at a time.

    `audit_draft` parses a full draft.txt and runs `parse_refs_block` on
    it. We've already done that splitting in `verify_citations`, so we
    rebuild a minimal draft body around each ref to feed it back through
    the per-ref classification logic without re-parsing the whole REFERENCES
    block. This is the cleanest way to delegate per-ref work to the audit
    module without forking its `audit_draft` body.
    """
    return f"REFERENCES:\n{ref_idx}. {raw_ref}\n"
