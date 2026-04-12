"""Offline tests for pdf_downloader — no network."""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


def test_existing_is_valid_accepts_pdf_magic(tmp_path):
    from pdf_downloader import _existing_is_valid
    good = tmp_path / "good.pdf"
    good.write_bytes(b"%PDF-1.4\nfake body\n%%EOF")
    assert _existing_is_valid(good)


def test_existing_is_valid_rejects_html_fallback(tmp_path):
    from pdf_downloader import _existing_is_valid
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"<!doctype html><html><body>Access denied</body></html>")
    assert not _existing_is_valid(bad)


def test_existing_is_valid_rejects_missing_and_empty(tmp_path):
    from pdf_downloader import _existing_is_valid
    missing = tmp_path / "missing.pdf"
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    assert not _existing_is_valid(missing)
    assert not _existing_is_valid(empty)


def test_process_reference_skips_non_ok_status(tmp_path):
    from pdf_downloader import _process_reference
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    log = {}
    ref = {"ref_idx": 1, "status": "unresolved", "citation": "x", "pdf_url": None}
    msg = _process_reference(None, "fake_slug", ref, pdfs_dir, log,
                             dry_run=True, force=False, delay=0)
    assert "skip" in msg
    assert log["ref01"]["status"] == "skipped"


def test_process_reference_dry_run_logs_planned(tmp_path):
    from pdf_downloader import _process_reference
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    log = {}
    ref = {"ref_idx": 2, "status": "ok", "citation": "Smith 2024",
           "pdf_url": "https://example.com/fake.pdf"}
    msg = _process_reference(None, "fake_slug", ref, pdfs_dir, log,
                             dry_run=True, force=False, delay=0)
    assert "would-fetch" in msg
    assert log["ref02"]["status"] == "planned"


def test_process_reference_reuses_existing_valid_pdf(tmp_path):
    from pdf_downloader import _process_reference
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    existing = pdfs_dir / "ref03.pdf"
    existing.write_bytes(b"%PDF-1.4\npre-existing\n%%EOF")
    log = {}
    ref = {"ref_idx": 3, "status": "ok", "citation": "Doe 2023",
           "pdf_url": "https://example.com/real.pdf"}
    msg = _process_reference(None, "fake_slug", ref, pdfs_dir, log,
                             dry_run=False, force=False, delay=0)
    assert "already-downloaded" in msg
    assert log["ref03"]["status"] == "ok"
    assert log["ref03"]["reused_existing"] is True


def test_rewrite_pmc_direct_to_europepmc():
    from pdf_downloader import _rewrite_pmc_to_europepmc
    cases = [
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC2931407/pdf/",
         "https://europepmc.org/articles/PMC2931407?pdf=render"),
        ("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5867436/pdf/",
         "https://europepmc.org/articles/PMC5867436?pdf=render"),
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/pdf/nihms12345.pdf",
         "https://europepmc.org/articles/PMC1234567?pdf=render"),
        ("http://ncbi.nlm.nih.gov/pmc/articles/PMC9/pdf/",
         "https://europepmc.org/articles/PMC9?pdf=render"),
    ]
    for input_url, expected in cases:
        assert _rewrite_pmc_to_europepmc(input_url) == expected, (
            f"failed on {input_url}: got {_rewrite_pmc_to_europepmc(input_url)!r}"
        )


def test_rewrite_pmc_leaves_non_pmc_urls_untouched():
    from pdf_downloader import _rewrite_pmc_to_europepmc
    untouched = [
        "https://europepmc.org/articles/PMC2931407?pdf=render",
        "https://www.strongerbyscience.com/article.pdf",
        "https://link.springer.com/content/pdf/10.1007/s40279.pdf",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
        "https://pmc.ncbi.nlm.nih.gov/",
        "",
    ]
    for url in untouched:
        assert _rewrite_pmc_to_europepmc(url) == url, (
            f"unexpectedly rewrote {url!r}"
        )


def test_europepmc_ua_is_browser_form_and_identified_ua_is_not():
    """Sanity check the per-host UA override doesn't leak into the default."""
    from pdf_downloader import _EUROPEPMC_UA, PDF_DOWNLOADER_UA
    assert "Mozilla/5.0" in _EUROPEPMC_UA
    assert "Chrome" in _EUROPEPMC_UA
    assert "CentralStrengthKB" not in _EUROPEPMC_UA
    assert "CentralStrengthKB" in PDF_DOWNLOADER_UA
    assert "Mozilla" not in PDF_DOWNLOADER_UA


def test_prior_failure_is_stale_missing_timestamp_is_stale():
    from pdf_downloader import _prior_failure_is_stale
    assert _prior_failure_is_stale({}, 168) is True
    assert _prior_failure_is_stale({"status": "failed"}, 168) is True
    assert _prior_failure_is_stale({"attempted_at": "not-a-date"}, 168) is True


def test_prior_failure_is_stale_recent_is_fresh():
    from datetime import datetime, timedelta
    from pdf_downloader import _prior_failure_is_stale
    recent = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
    assert _prior_failure_is_stale({"attempted_at": recent}, 168) is False


def test_prior_failure_is_stale_old_is_stale():
    from datetime import datetime, timedelta
    from pdf_downloader import _prior_failure_is_stale
    old = (datetime.now() - timedelta(hours=200)).isoformat(timespec="seconds")
    assert _prior_failure_is_stale({"attempted_at": old}, 168) is True


def test_process_reference_respects_fresh_sticky_failure(tmp_path):
    """A recent prior failure (< retry_after_hours) should short-circuit."""
    from datetime import datetime
    from pdf_downloader import _process_reference
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    log = {
        "ref05": {
            "status": "failed",
            "reason": "http error: 403",
            "url": "https://example.com/paper.pdf",
            "attempted_at": datetime.now().isoformat(timespec="seconds"),
        }
    }
    ref = {
        "ref_idx": 5,
        "status": "ok",
        "citation": "Smith 2024",
        "pdf_url": "https://example.com/paper.pdf",
    }
    msg = _process_reference(None, "slug", ref, pdfs_dir, log,
                             dry_run=False, force=False, delay=0,
                             retry_after_hours=168)
    assert "prior-failure" in msg
    assert log["ref05"]["status"] == "failed"


def test_process_reference_auto_retries_stale_sticky_failure(tmp_path):
    """A prior failure older than retry_after_hours should fall through
    to the fetch path. In dry-run mode we just see the planned line."""
    from datetime import datetime, timedelta
    from pdf_downloader import _process_reference
    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    stale_ts = (datetime.now() - timedelta(hours=200)).isoformat(timespec="seconds")
    log = {
        "ref06": {
            "status": "failed",
            "reason": "http error: 503",
            "url": "https://example.com/paper.pdf",
            "attempted_at": stale_ts,
        }
    }
    ref = {
        "ref_idx": 6,
        "status": "ok",
        "citation": "Doe 2024",
        "pdf_url": "https://example.com/paper.pdf",
    }
    msg = _process_reference(None, "slug", ref, pdfs_dir, log,
                             dry_run=True, force=False, delay=0,
                             retry_after_hours=168)
    assert "would-fetch" in msg
    assert log["ref06"]["status"] == "planned"


def test_load_url_manifest_has_expected_shape():
    from pdf_downloader import load_url_manifest
    manifest = load_url_manifest()
    assert "_meta" in manifest
    assert "status_counts" in manifest["_meta"]
    ok_count = manifest["_meta"]["status_counts"]["ok"]
    actual_ok = 0
    for slug, refs in manifest.items():
        if slug == "_meta":
            continue
        for ref in refs:
            if ref.get("status") == "ok" and ref.get("pdf_url"):
                actual_ok += 1
    assert actual_ok == ok_count, f"manifest says {ok_count} ok but counted {actual_ok}"
