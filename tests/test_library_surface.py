"""Tests for the `contentprinter` library package (Task #16).

These test the public surface only — NOT the internal `src/*` modules.
If a test here breaks, it's a compatibility-breaking change and
API_SURFACE.md needs a version bump.
"""

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def test_package_exposes_expected_symbols():
    import contentprinter
    assert contentprinter.__version__ == "0.5.0"
    required = {
        "generate_draft",
        "generate_grounded_draft",
        "parse_draft_text",
        "generate_chinese_from_english",
        "is_llm_configured",
        "render_page",
        "download_references",
        "verify_citations",
        "is_blocking",
        "run_verify_gate",
        "refresh_audit_meta",
        "scrape_for_topic",
        "TopicScraperError",
    }
    assert required.issubset(set(contentprinter.__all__))
    for name in required:
        # TopicScraperError is a class; everything else should be callable too.
        assert callable(getattr(contentprinter, name)), f"{name} must be callable"


def test_parse_draft_text_returns_render_ready_post():
    """The § 4 consumer flow must work without reaching into src.*."""
    import contentprinter
    draft_text = (
        "=" * 60 + "\n"
        "POST #1 — NUTRITION\n"
        "Source: Example Source\n"
        + "=" * 60 + "\n\n"
        "CAPTION:\n"
        + "-" * 40 + "\n"
        "PROTEIN TIMING — MYTH OR REALITY?\n\n"
        "Protein timing is less important than total daily intake.\n\n"
        "1. TOTAL INTAKE MATTERS MOST\n"
        "Hit 1.6-2.2g per kg bodyweight daily. The anabolic window myth is busted.\n\n"
        "2. DISTRIBUTION IS SECONDARY\n"
        "Spread across 3-5 meals is fine. Exact timing within +/- 2 hours is irrelevant.\n\n"
        + "-" * 40 + "\n\n"
        "REFERENCES:\n"
        "1. Schoenfeld BJ et al. (2013). J Int Soc Sports Nutr, 10(1):5. "
        "doi:10.1186/1550-2783-10-5\n"
    )
    post = contentprinter.parse_draft_text(draft_text)
    assert isinstance(post, dict)
    assert post.get("title")
    assert "layout" in post
    assert isinstance(post.get("references"), list)


def test_parse_draft_text_rejects_empty():
    import contentprinter
    for bad in ("", "   ", None, 42):
        try:
            contentprinter.parse_draft_text(bad)
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError(f"expected error on {bad!r}")


def test_generate_draft_returns_expected_post_shape():
    import contentprinter
    article = {
        "title": "Creatine Timing Is Irrelevant",
        "url": "https://example.com/creatine",
        "source": "Example Source",
        "topic": "nutrition",
        "summary": "Timing of creatine ingestion does not affect strength outcomes.",
        "full_text": (
            "Research shows 5g of creatine monohydrate daily is sufficient. "
            "A 2024 meta-analysis of 18 trials found no significant difference "
            "between pre-workout, post-workout, or anytime ingestion. "
            "Key findings: take it consistently, any time of day. "
            "Dose matters: 3-5g daily."
        ),
    }
    post = contentprinter.generate_draft(article)
    required_fields = {
        "post_number", "topic", "source", "source_url", "title",
        "caption", "key_points", "carousel_slides", "suggested_visual",
        "drafted_at",
    }
    assert required_fields.issubset(set(post.keys()))
    assert post["title"] == "Creatine Timing Is Irrelevant"
    assert post["topic"] == "nutrition"
    assert len(post["caption"]) > 100
    assert isinstance(post["carousel_slides"], list)
    assert len(post["carousel_slides"]) >= 2


def test_generate_draft_rejects_empty_article():
    import contentprinter
    try:
        contentprinter.generate_draft({})
    except ValueError as e:
        assert "title" in str(e).lower()
    else:
        raise AssertionError("expected ValueError for empty article")


def test_generate_chinese_returns_none_without_api_key(monkeypatch):
    import contentprinter
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import llm_client
    monkeypatch.setattr(llm_client, "_load_dotenv_key", lambda: None)
    result = contentprinter.generate_chinese_from_english(
        "This is a sufficiently long English draft to pass the 50-char minimum check. "
        "It contains a references block for completeness."
    )
    assert result is None


def test_generate_chinese_rejects_short_input():
    import contentprinter
    try:
        contentprinter.generate_chinese_from_english("tiny")
    except ValueError as e:
        assert "50" in str(e) or "non-trivial" in str(e)
    else:
        raise AssertionError("expected ValueError for short input")


def test_download_references_skips_non_ok_entries(tmp_path):
    import contentprinter
    refs = [
        {"ref_idx": 1, "status": "unresolved", "citation": "x", "pdf_url": None},
        {"ref_idx": 2, "status": "pmid_only", "citation": "y", "pmid": "12345"},
        {"ref_idx": 3, "status": "no_doi", "citation": "z"},
    ]
    downloaded = contentprinter.download_references(refs, out_dir=tmp_path)
    assert downloaded == []
    assert (tmp_path / "download_log.json").exists()


def test_download_references_reuses_existing_valid_pdf(tmp_path):
    import contentprinter
    existing = tmp_path / "ref04.pdf"
    existing.write_bytes(b"%PDF-1.4\nfake content\n%%EOF")
    refs = [{
        "ref_idx": 4,
        "status": "ok",
        "citation": "Smith 2024",
        "pdf_url": "https://example.com/real.pdf",
    }]
    downloaded = contentprinter.download_references(refs, out_dir=tmp_path)
    assert len(downloaded) == 1
    assert downloaded[0].resolve() == existing.resolve()


def test_render_page_writes_png_to_given_path(tmp_path):
    import contentprinter
    post = {
        "title": "Test Post",
        "topic": "nutrition",
        "topic_emoji": "🥩",
        "intro_text": "Short intro paragraph for test rendering.",
        "key_stat": "",
        "sections": [],
        "numbered_points": [
            {"headline": "Point A", "body": "Body text for point A."},
            {"headline": "Point B", "body": "Body text for point B."},
        ],
        "extra_sections": [],
        "practical_guide": [],
        "summary_text": "",
        "references": [],
        "layout": "default",
        "evidence_info": {},
        "hashtags": [],
        "cta": "",
        "suggested_visual": "",
    }
    out = tmp_path / "test.png"
    result = contentprinter.render_page(post, output_path=out)
    assert result.exists()
    assert result.suffix == ".png"
    assert result.stat().st_size > 1000
    with open(result, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
