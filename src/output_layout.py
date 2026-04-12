"""
Final output layout: move rendered artifacts from work/ to Posts/<category>/.

Pipeline separation:
    work/<slug>/en/draft.txt          ← internal scratch (drafter output)
    work/<slug>/en/single_page.png    ← internal scratch (renderer output)
    work/<slug>/zh/draft.txt          ← internal scratch (chinese drafter)
    work/<slug>/pdfs/ref*.pdf         ← internal scratch (pdf downloader)
    work/<slug>/meta.json             ← internal scratch (audit state)

    Posts/<category>/<clean_slug>.png        ← final
    Posts/<category>/<clean_slug>.zh.md      ← final (markdown-formatted)
    Posts/<category>/pdfs/<clean_slug>_refNN.pdf  ← final

`finalize_topic(slug)` promotes a single slug from work/ → Posts/.
`finalize_all()` walks work/ and promotes every slug with a rendered PNG.

The 6 categories are a user-facing editorial taxonomy, not a content dimension
the drafter knows about. Mapping from internal slug to (category, clean_slug)
lives in `config/categories.json` so it can be edited without touching code.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = PROJECT_ROOT / "work"
OUTPUT_DIR = PROJECT_ROOT / "Posts"
CATEGORIES_JSON = PROJECT_ROOT / "config" / "categories.json"

CATEGORIES: tuple[str, ...] = (
    "training_methods",
    "sample_programming",
    "nutrition",
    "supplements",
    "cardio",
    "warmup",
)


@dataclass(frozen=True)
class FinalizeResult:
    slug: str
    category: str
    clean_slug: str
    png_moved: bool
    zh_md_written: bool
    pdfs_moved: int
    skipped_reason: str | None = None


def _load_categories_config() -> dict:
    if not CATEGORIES_JSON.exists():
        return {}
    try:
        return json.loads(CATEGORIES_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def classify(slug: str) -> tuple[str, str]:
    """Return (category, clean_slug) for a work/<slug> topic.

    Looks up the explicit mapping in config/categories.json first. Falls back
    to a heuristic based on slug prefix if no explicit mapping exists.

    The fallback uses substring matching on the slug, in priority order:
        cardio_*          → cardio
        warmup_*, *_prehab → warmup
        supplements_*, *_creatine, *_vitamin_*, *_caffeine_*, *_magnesium,
            *_collagen, *_beta_alanine, *_omega3 → supplements
        nutrition_*, *_diet, *_carb_*, *_fat_*, *_protein_*, *_sleep_*,
            *_clean_eating → nutrition
        training_beginner_program, *_texas_method, *_powerlifting_program
            → sample_programming
        training_*, yt_*, rehab_* → training_methods (catchall)

    Clean slug strips the category prefix and any `yt_`/`rehab_` prefixes,
    producing a filename-friendly stem without category duplication.
    """
    config = _load_categories_config()
    explicit = config.get("mapping", {}).get(slug)
    if explicit and isinstance(explicit, list) and len(explicit) == 2:
        return explicit[0], explicit[1]
    if explicit and isinstance(explicit, dict):
        return explicit.get("category", "training_methods"), explicit.get("clean_slug", slug)

    s = slug.lower()
    if s.startswith("cardio_"):
        return "cardio", _strip_prefixes(s, ("cardio_",))
    if "prehab" in s or s.startswith("warmup_") or s in {"training_warmups"}:
        clean = _strip_prefixes(s, ("training_", "warmup_", "rehab_"))
        if s == "training_warmups":
            clean = "dynamic_warmups"
        return "warmup", clean

    supplement_markers = (
        "creatine", "vitamin_d", "caffeine", "magnesium", "collagen",
        "beta_alanine", "omega3", "whey",
    )
    if s.startswith("supplements_") or any(m in s for m in supplement_markers):
        return "supplements", _strip_prefixes(s, ("supplements_", "nutrition_"))

    program_markers = ("beginner_program", "texas_method", "powerlifting_program")
    if any(m in s for m in program_markers):
        return "sample_programming", _strip_prefixes(s, ("training_", "yt_"))

    nutrition_markers = (
        "diet", "carb", "fat_myth", "clean_eating",
        "sleep_recovery", "protein_excess",
    )
    if s.startswith("nutrition_") or any(m in s for m in nutrition_markers):
        return "nutrition", _strip_prefixes(s, ("nutrition_", "training_", "yt_"))

    return "training_methods", _strip_prefixes(s, ("training_", "yt_", "rehab_"))


def _strip_prefixes(slug: str, prefixes: tuple[str, ...]) -> str:
    for p in prefixes:
        if slug.startswith(p):
            return slug[len(p):]
    return slug


_NUMBERED_HEADER_RE = re.compile(r"^(\d+)[.、]")
_SECTION_LABELS = {"研究结果：", "总结：", "结论：", "研究方法：", "关键发现："}


def zh_draft_to_markdown(zh_text: str) -> str:
    """Convert a plain-text Chinese draft to markdown.

    Rules:
        - First non-empty line becomes an H1 title (stripped of trailing em-dashes).
        - Lines starting with "N." or "N、" become **bold** numbered headers.
        - Section labels like "研究结果：" become **bold**.
        - Other lines pass through unchanged.
        - Trailing whitespace normalized.
    """
    lines = zh_text.strip().splitlines()
    if not lines:
        return ""
    title = lines[0].strip().rstrip("—— ").strip()
    body_start = 1
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    out = [f"# {title}", ""]
    for line in lines[body_start:]:
        stripped = line.strip()
        if stripped and _NUMBERED_HEADER_RE.match(stripped):
            out.append(f"**{stripped}**")
        elif stripped in _SECTION_LABELS:
            out.append(f"**{stripped}**")
        else:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def finalize_topic(slug: str, *, dry_run: bool = False) -> FinalizeResult:
    """Promote work/<slug>/* artifacts into Posts/<category>/<clean_slug>.*.

    Idempotent. Safe to call multiple times; overwrites existing output files.
    Returns a FinalizeResult summarizing what was moved.
    """
    work_topic = WORK_DIR / slug
    if not work_topic.is_dir():
        return FinalizeResult(
            slug=slug, category="", clean_slug="",
            png_moved=False, zh_md_written=False, pdfs_moved=0,
            skipped_reason="missing-work-dir",
        )

    category, clean_slug = classify(slug)
    cat_dir = OUTPUT_DIR / category
    pdfs_dir = cat_dir / "pdfs"

    png_moved = False
    png_src = work_topic / "en" / "single_page.png"
    if png_src.exists():
        if not dry_run:
            cat_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png_src, cat_dir / f"{clean_slug}.png")
        png_moved = True

    zh_written = False
    zh_src = work_topic / "zh" / "draft.txt"
    if zh_src.exists():
        if not dry_run:
            cat_dir.mkdir(parents=True, exist_ok=True)
            md = zh_draft_to_markdown(zh_src.read_text(encoding="utf-8"))
            (cat_dir / f"{clean_slug}.zh.md").write_text(md, encoding="utf-8")
        zh_written = True

    pdfs_moved = 0
    pdf_src_dir = work_topic / "pdfs"
    if pdf_src_dir.is_dir():
        for pdf in sorted(pdf_src_dir.glob("*.pdf")):
            if not dry_run:
                pdfs_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pdf, pdfs_dir / f"{clean_slug}_{pdf.name}")
            pdfs_moved += 1

    return FinalizeResult(
        slug=slug, category=category, clean_slug=clean_slug,
        png_moved=png_moved, zh_md_written=zh_written, pdfs_moved=pdfs_moved,
    )


def finalize_all(*, dry_run: bool = False) -> list[FinalizeResult]:
    """Walk work/ and finalize every topic with a rendered PNG."""
    if not WORK_DIR.exists():
        return []
    results: list[FinalizeResult] = []
    for topic_dir in sorted(WORK_DIR.iterdir()):
        if not topic_dir.is_dir():
            continue
        if topic_dir.name in {"raw", "transcripts", "drafts", ".needs_research"}:
            continue
        results.append(finalize_topic(topic_dir.name, dry_run=dry_run))
    return results


def summarize(results: list[FinalizeResult]) -> str:
    if not results:
        return "0 topics finalized"
    per_cat: dict[str, int] = {}
    png_total = zh_total = pdf_total = 0
    for r in results:
        if r.skipped_reason:
            continue
        per_cat[r.category] = per_cat.get(r.category, 0) + 1
        png_total += int(r.png_moved)
        zh_total += int(r.zh_md_written)
        pdf_total += r.pdfs_moved
    lines = [
        f"Finalized {len(results)} topics ({png_total} png, {zh_total} zh.md, {pdf_total} pdf)",
    ]
    for cat in CATEGORIES:
        n = per_cat.get(cat, 0)
        if n:
            lines.append(f"  {cat}: {n}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Finalize work/ → Posts/ per-category layout")
    p.add_argument("--slug", help="finalize a single topic slug")
    p.add_argument("--dry-run", action="store_true", help="show what would change")
    args = p.parse_args()

    if args.slug:
        result = finalize_topic(args.slug, dry_run=args.dry_run)
        print(result)
    else:
        results = finalize_all(dry_run=args.dry_run)
        print(summarize(results))
