"""Library surface for Chinese (Bruce Lu voice) draft generation.

The underlying `src/chinese_drafter.py` exposes a Path-based
`generate_for_topic(topic_dir)` that both reads and writes files. For a
library consumer we want a string-in/string-out primitive so a FastAPI
handler can build a response without touching the Posts/ tree.

Graceful degradation: if `ANTHROPIC_API_KEY` is not configured, returns
`None`. Callers MUST handle the None case — do not crash on missing keys.
"""

from __future__ import annotations

import chinese_drafter as _cd
import llm_client as _llm_client


def is_llm_configured() -> bool:
    """Return True iff an Anthropic API key is available (env or .env file)."""
    return _llm_client.is_configured()


def generate_chinese_from_english(
    english_draft: str,
    *,
    temperature: float = 0.7,
    retry_on_validation_failure: bool = True,
) -> str | None:
    """Convert an English post draft into Bruce-Lu-voice Simplified Chinese.

    Args:
        english_draft: The full English draft text — caption + REFERENCES
            block. Shorter / partial drafts will usually fail validation
            (missing `参考文献` block → rejected).
        temperature: LLM sampling temperature. Default 0.7 matches the
            production pipeline. Lower (~0.3-0.4) for more deterministic
            output in tests.
        retry_on_validation_failure: If True, a failed validation (English
            lift loanwords, missing references block) triggers a single
            retry at a cooler temperature before returning None.

    Returns:
        The generated Chinese text (str) on success, or None if no API key
        is configured, the API call ultimately failed, or validation failed
        after retry. **Callers must handle None.**

    The Central Strength gym CTA is NOT included in the returned string —
    that's appended separately by downstream file writers. This function
    returns pure Bruce Lu voice, as written by the LLM.

    Stability: return type is `str | None` permanently. The Bruce-Lu voice
    prompt template lives in `config/chinese_prompt_template.md` and may
    evolve; the function signature will not change.
    """
    if not isinstance(english_draft, str) or len(english_draft.strip()) < 50:
        raise ValueError("english_draft must be a non-trivial string (>=50 chars)")

    if not _llm_client.is_configured():
        return None

    prompt = _cd.build_prompt(english_draft)
    text = _llm_client.complete(prompt, temperature=temperature)

    if text is not None:
        ok, _ = _cd.validate_chinese_output(text)
        if not ok and retry_on_validation_failure:
            text = _llm_client.complete(prompt, temperature=_cd.RETRY_TEMPERATURE)
            if text is not None:
                ok, _ = _cd.validate_chinese_output(text)
                if not ok:
                    text = None
        elif not ok:
            text = None

    return text
