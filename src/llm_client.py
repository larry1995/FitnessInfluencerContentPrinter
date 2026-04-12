"""
Thin LLM client for ContentPrinter.

Calls Anthropic's Messages API directly via the project's shared requests
session (http_utils.create_session) so no new dependencies are required.
API key is read from the environment variable `ANTHROPIC_API_KEY`. If the
variable is not set, every call returns `None` and the caller is expected
to handle the no-LLM path gracefully (e.g. leave an existing file in place).

Usage:
    from llm_client import complete
    text = complete("Write a haiku about squats.", temperature=0.7)
    if text is None:
        # no key configured or API call failed
        ...
"""

import json
import os
import time
from pathlib import Path

from http_utils import create_session

PROJECT_ROOT = Path(__file__).parent.parent

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-opus-4-6"
DEFAULT_MAX_TOKENS = 4096
API_VERSION = "2023-06-01"


def _load_dotenv_key() -> str | None:
    """Cheap .env loader — no python-dotenv dependency. Only reads ANTHROPIC_API_KEY."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return None
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("ANTHROPIC_API_KEY"):
                _, _, value = line.partition("=")
                value = value.strip().strip("'").strip('"')
                if value:
                    return value
    except OSError:
        return None
    return None


_session = None


def _get_session():
    global _session
    if _session is None:
        _session = create_session()
    return _session


def complete(
    prompt: str,
    *,
    system: str = "",
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    retries: int = 2,
    retry_delay: float = 2.0,
) -> str | None:
    """Send a single-turn user prompt to Claude and return the text content.

    Returns None if no API key is configured or the request ultimately fails.
    The caller MUST handle the None case (don't crash the pipeline).
    """
    key = _load_dotenv_key()
    if not key:
        return None

    session = _get_session()
    headers = {
        "x-api-key": key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = session.post(ANTHROPIC_URL, headers=headers, data=json.dumps(body), timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                blocks = data.get("content", [])
                text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
                return "".join(text_parts).strip()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            break
        except Exception as e:
            last_err = str(e)
            if attempt < retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            break

    print(f"[LLM] request failed after {retries + 1} attempts: {last_err}")
    return None


def is_configured() -> bool:
    """True iff an API key is available (env or .env file)."""
    return _load_dotenv_key() is not None
