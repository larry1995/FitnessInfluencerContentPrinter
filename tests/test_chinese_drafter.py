"""Offline tests for chinese_drafter — no LLM calls."""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


def test_prompt_template_loads_and_contains_marker_body():
    from chinese_drafter import load_prompt_template, PROMPT_MARKER_START, PROMPT_MARKER_END
    body = load_prompt_template()
    assert PROMPT_MARKER_START not in body
    assert PROMPT_MARKER_END not in body
    assert "{english_draft}" in body
    assert "Bruce Lu" in body


def test_build_prompt_substitutes_placeholder():
    from chinese_drafter import build_prompt
    prompt = build_prompt("ENGLISH_DRAFT_SENTINEL")
    assert "ENGLISH_DRAFT_SENTINEL" in prompt
    assert "{english_draft}" not in prompt


def test_validate_chinese_output_accepts_valid_output():
    from chinese_drafter import validate_chinese_output
    sample = (
        "【肌酸】一口气讲完99%的人都没做对的5件事\n\n"
        + ("一段中文内容。" * 30)
        + "\n\n参考文献：\n1. Forbes SC et al. (2025). doi:10.3390/nu17172748\n"
    )
    ok, reason = validate_chinese_output(sample)
    assert ok, f"expected valid, got: {reason}"


def test_validate_chinese_output_rejects_english_lifts():
    from chinese_drafter import validate_chinese_output
    bad = "【训练】解析 back squat 的技术要点\n" + ("内容。" * 60) + "\n参考文献：\n1. Smith 2024"
    ok, reason = validate_chinese_output(bad)
    assert not ok
    assert "back squat" in reason.lower() or "loanword" in reason.lower()


def test_validate_chinese_output_rejects_missing_references_block():
    from chinese_drafter import validate_chinese_output
    bad = "【肌酸】一口气讲完\n" + ("内容。" * 60)
    ok, reason = validate_chinese_output(bad)
    assert not ok
    assert "参考文献" in reason


def test_generate_for_topic_skips_when_no_api_key(tmp_path, monkeypatch):
    from chinese_drafter import generate_for_topic
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("chinese_drafter.is_configured", lambda: False)

    topic = tmp_path / "fake_topic"
    (topic / "en").mkdir(parents=True)
    (topic / "zh").mkdir(parents=True)
    (topic / "en" / "draft.txt").write_text("FAKE EN DRAFT", encoding="utf-8")
    (topic / "zh" / "draft.txt").write_text("existing zh", encoding="utf-8")

    status = generate_for_topic(topic)
    assert "skipped" in status
    assert (topic / "zh" / "draft.txt").read_text(encoding="utf-8") == "existing zh"
