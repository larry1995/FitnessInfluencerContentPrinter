"""
Chinese draft generator — Bruce Lu voice.

Loads config/chinese_prompt_template.md, calls the LLM with the English draft
substituted in, validates the output for common prompt-failure modes, and
writes it verbatim to Posts/<slug>/zh/draft.txt. A gym CTA block is appended
**outside** the Bruce Lu prompt (Bruce never writes ads in his own voice —
per frontend-writer's integration notes).

Usage:
    python src/chinese_drafter.py                      # refresh all zh drafts
    python src/chinese_drafter.py --topic nutrition_vegan_creatine
    python src/chinese_drafter.py --dry-run            # preview prompts, no LLM

Design notes:
- If no ANTHROPIC_API_KEY is configured, this script is a safe no-op for each
  topic that already has a zh draft (prints a warning and skips). New topics
  with no zh draft get a stub note.
- Validation layer: if the LLM returns English loanwords for common lifts
  ("back squat", "bench press", "deadlift" in Latin script), retry once at a
  lower temperature. This mirrors note #7 in the prompt template.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from llm_client import complete, is_configured

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "Posts"
PROMPT_TEMPLATE_PATH = CONFIG_DIR / "chinese_prompt_template.md"

PROMPT_MARKER_START = "<<<PROMPT_START>>>"
PROMPT_MARKER_END = "<<<PROMPT_END>>>"

DEFAULT_TEMPERATURE = 0.7
RETRY_TEMPERATURE = 0.4

GYM_CTA_ZH = (
    "\n\n---\n"
    "加入 Central Strength Gym（圣塔克拉拉 / 湾区）\n"
    "网址：centralstrengthgyms.com\n"
    "教练：Hao Cheng（NASM 认证私人教练） · 电话 573-529-3057\n"
)

ENGLISH_LIFT_TERMS = re.compile(
    r"\b(back\s*squat|bench\s*press|dead\s*lift|deadlift|overhead\s*press|pull[\s-]*up|chin[\s-]*up)\b",
    re.IGNORECASE,
)


def load_prompt_template() -> str:
    """Return the raw prompt body between the PROMPT_START/END markers.

    The markers are expected to appear on their own lines, so we match only
    standalone occurrences. This avoids picking up marker names mentioned in
    the template's own documentation / "Integration Notes" prose.
    """
    lines = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
    start_idx = None
    end_idx = None
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped == PROMPT_MARKER_START and start_idx is None:
            start_idx = i
        elif stripped == PROMPT_MARKER_END and start_idx is not None and end_idx is None:
            end_idx = i
            break
    if start_idx is None or end_idx is None:
        raise RuntimeError(
            f"Prompt markers not found in {PROMPT_TEMPLATE_PATH}. "
            f"Expected {PROMPT_MARKER_START} and {PROMPT_MARKER_END} on their own lines."
        )
    body = "\n".join(lines[start_idx + 1:end_idx])
    return body.strip("\n")


def build_prompt(english_draft: str) -> str:
    tmpl = load_prompt_template()
    return tmpl.replace("{english_draft}", english_draft)


def validate_chinese_output(text: str) -> tuple[bool, str]:
    """Return (ok, reason). False reasons trigger a retry at lower temperature."""
    if not text or len(text.strip()) < 100:
        return False, "output too short"
    if ENGLISH_LIFT_TERMS.search(text):
        bad = ENGLISH_LIFT_TERMS.search(text).group(0)
        return False, f"english loanword for common lift: {bad!r}"
    if "参考文献" not in text:
        return False, "missing 参考文献 block"
    return True, ""


def discover_topics(only: str | None = None) -> list[Path]:
    """Return a list of topic directories that have an en/draft.txt."""
    topics: list[Path] = []
    if not POSTS_DIR.exists():
        return topics
    for topic_dir in sorted(POSTS_DIR.iterdir()):
        if not topic_dir.is_dir():
            continue
        if only and topic_dir.name != only:
            continue
        en_draft = topic_dir / "en" / "draft.txt"
        if en_draft.exists():
            topics.append(topic_dir)
    return topics


def generate_for_topic(topic_dir: Path, dry_run: bool = False, force: bool = False) -> str:
    """Generate (or regenerate) the zh draft for one topic. Returns a status string."""
    slug = topic_dir.name
    en_draft_path = topic_dir / "en" / "draft.txt"
    zh_dir = topic_dir / "zh"
    zh_draft_path = zh_dir / "draft.txt"

    english_draft = en_draft_path.read_text(encoding="utf-8", errors="replace")
    prompt = build_prompt(english_draft)

    if dry_run:
        print(f"[DRY] {slug} — prompt {len(prompt)} chars, en {len(english_draft)} chars")
        return "dry-run"

    if not is_configured():
        if zh_draft_path.exists() and not force:
            return "skipped (no API key, existing zh preserved)"
        return "skipped (no API key, no existing zh)"

    text = complete(prompt, temperature=DEFAULT_TEMPERATURE)
    attempt = 1
    if text is not None:
        ok, reason = validate_chinese_output(text)
        if not ok:
            print(f"  [RETRY] {slug}: {reason}")
            text = complete(prompt, temperature=RETRY_TEMPERATURE)
            attempt = 2
            if text is not None:
                ok, reason = validate_chinese_output(text)
                if not ok:
                    print(f"  [FAIL] {slug}: {reason} (after retry)")
                    text = None

    if text is None:
        if zh_draft_path.exists():
            return "failed (preserved existing zh)"
        return "failed (no fallback available)"

    final = text.rstrip() + GYM_CTA_ZH
    zh_dir.mkdir(parents=True, exist_ok=True)
    zh_draft_path.write_text(final, encoding="utf-8")
    return f"written (attempt {attempt}, {len(final)} chars)"


def regenerate_all(only: str | None = None, dry_run: bool = False, force: bool = False) -> int:
    topics = discover_topics(only)
    if not topics:
        print(f"[INFO] No matching topics found under {POSTS_DIR}")
        return 0

    print(f"\n{'='*60}")
    print(f"  CHINESE DRAFTER (Bruce Lu voice) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Topics: {len(topics)}  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"  LLM configured: {is_configured()}")
    print(f"{'='*60}\n")

    for topic_dir in topics:
        try:
            status = generate_for_topic(topic_dir, dry_run=dry_run, force=force)
        except Exception as e:
            status = f"ERROR: {e}"
        print(f"[{topic_dir.name}] {status}")

    return len(topics)


def main():
    parser = argparse.ArgumentParser(description="Regenerate Chinese drafts in Bruce Lu voice")
    parser.add_argument("--topic", default=None, help="Single topic slug to process")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt sizes, no LLM calls")
    parser.add_argument("--force", action="store_true",
                        help="Without API key: error instead of silently skipping existing zh")
    args = parser.parse_args()
    n = regenerate_all(only=args.topic, dry_run=args.dry_run, force=args.force)
    sys.exit(0 if n > 0 else 1)


if __name__ == "__main__":
    main()
