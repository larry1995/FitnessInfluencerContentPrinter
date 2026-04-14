"""Offline tests for `contentprinter.verify_citations` (Task #27).

All tests monkeypatch the audit module's network helpers (`_get`, `_head`)
so the suite never makes live HTTP calls. The audit module is the source
of truth for citation classification — these tests verify the wrapper
contract (severity routing, graceful degradation, schema, version bump),
not the audit module's internals.
"""

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _draft_with_refs(*ref_lines: str) -> str:
    """Build a minimal draft.txt body with the given REFERENCES lines."""
    refs = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(ref_lines))
    return (
        "=" * 60 + "\n"
        "POST #1 — TEST\n"
        "Source: test\n"
        + "=" * 60 + "\n\n"
        "CAPTION:\n"
        + "-" * 40 + "\n"
        "TEST CAPTION\n\n"
        "Body text.\n\n"
        + "-" * 40 + "\n\n"
        "REFERENCES:\n"
        + refs + "\n"
    )


def _patch_audit_network(monkeypatch, *, crossref_response=None, head_status=200,
                        pubmed_search=None, pubmed_summary=None,
                        raise_on_get=None):
    """Replace the audit module's network primitives with deterministic stubs."""
    import _citation_audit as ca

    def fake_get(url, timeout=25):
        if raise_on_get is not None:
            raise raise_on_get
        if "api.crossref.org/works/" in url:
            return json.dumps(crossref_response or {"message": {}}).encode()
        if "esearch.fcgi" in url:
            return json.dumps(pubmed_search or {"esearchresult": {"idlist": []}}).encode()
        if "esummary.fcgi" in url:
            return json.dumps(pubmed_summary or {"result": {}}).encode()
        return b"{}"

    def fake_head(url, timeout=15):
        return head_status

    monkeypatch.setattr(ca, "_get", fake_get)
    monkeypatch.setattr(ca, "_head", fake_head)
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda *_: None)


# ── Severity classification (no network calls) ─────────────────────────────


def test_blocking_severities_includes_observed_and_forward_compat():
    from contentprinter import BLOCKING_SEVERITIES
    observed = {"DOI_FABRICATED", "DOI_WRONG", "DOI_MISATTRIBUTED", "NO_VERIFIABLE_SOURCE"}
    forward_compat = {"PMID_NOT_FOUND", "AUTHOR_WRONG", "TITLE_MISMATCH"}
    assert observed.issubset(BLOCKING_SEVERITIES)
    assert forward_compat.issubset(BLOCKING_SEVERITIES)
    assert len(BLOCKING_SEVERITIES) == 7


def test_soft_flag_severities_disjoint_from_blocking():
    from contentprinter import BLOCKING_SEVERITIES, SOFT_FLAG_SEVERITIES
    assert BLOCKING_SEVERITIES.isdisjoint(SOFT_FLAG_SEVERITIES)


def test_is_blocking_returns_true_for_all_seven_blocking_severities():
    from contentprinter import is_blocking, BLOCKING_SEVERITIES
    for sev in BLOCKING_SEVERITIES:
        assert is_blocking(sev) is True, f"{sev} should be blocking"


def test_is_blocking_returns_false_for_ok():
    from contentprinter import is_blocking
    assert is_blocking("OK") is False


def test_is_blocking_returns_false_for_soft_flags():
    from contentprinter import is_blocking, SOFT_FLAG_SEVERITIES
    for sev in SOFT_FLAG_SEVERITIES:
        assert is_blocking(sev) is False, f"{sev} should be soft, not blocking"


def test_is_blocking_returns_false_for_verification_unavailable():
    """Network outage = escalate to human, not block."""
    from contentprinter import is_blocking, VERIFICATION_UNAVAILABLE
    assert is_blocking(VERIFICATION_UNAVAILABLE) is False


def test_is_blocking_unknown_severity_blocks_by_default():
    """Forward-compat: unknown severities over-block on the safe side."""
    from contentprinter import is_blocking
    assert is_blocking("FUTURE_NEW_SEVERITY_NOT_IN_ANY_SET") is True


def test_is_blocking_unknown_severity_passes_when_unknown_blocks_false():
    from contentprinter import is_blocking
    assert is_blocking("FUTURE_NEW_SEVERITY", unknown_blocks=False) is False


def test_is_blocking_accepts_custom_allowed_set():
    """Consumer override: pass a stricter or looser blocking set."""
    from contentprinter import is_blocking
    custom = frozenset({"JOURNAL_MISMATCH", "OK"})
    assert is_blocking("JOURNAL_MISMATCH", allowed=custom) is True
    assert is_blocking("DOI_FABRICATED", allowed=custom, unknown_blocks=False) is False


# ── verify_citations input handling ────────────────────────────────────────


def test_verify_citations_rejects_empty_string():
    from contentprinter import verify_citations
    try:
        verify_citations("")
    except ValueError as e:
        assert "non-empty" in str(e).lower()
    else:
        raise AssertionError("expected ValueError on empty string")


def test_verify_citations_rejects_none():
    from contentprinter import verify_citations
    try:
        verify_citations(None)
    except ValueError as e:
        assert "none" in str(e).lower() or "draft" in str(e).lower()
    else:
        raise AssertionError("expected ValueError on None")


def test_verify_citations_returns_empty_list_for_draft_without_refs(monkeypatch):
    from contentprinter import verify_citations
    _patch_audit_network(monkeypatch)
    draft = "CAPTION:\n----\nNo references block here at all.\n----\n"
    result = verify_citations(draft)
    assert result == []


def test_verify_citations_accepts_path_object(tmp_path, monkeypatch):
    from contentprinter import verify_citations
    _patch_audit_network(
        monkeypatch,
        crossref_response={
            "message": {
                "title": ["Test Paper Title"],
                "author": [{"family": "Smith"}],
                "issued": {"date-parts": [[2024]]},
                "container-title": ["Journal of Tests"],
            }
        },
    )
    draft_text = _draft_with_refs(
        "Smith J et al. (2024). Test Paper Title. J Tests, 1(1):1. doi:10.1234/test"
    )
    draft_path = tmp_path / "draft.txt"
    draft_path.write_text(draft_text, encoding="utf-8")
    result = verify_citations(draft_path, slug="test_topic")
    assert len(result) == 1
    assert result[0]["slug"] == "test_topic"


# ── verify_citations severity routing (with mocked network) ────────────────


def test_verify_citations_classifies_ok_when_crossref_matches(monkeypatch):
    from contentprinter import verify_citations, is_blocking
    _patch_audit_network(
        monkeypatch,
        crossref_response={
            "message": {
                "title": ["Effects of Creatine on Strength"],
                "author": [{"family": "Forbes"}],
                "issued": {"date-parts": [[2025]]},
                "container-title": ["Nutrients"],
            }
        },
    )
    draft = _draft_with_refs(
        "Forbes SC et al. (2025). Effects of Creatine on Strength. Nutrients, 17:2748. doi:10.3390/nu17172748"
    )
    rows = verify_citations(draft, slug="creatine")
    assert len(rows) == 1
    assert rows[0]["severity"] == "OK"
    assert is_blocking(rows[0]["severity"]) is False


def test_verify_citations_classifies_doi_misattributed_on_title_theft(monkeypatch):
    """The 'title theft' pattern: real title + DOI, fake author."""
    from contentprinter import verify_citations, is_blocking
    _patch_audit_network(
        monkeypatch,
        crossref_response={
            "message": {
                "title": ["Effects of Creatine on Strength and Power"],
                "author": [{"family": "ActualAuthor"}],
                "issued": {"date-parts": [[2025]]},
                "container-title": ["Nutrients"],
            }
        },
    )
    draft = _draft_with_refs(
        "FakeAuthor X et al. (2025). Effects of Creatine on Strength and Power. Nutrients, 17:2748. doi:10.3390/nu17172748"
    )
    rows = verify_citations(draft)
    assert len(rows) == 1
    assert rows[0]["severity"] == "DOI_MISATTRIBUTED"
    assert is_blocking(rows[0]["severity"]) is True


def test_verify_citations_classifies_doi_fabricated_when_doi_does_not_exist(monkeypatch):
    """Crossref raises + doi.org also returns 404 → DOI is fake."""
    from contentprinter import verify_citations, is_blocking
    _patch_audit_network(
        monkeypatch,
        head_status=404,
        raise_on_get=Exception("HTTP 404 Not Found"),
    )
    draft = _draft_with_refs(
        "Fake B et al. (2024). Imaginary Paper. Imaginary J. doi:10.9999/totally-fake-9999"
    )
    rows = verify_citations(draft)
    assert len(rows) == 1
    assert rows[0]["severity"] == "DOI_FABRICATED"
    assert is_blocking(rows[0]["severity"]) is True


def test_verify_citations_handles_no_doi_no_pmid_with_no_pubmed_hits(monkeypatch):
    """No DOI/PMID + PubMed search returns nothing → NO_VERIFIABLE_SOURCE."""
    from contentprinter import verify_citations, is_blocking
    _patch_audit_network(
        monkeypatch,
        pubmed_search={"esearchresult": {"idlist": []}},
    )
    draft = _draft_with_refs(
        "Phantom A et al. (2024). A paper that does not exist. Mystery J."
    )
    rows = verify_citations(draft)
    assert len(rows) == 1
    assert rows[0]["severity"] == "NO_VERIFIABLE_SOURCE"
    assert is_blocking(rows[0]["severity"]) is True


def test_verify_citations_recognizes_non_academic_source(monkeypatch):
    """YouTube / textbook citations are flagged but not blocking."""
    from contentprinter import verify_citations, is_blocking
    _patch_audit_network(monkeypatch)
    draft = _draft_with_refs(
        "Nippard J (2024). Best chest exercises. YouTube video."
    )
    rows = verify_citations(draft)
    assert len(rows) == 1
    assert rows[0]["severity"] == "NOT_PUBMED_INDEXED"
    assert is_blocking(rows[0]["severity"]) is False


# ── Schema sanity ──────────────────────────────────────────────────────────


def test_verify_citations_row_schema_matches_audit_module(monkeypatch):
    """Wrapper rows must match the audit module's row dict shape so
    consumers (CSKB UI) can deserialize without per-key fallback logic."""
    from contentprinter import verify_citations
    _patch_audit_network(
        monkeypatch,
        crossref_response={
            "message": {
                "title": ["Some Paper"],
                "author": [{"family": "Author"}],
                "issued": {"date-parts": [[2024]]},
                "container-title": ["Journal"],
            }
        },
    )
    draft = _draft_with_refs(
        "Author A et al. (2024). Some Paper. Journal, 1:1. doi:10.1234/test"
    )
    rows = verify_citations(draft, slug="test")
    row = rows[0]
    for key in ("slug", "ref_idx", "raw", "severity", "draft", "fetched", "verify"):
        assert key in row, f"row missing required key {key!r}"
    assert isinstance(row["draft"], dict)
    assert "first_author" in row["draft"]
    assert "doi" in row["draft"]


def test_verify_citations_returns_rows_in_input_order(monkeypatch):
    from contentprinter import verify_citations
    _patch_audit_network(
        monkeypatch,
        crossref_response={
            "message": {
                "title": ["X"],
                "author": [{"family": "Y"}],
                "issued": {"date-parts": [[2024]]},
                "container-title": ["Z"],
            }
        },
    )
    draft = _draft_with_refs(
        "Author A et al. (2024). Paper One. J Test. doi:10.1/a",
        "Author B et al. (2024). Paper Two. J Test. doi:10.1/b",
        "Author C et al. (2024). Paper Three. J Test. doi:10.1/c",
    )
    rows = verify_citations(draft)
    assert [r["ref_idx"] for r in rows] == [1, 2, 3]


# ── Version bump check ────────────────────────────────────────────────────


def test_package_version_is_040():
    import contentprinter
    assert contentprinter.__version__ == "0.4.0"


def test_package_exports_verify_symbols():
    import contentprinter
    expected = {
        "verify_citations",
        "is_blocking",
        "BLOCKING_SEVERITIES",
        "SOFT_FLAG_SEVERITIES",
        "VERIFICATION_UNAVAILABLE",
        "CitationIssue",
    }
    assert expected.issubset(set(contentprinter.__all__))
    for name in expected:
        assert hasattr(contentprinter, name), f"{name} not exported"


# ── #36 network-failure normalization ──────────────────────────────────────


def test_verify_citations_preserves_real_doi_fabricated_with_http_404(monkeypatch):
    """A real DOI fabrication (Crossref returns 404, doi.org also 404)
    must remain DOI_FABRICATED — the #36 normalization logic must NOT
    over-normalize away real fabrications. This is the regression case
    that protects all 7 currently-flagged DOI_FABRICATED entries."""
    import urllib.error
    from contentprinter import verify_citations, is_blocking

    _patch_audit_network(
        monkeypatch,
        head_status=404,  # doi.org HEAD returns 404
        raise_on_get=urllib.error.HTTPError(
            "https://api.crossref.org/works/fake", 404, "Not Found", {}, None
        ),
    )
    draft = _draft_with_refs(
        "Fake B et al. (2024). Imaginary Paper. Imaginary J. doi:10.9999/totally-fake-9999"
    )
    rows = verify_citations(draft)
    assert len(rows) == 1
    # Real fabrication: severity must stay DOI_FABRICATED, NOT be normalized
    assert rows[0]["severity"] == "DOI_FABRICATED"
    assert "original_severity" not in rows[0], (
        "real DOI_FABRICATED must not be normalized — it had no network failure"
    )
    assert is_blocking(rows[0]["severity"]) is True


def test_verify_citations_normalizes_doi_fabricated_on_url_error(monkeypatch):
    """A DOI lookup that fails with URLError (DNS / connection refused /
    network unreachable) must be normalized to VERIFICATION_UNAVAILABLE
    instead of being mislabeled as DOI_FABRICATED. This is the #36 fix
    that prevents remediation operators from chasing ghost fabrications
    during a VPN drop."""
    import urllib.error
    from contentprinter import verify_citations, is_blocking, VERIFICATION_UNAVAILABLE

    _patch_audit_network(
        monkeypatch,
        # Both Crossref and doi.org HEAD fail with the same network error.
        # _head returns None on exception, doi_exists returns False, so the
        # audit module would label this DOI_FABRICATED.
        raise_on_get=urllib.error.URLError(
            "<urlopen error [Errno -3] Temporary failure in name resolution>"
        ),
    )
    # Override head_status to simulate doi.org failing too
    import _citation_audit as ca

    def head_fail(url, timeout=15):
        return None  # mimics _head's exception → None branch

    monkeypatch.setattr(ca, "_head", head_fail)

    draft = _draft_with_refs(
        "Real Author A et al. (2024). A real paper. Real J. doi:10.1234/real-paper"
    )
    rows = verify_citations(draft)
    assert len(rows) == 1
    # Network failure: severity must be normalized
    assert rows[0]["severity"] == VERIFICATION_UNAVAILABLE
    assert rows[0]["original_severity"] == "DOI_FABRICATED"
    assert is_blocking(rows[0]["severity"]) is False
    assert "Temporary failure" in rows[0]["notes"] or "name resolution" in rows[0]["notes"]


def test_verify_citations_unavailable_row_has_full_draft_schema(monkeypatch):
    """The exception-path VERIFICATION_UNAVAILABLE row must have all 6
    documented draft keys (first_author, year, title, journal, doi, pmid).
    Code-reviewer's #36 finding: previously the exception path used
    extract_fields() which only returned 5 keys (no journal), causing a
    schema drift that would KeyError on consumers reading draft.journal."""
    import _citation_audit as ca
    from contentprinter import verify_citations

    # Force the audit_draft call itself to raise (not the per-citation
    # network branches inside it). This exercises the exception-handler
    # branch in verify_citations that builds a row from extract_fields.
    def explode(*args, **kwargs):
        raise ConnectionError("simulated catastrophic failure during audit")

    monkeypatch.setattr(ca, "audit_draft", explode)

    draft = _draft_with_refs(
        "Smith J et al. (2024). The Title of the Paper. J Strength Cond Res, 38(1):1-10. doi:10.1234/test"
    )
    rows = verify_citations(draft, slug="test_topic")
    assert len(rows) == 1
    row = rows[0]
    assert row["severity"] == "VERIFICATION_UNAVAILABLE"

    # Schema check: all 6 documented draft keys must be present
    expected_keys = {"first_author", "year", "title", "journal", "doi", "pmid"}
    actual_keys = set(row["draft"].keys())
    assert expected_keys.issubset(actual_keys), (
        f"draft missing keys: {expected_keys - actual_keys}"
    )

    # Sanity: the journal field should have been populated by draft_journal_of
    # (it parses the citation tail after the title), so for a well-formed
    # citation it shouldn't be None. Smith J ... J Strength Cond Res, 38...
    assert row["draft"]["journal"] is not None
    assert "Strength Cond Res" in row["draft"]["journal"]
