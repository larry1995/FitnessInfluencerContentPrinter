"""Integration tests for the F-0 verify gate wired into the singlepage CLI
path (task #49).

These tests exercise `_run_verify_gate_for_slug` and the `finalize_topic`
sidecar check directly — the pure-Python parts of the wiring — so they can
run without PIL font resolution or the full render pipeline. The actual
render loop is covered by existing single_page_generator tests.

`contentprinter.verify_citations` is monkeypatched with synthetic rows so
no network calls happen.
"""

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _row(severity: str, idx: int = 1) -> dict:
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


def _make_topic(tmp_path: Path, slug: str, draft_text: str = "BODY") -> Path:
    topic_dir = tmp_path / slug
    (topic_dir / "en").mkdir(parents=True)
    draft = topic_dir / "en" / "draft.txt"
    draft.write_text(draft_text, encoding="utf-8")
    return topic_dir


# ── _run_verify_gate_for_slug ─────────────────────────────────────────────


def test_gate_writes_done_sidecar_on_all_ok(tmp_path, monkeypatch):
    from single_page_generator import _run_verify_gate_for_slug
    _patch_verify(monkeypatch, [_row("OK", 1)])
    topic_dir = _make_topic(tmp_path, "nutrition_x")
    counts = {"done": 0, "warn": 0, "blocked": 0, "skipped": 0}
    _run_verify_gate_for_slug(
        slug="nutrition_x",
        draft_path=topic_dir / "en" / "draft.txt",
        topic_dir=topic_dir,
        gate_active=True,
        gate_counts=counts,
    )
    assert (topic_dir / "_done.json").exists()
    assert not (topic_dir / "_blocked.json").exists()
    assert not (topic_dir / "_warn.json").exists()
    assert counts["done"] == 1
    payload = json.loads((topic_dir / "_done.json").read_text())
    assert payload["status"] == "done"
    assert payload["counts"]["verified"] == 1


def test_gate_writes_blocked_sidecar_on_doi_fabricated(tmp_path, monkeypatch):
    from single_page_generator import _run_verify_gate_for_slug
    _patch_verify(monkeypatch, [_row("DOI_FABRICATED", 1), _row("OK", 2)])
    topic_dir = _make_topic(tmp_path, "supplements_fake")
    counts = {"done": 0, "warn": 0, "blocked": 0, "skipped": 0}
    _run_verify_gate_for_slug(
        slug="supplements_fake",
        draft_path=topic_dir / "en" / "draft.txt",
        topic_dir=topic_dir,
        gate_active=True,
        gate_counts=counts,
    )
    assert (topic_dir / "_blocked.json").exists()
    assert not (topic_dir / "_done.json").exists()
    assert counts["blocked"] == 1
    payload = json.loads((topic_dir / "_blocked.json").read_text())
    assert payload["status"] == "verification_failed"
    assert payload["counts"]["blocked"] == 1


def test_gate_writes_warn_sidecar_on_pending_only(tmp_path, monkeypatch):
    from single_page_generator import _run_verify_gate_for_slug
    _patch_verify(monkeypatch, [_row("VERIFICATION_UNAVAILABLE", 1), _row("OK", 2)])
    topic_dir = _make_topic(tmp_path, "training_x")
    counts = {"done": 0, "warn": 0, "blocked": 0, "skipped": 0}
    _run_verify_gate_for_slug(
        slug="training_x",
        draft_path=topic_dir / "en" / "draft.txt",
        topic_dir=topic_dir,
        gate_active=True,
        gate_counts=counts,
    )
    assert (topic_dir / "_warn.json").exists()
    assert not (topic_dir / "_blocked.json").exists()
    assert counts["warn"] == 1
    payload = json.loads((topic_dir / "_warn.json").read_text())
    assert payload["status"] == "verification_pending_review"
    assert payload["counts"]["pending_review"] == 1


def test_gate_skipped_when_both_flags_set(tmp_path, monkeypatch):
    """Escape hatch writes _skip_verify.json instead of running the gate."""
    from single_page_generator import _run_verify_gate_for_slug
    import contentprinter.verify as vmod

    called = []
    monkeypatch.setattr(
        vmod, "verify_citations",
        lambda *a, **kw: called.append(1) or [],
    )
    topic_dir = _make_topic(tmp_path, "supplements_x")
    counts = {"done": 0, "warn": 0, "blocked": 0, "skipped": 0}
    _run_verify_gate_for_slug(
        slug="supplements_x",
        draft_path=topic_dir / "en" / "draft.txt",
        topic_dir=topic_dir,
        gate_active=False,
        gate_counts=counts,
    )
    assert called == []  # gate did NOT call verify_citations
    assert (topic_dir / "_skip_verify.json").exists()
    assert not (topic_dir / "_done.json").exists()
    assert not (topic_dir / "_blocked.json").exists()
    assert counts["skipped"] == 1


def test_gate_clears_stale_sidecar_from_previous_run(tmp_path, monkeypatch):
    """A slug that previously blocked but is now OK must shed _blocked.json."""
    from single_page_generator import _run_verify_gate_for_slug
    _patch_verify(monkeypatch, [_row("OK", 1)])
    topic_dir = _make_topic(tmp_path, "nutrition_fixed")
    # Seed a stale blocked sidecar from a "previous run".
    (topic_dir / "_blocked.json").write_text('{"status": "verification_failed"}')

    counts = {"done": 0, "warn": 0, "blocked": 0, "skipped": 0}
    _run_verify_gate_for_slug(
        slug="nutrition_fixed",
        draft_path=topic_dir / "en" / "draft.txt",
        topic_dir=topic_dir,
        gate_active=True,
        gate_counts=counts,
    )
    assert not (topic_dir / "_blocked.json").exists()
    assert (topic_dir / "_done.json").exists()
    assert counts["done"] == 1


def test_gate_fails_closed_on_unexpected_exception(tmp_path, monkeypatch):
    """If verify_citations itself blows up, the gate writes a blocked sidecar
    with a gate_error field — no silent pass-through."""
    from single_page_generator import _run_verify_gate_for_slug
    import contentprinter.verify as vmod

    def boom(draft, slug=""):
        raise RuntimeError("audit module exploded")

    monkeypatch.setattr(vmod, "verify_citations", boom)
    topic_dir = _make_topic(tmp_path, "nutrition_kaboom")
    counts = {"done": 0, "warn": 0, "blocked": 0, "skipped": 0}
    _run_verify_gate_for_slug(
        slug="nutrition_kaboom",
        draft_path=topic_dir / "en" / "draft.txt",
        topic_dir=topic_dir,
        gate_active=True,
        gate_counts=counts,
    )
    assert (topic_dir / "_blocked.json").exists()
    payload = json.loads((topic_dir / "_blocked.json").read_text())
    assert payload["status"] == "verification_failed"
    assert "RuntimeError" in payload["gate_error"]
    assert counts["blocked"] == 1


# ── finalize_topic honors the sidecar ─────────────────────────────────────


def test_finalize_topic_skips_blocked_slug(tmp_path, monkeypatch):
    """A slug with _blocked.json must not promote its PNG to Posts/."""
    import output_layout
    work_dir = tmp_path / "work"
    posts_dir = tmp_path / "Posts"
    work_dir.mkdir()
    monkeypatch.setattr(output_layout, "WORK_DIR", work_dir)
    monkeypatch.setattr(output_layout, "OUTPUT_DIR", posts_dir)

    slug_dir = work_dir / "nutrition_fake"
    (slug_dir / "en").mkdir(parents=True)
    (slug_dir / "en" / "single_page.png").write_bytes(b"\x89PNG fake")
    (slug_dir / "_blocked.json").write_text('{"status": "verification_failed"}')

    result = output_layout.finalize_topic("nutrition_fake")
    assert result.skipped_reason == "blocked-by-verify"
    assert not (posts_dir / "nutrition" / "fake.png").exists()
    # PNG stays in work/ for inspection.
    assert (slug_dir / "en" / "single_page.png").exists()


def test_finalize_topic_promotes_ok_slug(tmp_path, monkeypatch):
    import output_layout
    work_dir = tmp_path / "work"
    posts_dir = tmp_path / "Posts"
    work_dir.mkdir()
    monkeypatch.setattr(output_layout, "WORK_DIR", work_dir)
    monkeypatch.setattr(output_layout, "OUTPUT_DIR", posts_dir)

    slug_dir = work_dir / "nutrition_protein_timing"
    (slug_dir / "en").mkdir(parents=True)
    (slug_dir / "en" / "single_page.png").write_bytes(b"\x89PNG fake")
    (slug_dir / "_done.json").write_text('{"status": "done"}')

    result = output_layout.finalize_topic("nutrition_protein_timing")
    assert result.skipped_reason is None
    assert result.png_moved is True
    assert result.category == "nutrition"


def test_summarize_reports_held_slugs(tmp_path, monkeypatch):
    from output_layout import summarize, FinalizeResult
    results = [
        FinalizeResult(slug="a", category="nutrition", clean_slug="a",
                       png_moved=True, zh_md_written=False, pdfs_moved=0),
        FinalizeResult(slug="b", category="", clean_slug="",
                       png_moved=False, zh_md_written=False, pdfs_moved=0,
                       skipped_reason="blocked-by-verify"),
    ]
    text = summarize(results)
    assert "Finalized 1 topics" in text
    assert "HELD 1 topic" in text
    assert "- b" in text


def test_finalize_all_walks_mixed_sidecar_state(tmp_path, monkeypatch):
    """finalize_all promotes OK slugs and skips blocked ones in a single pass."""
    import output_layout
    work_dir = tmp_path / "work"
    posts_dir = tmp_path / "Posts"
    work_dir.mkdir()
    monkeypatch.setattr(output_layout, "WORK_DIR", work_dir)
    monkeypatch.setattr(output_layout, "OUTPUT_DIR", posts_dir)

    ok = work_dir / "nutrition_protein_timing"
    (ok / "en").mkdir(parents=True)
    (ok / "en" / "single_page.png").write_bytes(b"\x89PNG ok")
    (ok / "_done.json").write_text("{}")

    blocked = work_dir / "supplements_fake_one"
    (blocked / "en").mkdir(parents=True)
    (blocked / "en" / "single_page.png").write_bytes(b"\x89PNG blocked")
    (blocked / "_blocked.json").write_text("{}")

    results = output_layout.finalize_all()
    by_slug = {r.slug: r for r in results}
    assert by_slug["nutrition_protein_timing"].png_moved is True
    assert by_slug["supplements_fake_one"].skipped_reason == "blocked-by-verify"
