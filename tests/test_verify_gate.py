"""Unit tests for `contentprinter.run_verify_gate` (task #49).

The gate is a thin severity-routing classifier on top of `verify_citations`.
These tests monkeypatch `contentprinter.verify.verify_citations` with
synthetic rows so they never touch Crossref / PubMed. The gate's routing is
byte-identical to CSKB `app/jobs/verify_gate.py::run_verify_gate`; if either
one drifts, tests on one side will catch the divergence.
"""

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _row(severity: str, idx: int = 1) -> dict:
    """Build a minimal CitationIssue-shaped row for gate input."""
    return {
        "ref_idx": idx,
        "severity": severity,
        "slug": "test",
        "citation": f"ref {idx}",
        "doi": None,
        "pmid": None,
        "notes": "",
    }


def _patch_verify(monkeypatch, rows: list[dict]) -> None:
    import contentprinter.verify as vmod
    monkeypatch.setattr(vmod, "verify_citations", lambda draft, slug="": list(rows))


def test_all_ok_returns_done(monkeypatch):
    from contentprinter import run_verify_gate
    _patch_verify(monkeypatch, [_row("OK", 1), _row("OK", 2)])
    outcome = run_verify_gate("draft body", slug="all-ok")
    assert outcome["status"] == "done"
    assert outcome["counts"] == {"blocked": 0, "warn": 0, "pending_review": 0, "verified": 2}
    assert len(outcome["citations"]) == 2


def test_blocking_row_fails_closed(monkeypatch):
    from contentprinter import run_verify_gate
    _patch_verify(
        monkeypatch,
        [_row("OK", 1), _row("DOI_FABRICATED", 2), _row("OK", 3)],
    )
    outcome = run_verify_gate("draft body", slug="blocked")
    assert outcome["status"] == "verification_failed"
    assert outcome["counts"]["blocked"] == 1
    assert outcome["counts"]["verified"] == 2


def test_pending_only_is_pending_review(monkeypatch):
    """VERIFICATION_UNAVAILABLE alone lands the draft in pending, not done."""
    from contentprinter import run_verify_gate
    _patch_verify(
        monkeypatch,
        [_row("OK", 1), _row("VERIFICATION_UNAVAILABLE", 2)],
    )
    outcome = run_verify_gate("draft body", slug="network-down")
    assert outcome["status"] == "verification_pending_review"
    assert outcome["counts"]["pending_review"] == 1
    assert outcome["counts"]["blocked"] == 0


def test_soft_flag_only_is_pending_review(monkeypatch):
    from contentprinter import run_verify_gate
    _patch_verify(
        monkeypatch,
        [_row("OK", 1), _row("JOURNAL_MISMATCH", 2)],
    )
    outcome = run_verify_gate("draft body", slug="soft")
    assert outcome["status"] == "verification_pending_review"
    assert outcome["counts"]["warn"] == 1
    assert outcome["counts"]["blocked"] == 0


def test_blocking_beats_pending_and_warn(monkeypatch):
    """Any blocking row forces verification_failed regardless of co-presence."""
    from contentprinter import run_verify_gate
    _patch_verify(
        monkeypatch,
        [
            _row("OK", 1),
            _row("JOURNAL_MISMATCH", 2),
            _row("VERIFICATION_UNAVAILABLE", 3),
            _row("DOI_WRONG", 4),
        ],
    )
    outcome = run_verify_gate("draft body", slug="mixed")
    assert outcome["status"] == "verification_failed"
    assert outcome["counts"] == {
        "blocked": 1,
        "warn": 1,
        "pending_review": 1,
        "verified": 1,
    }


def test_unknown_severity_fails_closed(monkeypatch):
    """Any severity not in the known sets MUST be treated as blocked."""
    from contentprinter import run_verify_gate
    _patch_verify(
        monkeypatch,
        [_row("OK", 1), _row("BRAND_NEW_SEVERITY_FROM_FUTURE_AUDIT", 2)],
    )
    outcome = run_verify_gate("draft body", slug="unknown")
    assert outcome["status"] == "verification_failed"
    assert outcome["counts"]["blocked"] == 1
    assert outcome["counts"]["verified"] == 1


def test_empty_citation_list_is_done(monkeypatch):
    """A draft with no references is trivially 'done' (vacuously verified)."""
    from contentprinter import run_verify_gate
    _patch_verify(monkeypatch, [])
    outcome = run_verify_gate("draft body", slug="no-refs")
    assert outcome["status"] == "done"
    assert outcome["counts"] == {"blocked": 0, "warn": 0, "pending_review": 0, "verified": 0}
    assert outcome["citations"] == []


def test_citations_are_independent_copies(monkeypatch):
    """Mutating an outcome row should not bleed back into `verify_citations`
    results (gate consumers shouldn't have to defensively copy)."""
    from contentprinter import run_verify_gate
    source_rows = [_row("OK", 1)]
    _patch_verify(monkeypatch, source_rows)
    outcome = run_verify_gate("draft body", slug="copy")
    outcome["citations"][0]["severity"] = "MUTATED"
    assert source_rows[0]["severity"] == "OK"


def test_outcome_exports_match_public_api():
    from contentprinter import run_verify_gate, VerifyGateOutcome
    assert callable(run_verify_gate)
    # TypedDict export is callable-ish (class) — smoke test shape.
    assert VerifyGateOutcome.__name__ == "VerifyGateOutcome"
