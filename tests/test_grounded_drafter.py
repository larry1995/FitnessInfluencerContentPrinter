"""Tests for the grounded LLM drafter (Task #35).

Network-isolated: every test injects a fake `verify_fn` and fake LLM
callables, so no Crossref/PubMed/Anthropic round-trips ever happen.
The fake `verify_fn` mirrors the real `verify_citations` row shape so
the byte-check + Layer B paths exercise the same code as production.

Three worked examples from `audits/grounded_drafter_design.md` §7 are
covered as end-to-end fixtures: rich-citation, borderline-1-citation,
zero-citation. Plus per-component unit tests for extraction, prompt
substitution, byte-check, and the three None paths.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


# ── Fakes ─────────────────────────────────────────────────────────────────


def _ok_row(*, ref_idx: int, raw: str, doi=None, pmid=None, first_author="Smith J", year=2024,
            title="Effects of Training", journal="J Sport Sci"):
    return {
        "ref_idx": ref_idx,
        "raw": raw,
        "severity": "OK",
        "draft": {
            "first_author": first_author,
            "year": year,
            "title": title,
            "journal": journal,
            "doi": doi,
            "pmid": pmid,
        },
        "fetched": {
            "first_author": first_author,
            "year": year,
            "title": title,
            "journal": journal,
            "pmid": pmid,
        },
        "verify": {"author_match": True, "year_match": True, "title_overlap": 1.0, "journal_match": True},
        "notes": None,
    }


def _blocking_row(ref_idx: int, raw: str):
    return {
        "ref_idx": ref_idx,
        "raw": raw,
        "severity": "DOI_FABRICATED",
        "draft": {"doi": "10.0000/fake"},
        "fetched": None,
        "verify": {},
        "notes": "DOI does not exist",
    }


def _make_verify_fn(*, by_doi=None, by_pmid=None, default_ok=False):
    """Build a verify_fn stub that returns OK rows for known DOIs/PMIDs."""
    by_doi = by_doi or {}
    by_pmid = by_pmid or {}

    def fake_verify(draft_text, *, slug=""):
        import re as _re
        from audits import _citation_audit as _ca  # noqa
        # Simple inline match — the synthetic single-ref drafts contain one ref
        m = _re.search(r"doi:(\S+)", draft_text)
        if m:
            doi = m.group(1).rstrip(".,;")
            if doi in by_doi:
                return [by_doi[doi]]
            if default_ok:
                return [_ok_row(ref_idx=1, raw="X", doi=doi)]
            return [_blocking_row(1, draft_text)]
        m = _re.search(r"PMID:(\d+)", draft_text)
        if m:
            pmid = m.group(1)
            if pmid in by_pmid:
                return [by_pmid[pmid]]
            return [_blocking_row(1, draft_text)]
        return []

    return fake_verify


# Patch the import path so `from audits import _citation_audit` works
@pytest.fixture(autouse=True)
def _ensure_audits_on_path():
    audits = _REPO / "audits"
    audits_str = str(audits)
    added = False
    if audits_str not in sys.path:
        sys.path.insert(0, audits_str)
        added = True
    # Provide a stub `audits` package so the `from audits import` in fakes works
    import types
    if "audits" not in sys.modules:
        pkg = types.ModuleType("audits")
        pkg.__path__ = [audits_str]
        sys.modules["audits"] = pkg
    yield
    if added and audits_str in sys.path:
        sys.path.remove(audits_str)


# ── Allow-list extraction ─────────────────────────────────────────────────


def test_structured_content_yields_one_citation():
    import grounded_drafter as gd
    article = {
        "title": "Creatine and Strength: A Meta-Analysis",
        "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
        "structured_content": {
            "pmid": "12345678",
            "doi": "10.3390/nu17172748",
            "authors": ["Forbes SC", "Candow DG"],
            "journal": "Nutrients",
            "year": "2025",
        },
        "full_text": "abstract body without inline DOIs",
    }
    allowed = gd.extract_allowed_citations(article, verify_fn=_make_verify_fn())
    assert len(allowed) == 1
    cit = allowed[0]
    assert cit["doi"] == "10.3390/nu17172748"
    assert cit["pmid"] == "12345678"
    assert cit["first_author"] == "Forbes SC"
    assert cit["year"] == 2025
    assert "Forbes SC et al. (2025)" in cit["citation_text"]
    assert "doi:10.3390/nu17172748" in cit["citation_text"]
    assert "PMID:12345678" in cit["citation_text"]


def test_inline_doi_extraction_only_accepts_ok_rows():
    import grounded_drafter as gd
    article = {
        "title": "RSS post with inline DOI",
        "full_text": "...as Helms et al. (2018) showed (doi:10.1519/JSC.0000000000002491)...",
    }
    by_doi = {
        "10.1519/JSC.0000000000002491": _ok_row(
            ref_idx=1,
            raw="Helms ER et al. (2018). Title.",
            doi="10.1519/JSC.0000000000002491",
            first_author="Helms ER",
            year=2018,
            title="Recommendations for Natural Bodybuilding Contest Preparation",
            journal="J Strength Cond Res",
        ),
    }
    allowed = gd.extract_allowed_citations(article, verify_fn=_make_verify_fn(by_doi=by_doi))
    assert len(allowed) == 1
    assert allowed[0]["source"] == "rss_inline_doi"
    assert allowed[0]["doi"] == "10.1519/JSC.0000000000002491"


def test_inline_doi_rejected_when_verify_returns_blocking():
    import grounded_drafter as gd
    article = {
        "title": "RSS post with fake inline DOI",
        "full_text": "...nonsense (doi:10.0000/fake-fake-fake)...",
    }
    allowed = gd.extract_allowed_citations(article, verify_fn=_make_verify_fn())
    assert allowed == []


def test_dedup_skips_duplicate_doi_across_sources():
    import grounded_drafter as gd
    article = {
        "title": "Paper",
        "structured_content": {
            "pmid": "12345678",
            "doi": "10.3390/nu17172748",
            "authors": ["Forbes SC"],
            "journal": "Nutrients",
            "year": "2025",
        },
        "full_text": "Body cites itself: doi:10.3390/nu17172748",
    }
    by_doi = {
        "10.3390/nu17172748": _ok_row(
            ref_idx=1, raw="X", doi="10.3390/nu17172748",
            first_author="Forbes SC", year=2025, title="Effects", journal="Nutrients",
        ),
    }
    allowed = gd.extract_allowed_citations(article, verify_fn=_make_verify_fn(by_doi=by_doi))
    assert len(allowed) == 1  # not 2
    assert allowed[0]["source"] == "pubmed_scraper"


def test_zero_citation_article_returns_empty_list():
    import grounded_drafter as gd
    article = {
        "title": "T-Nation Practitioner Post",
        "full_text": "Everyone knows squats are king. Just lift heavy.",
    }
    allowed = gd.extract_allowed_citations(article, verify_fn=_make_verify_fn())
    assert allowed == []


# ── Prompt building ───────────────────────────────────────────────────────


def test_excerpt_truncates_at_paragraph_boundary():
    import grounded_drafter as gd
    text = ("para1.\n\n" * 100) + "extra"
    out = gd._excerpt(text, max_chars=200)
    assert out.endswith("[...truncated, see source URL for full article]")
    assert "para1" in out


def test_excerpt_short_text_unchanged():
    import grounded_drafter as gd
    out = gd._excerpt("short", max_chars=100)
    assert out == "short"


def test_format_allowed_block_empty():
    import grounded_drafter as gd
    assert gd._format_allowed_block([]) == "[NO VERIFIED CITATIONS AVAILABLE FROM THIS SOURCE]"


def test_format_references_instruction_empty():
    import grounded_drafter as gd
    assert gd._format_references_instruction([]) == "[INSUFFICIENT_SOURCE_DATA]"


def test_build_prompt_substitutes_all_placeholders():
    import grounded_drafter as gd
    article = {
        "title": "Test Title",
        "url": "https://example.com/x",
        "source": "Example",
        "full_text": "Body text",
    }
    allowed = [
        {
            "citation_text": "Forbes SC et al. (2025). Effects. Nutrients. doi:10.3390/nu17172748",
            "doi": "10.3390/nu17172748",
            "pmid": None,
            "first_author": "Forbes SC",
            "year": 2025,
            "journal": "Nutrients",
            "title": "Effects",
            "source": "pubmed_scraper",
        }
    ]
    prompt = gd.build_grounded_prompt(article, allowed)
    assert "{allowed_citations_block}" not in prompt
    assert "{article_title}" not in prompt
    assert "{references_block_instruction}" not in prompt
    assert "Test Title" in prompt
    assert "https://example.com/x" in prompt
    assert "Forbes SC et al. (2025)" in prompt
    assert "Body text" in prompt


# ── Layer A byte-check ────────────────────────────────────────────────────


def _make_allowed(text: str) -> dict:
    return {
        "citation_text": text,
        "doi": None,
        "pmid": None,
        "first_author": "X",
        "year": 2024,
        "journal": "J",
        "title": "T",
        "source": "test",
    }


def test_byte_check_accepts_exact_match():
    import grounded_drafter as gd
    cit = "Forbes SC et al. (2025). Effects of Creatine. Nutrients. doi:10.3390/nu17172748"
    allowed = [_make_allowed(cit)]
    draft = f"... post body ...\n\nREFERENCES:\n1. {cit}\n"
    assert gd._all_refs_in_allowlist(draft, allowed) is True


def test_byte_check_rejects_extra_citation():
    import grounded_drafter as gd
    cit = "Forbes SC et al. (2025). Effects. Nutrients. doi:10.3390/nu17172748"
    fabricated = "Hallucinated J et al. (2099). Fake Title. Fake J. doi:10.0000/fake"
    allowed = [_make_allowed(cit)]
    draft = f"REFERENCES:\n1. {cit}\n2. {fabricated}\n"
    assert gd._all_refs_in_allowlist(draft, allowed) is False


def test_byte_check_strips_whitespace_before_compare():
    import grounded_drafter as gd
    cit = "Forbes SC et al. (2025). Effects. Nutrients. doi:10.3390/nu17172748"
    allowed = [_make_allowed(cit)]
    draft = f"REFERENCES:\n1.   {cit}   \n"
    assert gd._all_refs_in_allowlist(draft, allowed) is True


def test_byte_check_empty_refs_returns_true():
    import grounded_drafter as gd
    draft = "post with no references block at all"
    assert gd._all_refs_in_allowlist(draft, []) is True


# ── End-to-end worked examples ────────────────────────────────────────────


@pytest.fixture
def needs_research_dir(tmp_path, monkeypatch):
    """Redirect Posts/.needs_research/ to a tmp dir so tests don't write into the real Posts/."""
    import grounded_drafter as gd
    target = tmp_path / "needs_research"
    monkeypatch.setattr(gd, "NEEDS_RESEARCH_DIR", target)
    return target


def test_worked_example_rich_citation_success(needs_research_dir):
    """§7.1 — PubMed source with verified citation, LLM emits a clean draft."""
    import grounded_drafter as gd

    article = {
        "title": "Creatine and Strength",
        "url": "https://pubmed.ncbi.nlm.nih.gov/123/",
        "source": "PubMed",
        "structured_content": {
            "pmid": "12345678",
            "doi": "10.3390/nu17172748",
            "authors": ["Forbes SC"],
            "journal": "Nutrients",
            "year": "2025",
        },
        "full_text": "Abstract body.",
    }

    expected_cit = "Forbes SC et al. (2025). Creatine and Strength. Nutrients. doi:10.3390/nu17172748 PMID:12345678"
    fake_llm_output = (
        "💪 CREATINE WORKS\n\n"
        "Research is clear.\n\n"
        "1. EVIDENCE\nMeta-analysis confirms.\n\n"
        "PRACTICAL TAKEAWAYS:\n- Take 5g daily\n\n"
        "THE BOTTOM LINE: It works.\n\n"
        "REFERENCES:\n"
        f"1. {expected_cit}\n"
    )

    captured_prompts = []
    def fake_complete(prompt, *, temperature=0.5, **kw):
        captured_prompts.append((prompt, temperature))
        return fake_llm_output

    def fake_verify(draft_or_text, *, slug=""):
        return [_ok_row(ref_idx=1, raw=expected_cit, doi="10.3390/nu17172748",
                        pmid="12345678", first_author="Forbes SC", year=2025,
                        title="Creatine and Strength", journal="Nutrients")]

    result = gd.generate_grounded_draft(
        article,
        verify_fn=fake_verify,
        llm_complete=fake_complete,
        llm_is_configured=lambda: True,
        slug="creatine_test",
    )
    assert result is not None
    assert expected_cit in result
    assert len(captured_prompts) == 1
    assert captured_prompts[0][1] == 0.5
    # No needs_research signal on success
    assert not (needs_research_dir / "creatine_test.json").exists()


def test_worked_example_zero_citation_writes_signal(needs_research_dir):
    """§7.3 — Zero allow-list returns None and emits signal file."""
    import grounded_drafter as gd

    article = {
        "title": "Everyone Knows Squats Are King",
        "url": "https://www.t-nation.com/squats",
        "source": "T-Nation",
        "source_type": "rss",
        "full_text": "No DOIs anywhere just narrative.",
    }

    def fake_complete(prompt, **kw):
        raise AssertionError("LLM should never be called when allow-list is empty")

    result = gd.generate_grounded_draft(
        article,
        verify_fn=_make_verify_fn(),
        llm_complete=fake_complete,
        llm_is_configured=lambda: True,
        slug="training_squats_king",
    )
    assert result is None
    signal = needs_research_dir / "training_squats_king.json"
    assert signal.exists()
    payload = json.loads(signal.read_text())
    assert payload["slug"] == "training_squats_king"
    assert payload["extraction_breakdown"]["inline_doi_matches"] == 0
    assert payload["extraction_breakdown"]["structured_content_doi"] is False


def test_drop_path_when_llm_emits_hallucinated_ref(needs_research_dir):
    """§5 — LLM ignores allow-list constraint, retry, fail, drop."""
    import grounded_drafter as gd

    article = {
        "title": "Real Paper",
        "url": "https://example.com",
        "source": "Example",
        "structured_content": {
            "pmid": "11111111",
            "doi": "10.1234/real",
            "authors": ["Real A"],
            "journal": "J Real",
            "year": "2024",
        },
        "full_text": "body",
    }
    fake_llm = (
        "POST\n\nbody\n\nREFERENCES:\n"
        "1. Hallucinated J et al. (2099). Fake. Fake J. doi:10.0000/fake\n"
    )
    call_count = {"n": 0}
    def fake_complete(prompt, *, temperature=0.5, **kw):
        call_count["n"] += 1
        return fake_llm

    def fake_verify(draft_or_text, *, slug=""):
        # Used during extraction (no inline DOIs in body) and during Layer B
        return []

    result = gd.generate_grounded_draft(
        article,
        verify_fn=fake_verify,
        llm_complete=fake_complete,
        llm_is_configured=lambda: True,
        slug="test_drop",
        max_retries=1,
    )
    assert result is None
    assert call_count["n"] == 2  # initial attempt + 1 retry


def test_no_api_key_returns_none_without_calling_llm(needs_research_dir):
    import grounded_drafter as gd

    article = {
        "title": "T",
        "structured_content": {
            "pmid": "1", "doi": "10.1/x", "authors": ["A"], "journal": "J", "year": "2024",
        },
        "full_text": "",
    }

    def must_not_call(*a, **k):
        raise AssertionError("LLM must not be called when not configured")

    result = gd.generate_grounded_draft(
        article,
        verify_fn=_make_verify_fn(),
        llm_complete=must_not_call,
        llm_is_configured=lambda: False,
        slug="no_key",
    )
    assert result is None


def test_invalid_article_raises_value_error():
    import grounded_drafter as gd
    with pytest.raises(ValueError):
        gd.generate_grounded_draft({})
    with pytest.raises(ValueError):
        gd.generate_grounded_draft({"title": ""})
    with pytest.raises(ValueError):
        gd.generate_grounded_draft("not a dict")  # type: ignore[arg-type]


# ── Library surface ───────────────────────────────────────────────────────


def test_library_export_reachable():
    import contentprinter
    assert hasattr(contentprinter, "generate_grounded_draft")
    assert callable(contentprinter.generate_grounded_draft)
    # Confirm the package version bump landed
    assert contentprinter.__version__ == "0.3.1"


def test_library_export_validates_article():
    import contentprinter
    with pytest.raises(ValueError):
        contentprinter.generate_grounded_draft({"title": ""})


def test_library_export_refresh_audit_meta_reachable():
    import contentprinter
    assert hasattr(contentprinter, "refresh_audit_meta")
    assert callable(contentprinter.refresh_audit_meta)


def test_refresh_audit_meta_wrapper_validates_slug():
    import contentprinter
    with pytest.raises(ValueError):
        contentprinter.refresh_audit_meta("")
    with pytest.raises(ValueError):
        contentprinter.refresh_audit_meta(None)  # type: ignore[arg-type]


# ── #45 polish item: signal file schema coverage ──────────────────────────


def test_signal_file_payload_has_full_schema(tmp_path, monkeypatch):
    """Pin all 8 top-level keys + extraction_breakdown subkeys against schema drift."""
    import grounded_drafter as gd
    target = tmp_path / "needs_research"
    monkeypatch.setattr(gd, "NEEDS_RESEARCH_DIR", target)
    article = {
        "title": "Practitioner Post",
        "url": "https://example.com/post",
        "source_type": "rss",
        "source": "Example",
        "full_text": "no DOIs",
    }
    result = gd.generate_grounded_draft(
        article,
        verify_fn=_make_verify_fn(),
        llm_complete=lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM not called")),
        llm_is_configured=lambda: True,
        slug="schema_test",
    )
    assert result is None
    payload = json.loads((target / "schema_test.json").read_text())
    expected_top = {
        "slug",
        "source_url",
        "source_type",
        "article_title",
        "extracted_refs_attempted",
        "extraction_breakdown",
        "timestamp",
    }
    assert expected_top.issubset(set(payload.keys()))
    expected_breakdown = {
        "structured_content_doi",
        "inline_doi_matches",
        "inline_pmid_matches",
        "total_attempted",
    }
    assert expected_breakdown.issubset(set(payload["extraction_breakdown"].keys()))
    # Spot-check semantic correctness
    assert payload["slug"] == "schema_test"
    assert payload["source_type"] == "rss"
    assert payload["article_title"] == "Practitioner Post"
    # Timestamp must be UTC-aware ISO8601 ending in `Z`
    assert payload["timestamp"].endswith("Z")
