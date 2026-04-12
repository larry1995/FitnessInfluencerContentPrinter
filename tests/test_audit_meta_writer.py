"""Tests for src/audit_meta_writer.py (Task #29)."""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


# ── derive_status ──────────────────────────────────────────────────────────


def test_derive_status_ok_when_all_ok():
    from audit_meta_writer import derive_status
    rows = [{"severity": "OK"}, {"severity": "OK"}]
    assert derive_status(rows) == "OK"


def test_derive_status_ok_when_empty():
    from audit_meta_writer import derive_status
    assert derive_status([]) == "OK"


def test_derive_status_warn_when_only_soft_flags():
    from audit_meta_writer import derive_status
    rows = [
        {"severity": "OK"},
        {"severity": "JOURNAL_MISMATCH"},
        {"severity": "OK"},
    ]
    assert derive_status(rows) == "WARN"


def test_derive_status_warn_with_multiple_soft_flags():
    from audit_meta_writer import derive_status
    rows = [
        {"severity": "JOURNAL_MISMATCH"},
        {"severity": "YEAR_WRONG"},
        {"severity": "NOT_PUBMED_INDEXED"},
        {"severity": "DOI_UNRESOLVABLE"},
    ]
    assert derive_status(rows) == "WARN"


def test_derive_status_blocked_when_any_hard_severity():
    from audit_meta_writer import derive_status
    rows = [
        {"severity": "OK"},
        {"severity": "OK"},
        {"severity": "DOI_FABRICATED"},
        {"severity": "OK"},
    ]
    assert derive_status(rows) == "BLOCKED"


def test_derive_status_blocked_dominates_soft_flags():
    """A single hard severity must dominate even if there are multiple
    soft flags. Don't allow majority-wins or first-wins logic."""
    from audit_meta_writer import derive_status
    rows = [
        {"severity": "JOURNAL_MISMATCH"},
        {"severity": "YEAR_WRONG"},
        {"severity": "JOURNAL_MISMATCH"},
        {"severity": "DOI_WRONG"},
        {"severity": "JOURNAL_MISMATCH"},
    ]
    assert derive_status(rows) == "BLOCKED"


def test_derive_status_blocked_for_each_of_seven_hard_severities():
    """Forward-compat: all 7 entries in BLOCKING_SEVERITIES must dominate."""
    from audit_meta_writer import derive_status
    from contentprinter import BLOCKING_SEVERITIES
    for sev in BLOCKING_SEVERITIES:
        assert derive_status([{"severity": sev}]) == "BLOCKED", \
            f"{sev} should produce BLOCKED status"


# ── trim_issue_for_meta ────────────────────────────────────────────────────


def test_trim_issue_keeps_only_four_fields():
    from audit_meta_writer import trim_issue_for_meta
    full_row = {
        "slug": "test",
        "ref_idx": 3,
        "raw": "Smith J et al. (2024). Some Paper. J Test, 1:1.",
        "draft": {"first_author": "Smith", "year": 2024, "doi": None},
        "fetched": {"title": "Some Paper", "first_author": "Smith"},
        "verify": {"author_match": True, "title_overlap": 0.95},
        "severity": "OK",
        "notes": None,
    }
    trimmed = trim_issue_for_meta(full_row)
    assert set(trimmed.keys()) == {"ref_idx", "severity", "raw", "notes"}
    assert trimmed["ref_idx"] == 3
    assert trimmed["severity"] == "OK"
    assert trimmed["raw"].startswith("Smith J")


# ── build_audit_fields ─────────────────────────────────────────────────────


def test_build_audit_fields_excludes_ok_rows_from_issues_list():
    from audit_meta_writer import build_audit_fields
    rows = [
        {"ref_idx": 1, "severity": "OK", "raw": "ok", "notes": None},
        {"ref_idx": 2, "severity": "DOI_WRONG", "raw": "bad", "notes": "wrong"},
        {"ref_idx": 3, "severity": "OK", "raw": "ok", "notes": None},
    ]
    fields = build_audit_fields(rows, "2026-04-12")
    assert fields["audit_status"] == "BLOCKED"
    assert fields["audit_date"] == "2026-04-12"
    assert fields["publication_allowed"] is False
    assert len(fields["audit_issues"]) == 1
    assert fields["audit_issues"][0]["ref_idx"] == 2
    assert fields["audit_issues"][0]["severity"] == "DOI_WRONG"


def test_build_audit_fields_publication_allowed_true_for_warn():
    from audit_meta_writer import build_audit_fields
    rows = [
        {"ref_idx": 1, "severity": "OK", "raw": "ok", "notes": None},
        {"ref_idx": 2, "severity": "JOURNAL_MISMATCH", "raw": "soft", "notes": "minor"},
    ]
    fields = build_audit_fields(rows, "2026-04-12")
    assert fields["audit_status"] == "WARN"
    assert fields["publication_allowed"] is True
    assert len(fields["audit_issues"]) == 1


def test_build_audit_fields_publication_allowed_true_for_ok():
    from audit_meta_writer import build_audit_fields
    rows = [
        {"ref_idx": 1, "severity": "OK", "raw": "ok", "notes": None},
        {"ref_idx": 2, "severity": "OK", "raw": "ok", "notes": None},
    ]
    fields = build_audit_fields(rows, "2026-04-12")
    assert fields["audit_status"] == "OK"
    assert fields["publication_allowed"] is True
    assert fields["audit_issues"] == []


# ── process_slug end-to-end ────────────────────────────────────────────────


def test_process_slug_writes_meta_json(tmp_path, monkeypatch):
    import audit_meta_writer
    posts_dir = tmp_path / "Posts"
    topic = posts_dir / "test_topic"
    topic.mkdir(parents=True)
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    rows = [
        {"slug": "test_topic", "ref_idx": 1, "severity": "DOI_FABRICATED",
         "raw": "Fake A. (2024).", "notes": "fake doi"},
    ]
    msg = audit_meta_writer.process_slug("test_topic", rows, "2026-04-12")
    assert "BLOCKED" in msg
    assert "test_topic" in msg

    meta = json.loads((topic / "meta.json").read_text())
    assert meta["audit_status"] == "BLOCKED"
    assert meta["publication_allowed"] is False
    assert meta["audit_date"] == "2026-04-12"
    assert len(meta["audit_issues"]) == 1


def test_process_slug_preserves_existing_meta_fields(tmp_path, monkeypatch):
    """The writer must merge_meta-style: audit fields update, everything
    else stays untouched."""
    import audit_meta_writer
    posts_dir = tmp_path / "Posts"
    topic = posts_dir / "test_topic"
    topic.mkdir(parents=True)
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    existing = {
        "post_number": 5,
        "topic_slug": "test_topic",
        "topic_label": "NUTRITION",
        "source_name": "BarBend",
        "source_url": "https://example.com/x",
        "tags": ["#Curated", "#ByHand"],
        "references": [{"citation": "hand-curated"}],
        "has_chinese": True,
    }
    (topic / "meta.json").write_text(json.dumps(existing), encoding="utf-8")

    rows = [
        {"slug": "test_topic", "ref_idx": 1, "severity": "DOI_FABRICATED",
         "raw": "Fake.", "notes": None},
    ]
    audit_meta_writer.process_slug("test_topic", rows, "2026-04-12")

    after = json.loads((topic / "meta.json").read_text())
    assert after["audit_status"] == "BLOCKED"
    assert after["publication_allowed"] is False
    assert after["post_number"] == 5
    assert after["topic_label"] == "NUTRITION"
    assert after["tags"] == ["#Curated", "#ByHand"]
    assert after["references"] == [{"citation": "hand-curated"}]
    assert after["has_chinese"] is True


def test_process_slug_remediation_overwrites_blocked_to_ok(tmp_path, monkeypatch):
    """Critical case: a remediation pass that clears all hard severities
    must overwrite the old BLOCKED status with the new OK, not preserve
    the stale BLOCKED. This is why audit fields are in MERGE_UPDATE_KEYS,
    not MERGE_PRESERVE_KEYS."""
    import audit_meta_writer
    posts_dir = tmp_path / "Posts"
    topic = posts_dir / "test_topic"
    topic.mkdir(parents=True)
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    rows_blocked = [{"slug": "test_topic", "ref_idx": 1, "severity": "DOI_FABRICATED",
                     "raw": "Fake.", "notes": None}]
    audit_meta_writer.process_slug("test_topic", rows_blocked, "2026-04-12")
    assert json.loads((topic / "meta.json").read_text())["audit_status"] == "BLOCKED"

    rows_clean = [{"slug": "test_topic", "ref_idx": 1, "severity": "OK",
                   "raw": "Real.", "notes": None}]
    audit_meta_writer.process_slug("test_topic", rows_clean, "2026-04-13")

    after = json.loads((topic / "meta.json").read_text())
    assert after["audit_status"] == "OK", "remediation must overwrite BLOCKED → OK"
    assert after["publication_allowed"] is True
    assert after["audit_date"] == "2026-04-13"
    assert after["audit_issues"] == []


def test_process_slug_idempotent_no_op_on_re_run(tmp_path, monkeypatch):
    import audit_meta_writer
    import time
    posts_dir = tmp_path / "Posts"
    topic = posts_dir / "test_topic"
    topic.mkdir(parents=True)
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    rows = [{"slug": "test_topic", "ref_idx": 1, "severity": "DOI_WRONG",
             "raw": "Wrong.", "notes": None}]
    audit_meta_writer.process_slug("test_topic", rows, "2026-04-12")
    mtime_before = (topic / "meta.json").stat().st_mtime
    time.sleep(0.01)  # ensure mtime resolution would catch a write

    msg = audit_meta_writer.process_slug("test_topic", rows, "2026-04-12")
    assert "already up-to-date" in msg
    mtime_after = (topic / "meta.json").stat().st_mtime
    assert mtime_after == mtime_before, "no-op must not touch file mtime"


def test_process_slug_dry_run_does_not_write(tmp_path, monkeypatch):
    import audit_meta_writer
    posts_dir = tmp_path / "Posts"
    topic = posts_dir / "test_topic"
    topic.mkdir(parents=True)
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    rows = [{"slug": "test_topic", "ref_idx": 1, "severity": "DOI_FABRICATED",
             "raw": "Fake.", "notes": None}]
    msg = audit_meta_writer.process_slug("test_topic", rows, "2026-04-12", dry_run=True)
    assert "would-write" in msg
    assert not (topic / "meta.json").exists()


def test_process_slug_missing_topic_dir_returns_warning(tmp_path, monkeypatch):
    import audit_meta_writer
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    rows = [{"slug": "nonexistent_topic", "ref_idx": 1, "severity": "OK",
             "raw": "ok", "notes": None}]
    msg = audit_meta_writer.process_slug("nonexistent_topic", rows, "2026-04-12")
    assert "missing-topic-dir" in msg


# ── #40 — audit_issues sort ────────────────────────────────────────────────


def test_build_audit_fields_sorts_issues_by_ref_idx():
    """Forward-brittle guard: if researcher ever re-sorts the audit JSON
    (e.g. by severity-first for diagnostic display), the order-sensitive
    `_audit_fields_match` would produce spurious re-writes. The sort in
    build_audit_fields pins the invariant explicitly."""
    from audit_meta_writer import build_audit_fields
    rows = [
        {"ref_idx": 5, "severity": "DOI_WRONG", "raw": "ref5", "notes": None},
        {"ref_idx": 2, "severity": "DOI_FABRICATED", "raw": "ref2", "notes": None},
        {"ref_idx": 1, "severity": "OK", "raw": "ref1", "notes": None},
        {"ref_idx": 3, "severity": "DOI_MISATTRIBUTED", "raw": "ref3", "notes": None},
    ]
    fields = build_audit_fields(rows, "2026-04-12")
    # OK row excluded; remaining 3 sorted by ref_idx ascending
    assert [i["ref_idx"] for i in fields["audit_issues"]] == [2, 3, 5]


# ── fetch_error projection ────────────────────────────────────────────────


def test_trim_issue_for_meta_includes_fetch_error_when_present():
    """The iOS UI wants to surface 'network was down during this audit'
    messaging without re-running the audit. Truncated to 120 chars to
    keep meta.json compact."""
    from audit_meta_writer import trim_issue_for_meta
    row = {
        "ref_idx": 3,
        "severity": "VERIFICATION_UNAVAILABLE",
        "raw": "Smith 2024.",
        "notes": "Network failure",
        "fetch_error": "<urlopen error [Errno -3] Temporary failure in name resolution>",
    }
    trimmed = trim_issue_for_meta(row)
    assert "fetch_error" in trimmed
    assert "Temporary failure" in trimmed["fetch_error"]


def test_trim_issue_for_meta_truncates_long_fetch_error():
    from audit_meta_writer import trim_issue_for_meta
    row = {
        "ref_idx": 1,
        "severity": "VERIFICATION_UNAVAILABLE",
        "raw": "X.",
        "notes": None,
        "fetch_error": "A" * 500,
    }
    trimmed = trim_issue_for_meta(row)
    assert len(trimmed["fetch_error"]) == 120


def test_trim_issue_for_meta_omits_fetch_error_when_absent():
    from audit_meta_writer import trim_issue_for_meta
    row = {"ref_idx": 1, "severity": "OK", "raw": "X.", "notes": None}
    trimmed = trim_issue_for_meta(row)
    assert "fetch_error" not in trimmed


# ── #39 refresh_audit_meta ────────────────────────────────────────────────


def _make_topic_with_draft(tmp_path, slug, draft_text):
    """Build a Posts/<slug>/en/draft.txt under tmp_path and return the topic dir."""
    topic = tmp_path / "Posts" / slug
    en = topic / "en"
    en.mkdir(parents=True)
    (en / "draft.txt").write_text(draft_text, encoding="utf-8")
    return topic


def _patch_verify_for_refresh(monkeypatch, *, severities):
    """Stub `contentprinter.verify_citations` to return controllable rows.

    `severities` is a list of strings; the helper builds one row per severity
    with sequential ref_idx values starting at 1, then makes the imported
    `verify_citations` symbol return that list when called from
    `refresh_audit_meta`. We patch where the symbol is RESOLVED, not where
    it's defined — refresh_audit_meta does a lazy `from contentprinter.verify
    import verify_citations` inside its body, so we monkeypatch the
    underlying module attribute and let the import resolution find the stub.
    """
    import contentprinter.verify as cv

    def fake_verify(draft, *, slug=""):
        return [
            {
                "slug": slug,
                "ref_idx": idx,
                "raw": f"Ref {idx}.",
                "severity": sev,
                "draft": {},
                "fetched": None,
                "verify": {},
                "notes": None,
            }
            for idx, sev in enumerate(severities, 1)
        ]

    monkeypatch.setattr(cv, "verify_citations", fake_verify)


def test_refresh_audit_meta_overwrites_stale_audit_after_remediation(tmp_path, monkeypatch):
    """The #39 core regression case: a remediation pass dropped a
    fabricated citation from draft.txt; refresh_audit_meta picks up the
    new state and overwrites the stale BLOCKED audit_issues with the new
    OK status. This is what frontend-writer's #31 workflow needs to
    avoid the stale-index drift that the joint smoke caught."""
    import audit_meta_writer
    import json

    posts_dir = tmp_path / "Posts"
    topic = _make_topic_with_draft(
        tmp_path,
        "test_remediated",
        "REFERENCES:\n1. Real Author A. (2024). Real Paper. Real J.\n",
    )
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    # Pre-stamp meta.json with the stale BLOCKED state
    stale_meta = {
        "post_number": 1,
        "topic_slug": "test_remediated",
        "audit_status": "BLOCKED",
        "audit_date": "2026-04-12",
        "publication_allowed": False,
        "audit_issues": [
            {"ref_idx": 1, "severity": "DOI_FABRICATED",
             "raw": "Fake B. (2024).", "notes": "fabricated"},
        ],
    }
    (topic / "meta.json").write_text(json.dumps(stale_meta), encoding="utf-8")

    # Now stub verify_citations to report the post is clean (post-remediation)
    _patch_verify_for_refresh(monkeypatch, severities=["OK"])

    msg = audit_meta_writer.refresh_audit_meta("test_remediated")
    assert "OK" in msg
    assert "refreshed" in msg

    after = json.loads((topic / "meta.json").read_text())
    assert after["audit_status"] == "OK"
    assert after["publication_allowed"] is True
    assert after["audit_issues"] == []
    # Pre-existing fields preserved
    assert after["post_number"] == 1
    assert after["topic_slug"] == "test_remediated"


def test_refresh_audit_meta_idempotent_no_op_on_re_call(tmp_path, monkeypatch):
    """After a successful refresh, calling refresh_audit_meta again with
    the same draft and verification result should be a no-op (no file
    write, no mtime touch). This makes the helper safe to call from
    automation that may invoke it more than once per remediation."""
    import audit_meta_writer
    import json
    import time as _time

    posts_dir = tmp_path / "Posts"
    topic = _make_topic_with_draft(
        tmp_path,
        "test_idempotent",
        "REFERENCES:\n1. Smith J. (2024). Test. J Test.\n",
    )
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)
    _patch_verify_for_refresh(monkeypatch, severities=["DOI_WRONG"])

    audit_meta_writer.refresh_audit_meta("test_idempotent")
    mtime_before = (topic / "meta.json").stat().st_mtime
    _time.sleep(0.01)

    msg = audit_meta_writer.refresh_audit_meta("test_idempotent")
    assert "already up-to-date" in msg
    mtime_after = (topic / "meta.json").stat().st_mtime
    assert mtime_after == mtime_before, "no-op must not touch file mtime"


def test_refresh_audit_meta_missing_draft_returns_error(tmp_path, monkeypatch):
    import audit_meta_writer
    posts_dir = tmp_path / "Posts"
    topic = posts_dir / "test_no_draft"
    (topic / "en").mkdir(parents=True)
    # No draft.txt created
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    msg = audit_meta_writer.refresh_audit_meta("test_no_draft")
    assert "missing-draft" in msg


def test_refresh_audit_meta_missing_topic_dir_returns_error(tmp_path, monkeypatch):
    import audit_meta_writer
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)

    msg = audit_meta_writer.refresh_audit_meta("nonexistent_slug")
    assert "missing-topic-dir" in msg


def test_refresh_audit_meta_dry_run_does_not_write(tmp_path, monkeypatch):
    import audit_meta_writer
    import json

    posts_dir = tmp_path / "Posts"
    topic = _make_topic_with_draft(
        tmp_path,
        "test_dryrun",
        "REFERENCES:\n1. Smith J. (2024). Test. J Test.\n",
    )
    monkeypatch.setattr(audit_meta_writer, "POSTS_DIR", posts_dir)
    _patch_verify_for_refresh(monkeypatch, severities=["DOI_FABRICATED"])

    msg = audit_meta_writer.refresh_audit_meta("test_dryrun", dry_run=True)
    assert "would-refresh" in msg
    assert not (topic / "meta.json").exists()
