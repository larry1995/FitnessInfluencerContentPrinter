"""
Single-Page Detailed PDF Generator for Central Strength Gym
Creates one tall infographic per post with ALL content:
  - Author header & gym branding with topic badge
  - Prominent evidence strength indicator
  - Key statistic highlight
  - Overview / introduction paragraph
  - Numbered key points with full body text
  - Post-type-specific layouts (program cards, myth vs fact, supplement
    fact sheets, rehab exercise sequences)
  - Additional info sections (what to avoid, signs, etc.)
  - Practical guide (bullet-point recommendations)
  - Summary / bottom line
  - Full references with DOI/URL citation formatting
  - Author & gym footer

Outputs individual PNGs + a combined PDF.
Renders at 3x for print-quality output (3240 x variable height).

Usage:
    python src/single_page_generator.py
    python src/main.py singlepage
"""

import json
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from image_generator import strip_emoji

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize

# Render at 3x for print-quality, Instagram-ready output
SCALE = 3
PAGE_WIDTH = 1080 * SCALE
MARGIN_X = 55 * SCALE
MARGIN_TOP = 40 * SCALE
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
PDF_DPI = 400

# Brand colors — Central Strength dark theme
BG_DARK = (26, 26, 46)          # #1A1A2E
BG_CARD = (33, 33, 55)          # slightly lighter card
BG_STAT = (46, 26, 36)          # red-tinted stat box
ACCENT_RED = (233, 69, 96)      # #E94560
ACCENT_RED_DIM = (160, 50, 65)
TEXT_WHITE = (255, 255, 255)
TEXT_LIGHT = (210, 210, 220)
TEXT_MUTED = (150, 150, 165)
TEXT_REF = (130, 140, 160)
TEXT_DOI = (100, 160, 220)       # blue for DOI/URL links
DIVIDER = (60, 60, 80)

# Topic badge colors
TOPIC_COLORS = {
    "nutrition":  ((35, 90, 50),   (140, 220, 155)),    # green
    "training":   ((90, 35, 45),   (230, 160, 165)),    # red
    "techniques": ((35, 55, 100),  (150, 185, 235)),    # blue
    "rehab":      ((90, 70, 35),   (230, 200, 130)),    # gold
    "supplement": ((35, 80, 90),   (130, 210, 220)),    # teal
    "reddit":     ((70, 35, 20),   (255, 140, 90)),     # orange
    "forum":      ((20, 45, 75),   (120, 180, 230)),    # sky blue
}

# Author & contact info — loaded from config/sources.json "brand" section
def _load_brand_config():
    with open(CONFIG_DIR / "sources.json") as f:
        return json.load(f)["brand"]

_brand = _load_brand_config()
AUTHOR_NAME = _brand.get("author_name", "")
AUTHOR_TITLE = _brand.get("author_title", "")
GYM_NAME = _brand.get("full_gym_name", _brand.get("gym_name", ""))
GYM_LOCATION = _brand.get("location", "")
GYM_WEB = _brand.get("website", "")
GYM_PHONE = _brand.get("gym_phone", "")
AUTHOR_PHONE = _brand.get("author_phone", "")
PERSONAL_CTA = _brand.get("personal_cta", "")


def S(val):
    return int(val * SCALE)


def get_font(size, bold=False):
    scaled_size = S(size)
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, scaled_size)
    return ImageFont.load_default()


def wrap_text_lines(text, font, max_width, draw):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ── Content parser ───────────────────────────────────────────────────────────


def extract_evidence_info(caption, references):
    """Extract evidence strength indicator from the content.

    Returns a dict with 'level' (strong/moderate/emerging), 'label' text,
    'detail' text, and 'total_refs' count for the prominent badge.
    """
    text = caption.lower()
    ref_text = " ".join(references).lower()

    indicators = []

    # Count reference types
    meta_count = len(re.findall(r'meta-analy', ref_text))
    review_count = len(re.findall(r'systematic review|position stand', ref_text))
    rct_count = len(re.findall(r'randomized|controlled trial|rct', ref_text))

    if meta_count:
        indicators.append(f"{meta_count} meta-analy{'ses' if meta_count > 1 else 'sis'}")
    if review_count:
        indicators.append(f"{review_count} systematic review{'s' if review_count > 1 else ''}")

    total_refs = len(references)

    # Determine evidence level
    if meta_count or (review_count and rct_count):
        level = "strong"
    elif review_count or rct_count >= 2 or total_refs >= 4:
        level = "moderate"
    elif total_refs:
        level = "emerging"
    else:
        level = ""

    if indicators:
        detail = " | ".join(indicators) + f" | {total_refs} cited sources"
    elif total_refs:
        detail = f"{total_refs} peer-reviewed sources cited"
    else:
        detail = ""

    return {
        "level": level,
        "label": level.upper() + " EVIDENCE" if level else "",
        "detail": detail,
        "total_refs": total_refs,
    }


def extract_key_stat(caption):
    """Extract the most impactful statistic from the content for a highlight box."""
    # Look for percentage-based findings
    pct_patterns = [
        r'(\d+(?:\.\d+)?%\s+(?:more|less|higher|lower|increase|decrease|improvement|reduction)[^.]*\.)',
        r'(\d+(?:\.\d+)?x\s+(?:more|higher|greater|lower)[^.]*\.)',
        r'(\d+(?:\.\d+)?%\s+of\s+[^.]*(?:deficient|athletes|lifters)[^.]*\.)',
    ]
    for pat in pct_patterns:
        m = re.search(pat, caption, re.IGNORECASE)
        if m:
            stat = strip_emoji(m.group(1)).strip()
            if 20 < len(stat) < 200:
                return stat

    # Look for specific numeric findings
    num_patterns = [
        r'(gained\s+(?:an\s+)?average\s+of\s+[\d.]+\s*(?:kg|lbs?|g)[^.]*\.)',
        r'([\d.]+(?:g|mg|iu)\s+(?:of\s+)?[a-z]+\s+(?:daily|per\s+day|per\s+meal)[^.]*\.)',
        r'(\d+-\d+\s*(?:sets?|reps?|hours?|weeks?)\s+[^.]*(?:optimal|recommended|effective)[^.]*\.)',
    ]
    for pat in num_patterns:
        m = re.search(pat, caption, re.IGNORECASE)
        if m:
            stat = strip_emoji(m.group(1)).strip()
            if 15 < len(stat) < 200:
                return stat

    return ""


def _load_sidecar_if_present(draft_path):
    sidecar_path = Path(draft_path).parent / "source.json"
    if not sidecar_path.exists():
        return None
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _populate_from_sidecar(post, sidecar):
    """Populate post dict from a community-source sidecar.

    Returns True if the sidecar was recognized and the post was populated;
    False for unknown source_type so the caller falls through to the regex
    parser instead of short-circuiting into an empty post.
    """
    source_type = sidecar.get("source_type", "")

    if source_type == "reddit":
        post["layout"] = "reddit_thread"
        post["topic"] = "reddit"
        post["title"] = strip_emoji(sidecar.get("thread_title", "")).strip()
        post["source"] = f"r/{sidecar.get('subreddit', '')}"
        post["reddit_meta"] = {
            "subreddit": sidecar.get("subreddit", ""),
            "thread_title": sidecar.get("thread_title", ""),
            "thread_score": sidecar.get("thread_score", 0),
            "thread_permalink": sidecar.get("thread_permalink", ""),
            "op_author": sidecar.get("op_author", ""),
            "op_body": sidecar.get("op_body", ""),
            "fetched_at": sidecar.get("fetched_at", ""),
        }
        post["reddit_callouts"] = list(sidecar.get("reddit_callouts", []))[:4]
        return True

    if source_type == "forum":
        post["layout"] = "forum_thread"
        post["topic"] = "forum"
        post["title"] = strip_emoji(sidecar.get("thread_title", "")).strip()
        post["source"] = f"{sidecar.get('forum_name', '')} / {sidecar.get('subforum', '')}"
        post["forum_meta"] = {
            "forum_name": sidecar.get("forum_name", ""),
            "subforum": sidecar.get("subforum", ""),
            "thread_title": sidecar.get("thread_title", ""),
            "thread_url": sidecar.get("thread_url", ""),
            "op_author": sidecar.get("op_author", ""),
            "op_rank": sidecar.get("op_rank", ""),
            "op_post_count": sidecar.get("op_post_count"),
            "op_body": sidecar.get("op_body", ""),
            "fetched_at": sidecar.get("fetched_at", ""),
        }
        post["forum_quote_chain"] = list(sidecar.get("forum_quote_chain", []))[:4]
        return True

    return False


def parse_detailed_content(filepath):
    """Parse a polished .txt file extracting ALL content sections."""
    with open(filepath) as f:
        text = f.read()

    post = {
        "filename": filepath.name,
        "title": "",
        "source": "",
        "topic": "",
        "layout": "default",        # default | program | mythbust | supplement | rehab | reddit_thread | forum_thread
        "intro_text": "",
        "numbered_points": [],
        "sections": [],
        "extra_sections": [],      # ✅/⚠️/📊 sections
        "practical_guide": [],
        "practical_guide_header": "",
        "summary_text": "",
        "references": [],
        "evidence_info": {},
        "key_stat": "",
        # Layout-specific fields
        "program_phases": [],       # for program cards
        "myths": [],                # for myth-busting layout
        "rehab_steps": [],          # for rehab sequences
        "supplement_facts": {},     # for supplement fact sheets
        "reddit_meta": {},          # for reddit_thread layout (sidecar source.json)
        "reddit_callouts": [],      # list of top-voted comments, len <= 4
        "forum_meta": {},           # for forum_thread layout
        "forum_quote_chain": [],    # flattened quote chain, len <= 4
        # Audit state (populated from meta.json by the discovery wrapper).
        # When "BLOCKED", render_single_page stamps the output with a
        # publication-block watermark unless WATERMARK_BLOCKED is disabled.
        "audit_status": "",
        "audit_issue_count": 0,
    }

    sidecar = _load_sidecar_if_present(filepath)
    if sidecar and _populate_from_sidecar(post, sidecar):
        return post

    # Source
    source_match = re.search(r"Source:\s*(.+?)(?:\s*\(|$)", text, re.MULTILINE)
    if source_match:
        post["source"] = source_match.group(1).strip()

    # Topic from filename
    fname_lower = filepath.name.lower()
    if "nutrition" in fname_lower:
        post["topic"] = "nutrition"
    elif "technique" in fname_lower:
        post["topic"] = "techniques"
    elif "rehab" in fname_lower:
        post["topic"] = "rehab"
    elif "supplement" in fname_lower:
        post["topic"] = "supplement"
    else:
        post["topic"] = "training"

    # Caption between separator lines
    caption_match = re.search(r'CAPTION:\s*\n-{10,}\n(.+?)\n-{10,}', text, re.DOTALL)
    caption = caption_match.group(1).strip() if caption_match else ""

    # Title (first non-empty, non-hashtag line)
    caption_lines = caption.split("\n")
    title_line_idx = -1
    for i, line in enumerate(caption_lines):
        line = line.strip()
        if line and not line.startswith("#"):
            post["title"] = strip_emoji(line).strip(" \u2014-:")
            title_line_idx = i
            break

    # ── INTRO TEXT ──
    if title_line_idx >= 0:
        intro_parts = []
        for line in caption_lines[title_line_idx + 1:]:
            stripped = line.strip()
            if re.match(r'^\d[.)\s]', stripped) or re.match(r'^\d\uFE0F?\u20E3', stripped):
                break
            if re.match(r'^[A-Z][A-Z\s0-9:&/\-]{5,}:?\s*$', stripped):
                break
            if re.match(r'^[\U0001F300-\U0001FAFF].+[A-Z]{3,}', stripped):
                break
            clean = strip_emoji(stripped).strip()
            if clean and not clean.startswith("#") and not clean.startswith("Book "):
                intro_parts.append(clean)
        post["intro_text"] = " ".join(intro_parts)[:800]

    # ── NUMBERED POINTS (full body, up to 600 chars) ──
    point_pattern = re.compile(
        r'^(?:(\d)[.)\s]\s*|(\d)\uFE0F?\u20E3\s*)'
        r'([^\n]{1,80})\n'
        r'((?:(?!\n\n|^\d[.)]\s|^\d\uFE0F?\u20E3).)*)',
        re.DOTALL | re.MULTILINE
    )
    for m in point_pattern.finditer(caption):
        num = m.group(1) or m.group(2)
        headline = m.group(3).strip()
        body = m.group(4).strip()
        body = strip_emoji(body)
        body = re.sub(r'\s+', ' ', body).strip()
        if len(body) > 600:
            body = body[:597] + "..."
        post["numbered_points"].append({
            "number": int(num),
            "headline": headline,
            "body": body,
        })

    # ── EMOJI-PREFIXED SECTIONS (✅, ⚠️, 📊, etc.) ──
    emoji_section_re = re.compile(
        r'(?:[\u2705\u26A0\uFE0F\U0001F4CA\U0001F4A1\U0001F525][\uFE0F]?\s*)'
        r'([A-Z][A-Z\s0-9:&/\-\']+):?\s*\n'
        r'((?:(?!\n(?:[\u2705\u26A0\U0001F4CA\U0001F4A1\U0001F525]|[A-Z][A-Z\s:]+:|\d[.)]\s|\d\uFE0F)).)+)',
        re.DOTALL
    )
    for m in emoji_section_re.finditer(caption):
        header = m.group(1).strip().rstrip(":")
        body = m.group(2).strip()
        body = strip_emoji(body)
        body = re.sub(r'\s+', ' ', body)
        if len(body) > 25:
            post["extra_sections"].append({"header": header, "body": body[:500]})

    # ── ALL-CAPS SECTION HEADERS (fallback for posts without numbered points) ──
    section_pattern = re.compile(
        r'\n(?:'
        r'([A-Z][A-Z\s0-9:&/\-]+:)'
        r'|'
        r'(?:[\U0001F300-\U0001FAFF]\uFE0F?\s*)'
        r'([A-Z][A-Z\s0-9:&/\-]+)'
        r')\s*\n'
        r'((?:(?!\n(?:[A-Z][A-Z\s:&/\-]+:|\S*[\U0001F300-\U0001FAFF])).)+)',
        re.DOTALL
    )
    for m in section_pattern.finditer(caption):
        header = (m.group(1) or m.group(2) or "").strip().rstrip(":")
        body = m.group(3).strip()
        body = strip_emoji(body)
        body = re.sub(r'\s+', ' ', body)
        if len(body) > 20:
            post["sections"].append({"header": header, "body": body[:500]})

    # ── PRACTICAL GUIDE ──
    guide_header_re = re.compile(
        r'^((?:PRACTICAL|HOW\s+TO|SAMPLE|DOSING|SUPPLEMENTATION|ACTION|KEY|WHEN\s+TO|'
        r'WHO\s+SHOULD|WHAT\s+TO|THE\s+PRACTICAL|WHAT\s+TO\s+LOOK|WHAT\s+TO\s+AVOID|'
        r'HOW\s+TO\s+SUPPLEMENT|HOW\s+TO\s+OPTIMIZE|PRO\s+TIP)[A-Z\s0-9:&/\-]*?)[:\s]*$',
        re.MULTILINE | re.IGNORECASE
    )

    for hdr_m in guide_header_re.finditer(caption):
        header_text = hdr_m.group(1).strip()
        if re.match(r'THE\s+(BOTTOM|RESEARCH)', header_text, re.I):
            continue
        if not post["practical_guide_header"]:
            post["practical_guide_header"] = strip_emoji(header_text)

        after = caption[hdr_m.end():]
        for item_line in after.split("\n"):
            stripped = item_line.strip()
            if not stripped:
                continue
            if re.match(r'^[A-Z][A-Z\s0-9:&/\-]{5,}:\s*$', stripped):
                break
            if stripped.startswith("#") or stripped.startswith("\U0001F449"):
                break
            if re.match(r'^\d[.)\s]\s*[A-Z]', stripped):
                break
            # Accept: - bullets, arrow bullets, workout notation
            if re.match(r'^[-\u2022\u2192\u2794\u279C\u2023]', stripped):
                item = re.sub(r'^[-\u2022\u2192\u2794\u279C\u2023]+\s*', '', stripped).strip()
                if item and len(item) > 5:
                    post["practical_guide"].append(strip_emoji(item).strip())
            elif re.match(r'^[A-Z]\d[.:]', stripped):
                post["practical_guide"].append(strip_emoji(stripped).strip())

    # Also capture → arrow bullets under "THE TAKEAWAY FOR YOU:" etc.
    takeaway_re = re.compile(
        r'(?:THE\s+TAKEAWAY[^:\n]*|TIPS?\s+FOR[^:\n]*)[:\s]*\n'
        r'((?:[\u2192\u2794\u279C\u2023\-\u2022].*\n?)+)',
        re.IGNORECASE
    )
    for m in takeaway_re.finditer(caption):
        if not post["practical_guide_header"]:
            post["practical_guide_header"] = "KEY TAKEAWAYS"
        block = m.group(1)
        for item_line in block.split("\n"):
            item = re.sub(r'^[\u2192\u2794\u279C\u2023\-\u2022]+\s*', '', item_line.strip()).strip()
            item = strip_emoji(item).strip()
            if item and len(item) > 5 and item not in post["practical_guide"]:
                post["practical_guide"].append(item)

    post["practical_guide"] = post["practical_guide"][:12]

    # ── SUMMARY / BOTTOM LINE ──
    summary_pattern = re.compile(
        r'(?:THE\s+BOTTOM\s+LINE|KEY\s+TAKEAWAY|THE\s+TAKEAWAY|TAKEAWAY|SUMMARY)[:\s]*\n'
        r'(.+?)(?=\n\n|\nSave\s+this|\nTag\s+a|\nBook\s+your|\nDrop\s+in|\nComment|\n#|\n\U0001F449|\Z)',
        re.DOTALL | re.IGNORECASE
    )
    all_summaries = list(summary_pattern.finditer(caption))
    if all_summaries:
        summary_match = all_summaries[-1]
        summary = summary_match.group(1).strip()
        summary = strip_emoji(summary)
        summary = re.sub(r'\s+', ' ', summary)
        # Filter out guide bullets that might have been captured
        if not summary.startswith("- ") and not summary.startswith("> "):
            post["summary_text"] = summary[:600]

    # Also try standalone insight lines (💡 or "RULE OF THUMB:")
    if not post["summary_text"]:
        for pattern in [
            r'\U0001F4A1\s*(?:RULE\s+OF\s+THUMB:?\s*)?(.{30,200})',
            r'RULE\s+OF\s+THUMB:\s*(.{30,200})',
        ]:
            m = re.search(pattern, caption)
            if m:
                post["summary_text"] = strip_emoji(m.group(1).strip())[:400]
                break

    # Supplement intro with THE RESEARCH section if found
    research_match = re.search(
        r'THE\s+RESEARCH[:\s]*\n(.+?)(?=\n\n|\n\d[.)]\s|\Z)',
        caption, re.DOTALL | re.IGNORECASE
    )
    if research_match:
        research = strip_emoji(research_match.group(1).strip())
        research = re.sub(r'\s+', ' ', research)
        if post["intro_text"]:
            post["intro_text"] = post["intro_text"] + " " + research[:400]
        else:
            post["intro_text"] = research[:600]

    # ── REFERENCES ──
    ref_match = re.search(r'REFERENCES:\s*\n(.*?)(?:\n-{5,}|\Z)', text, re.DOTALL)
    if ref_match:
        for line in ref_match.group(1).strip().split("\n"):
            line = line.strip()
            if line and re.match(r'^\d+\.', line):
                post["references"].append(line)

    # ── EVIDENCE & KEY STAT ──
    post["evidence_info"] = extract_evidence_info(caption, post["references"])
    post["key_stat"] = extract_key_stat(caption)

    # ── LAYOUT DETECTION ──
    # Detect program card layout (phases, weeks, RPE)
    phase_re = re.compile(
        r'(?:PHASE|WEEK[S]?)\s*(\d+)\s*[\u2014\-:]+\s*([A-Z][A-Z\s]+)\s*(?:\(([^)]+)\))?\s*\n'
        r'((?:[^\n]*\n)*?)(?=\n(?:PHASE|WEEK[S]?|\u2705|WHY|THE\s+BOTTOM|$))',
        re.IGNORECASE
    )
    phases = list(phase_re.finditer(caption))
    if phases and len(phases) >= 2:
        post["layout"] = "program"
        for pm in phases:
            phase_bullets = []
            for line in pm.group(4).strip().split("\n"):
                line = strip_emoji(line.strip())
                line = re.sub(r'^[\u2022\-\u25B8\u25CF]\s*', '', line).strip()
                if line and len(line) > 3:
                    phase_bullets.append(line)
            post["program_phases"].append({
                "number": pm.group(1),
                "name": pm.group(2).strip(),
                "detail": pm.group(3).strip() if pm.group(3) else "",
                "bullets": phase_bullets[:6],
            })

    # Detect myth-busting layout
    myth_re = re.compile(
        r'(?:MYTH|MISCONCEPTION)\s*(?:#?\d*)[:\s]*([^\n]+)\n'
        r'(?:FACT|REALITY|TRUTH)[:\s]*([^\n]+(?:\n(?!MYTH|MISCONCEPTION|THE\s+BOTTOM)[^\n]*)*)',
        re.IGNORECASE
    )
    myths = list(myth_re.finditer(caption))
    if myths and len(myths) >= 2:
        post["layout"] = "mythbust"
        for mm in myths:
            post["myths"].append({
                "myth": strip_emoji(mm.group(1).strip()),
                "fact": strip_emoji(re.sub(r'\s+', ' ', mm.group(2).strip())),
            })

    # Detect rehab/exercise sequence (STEP 1, STEP 2, etc.)
    step_re = re.compile(
        r'STEP\s+(\d+)[:\s\u2014\-]+([^\n]+)\n'
        r'((?:(?!STEP\s+\d)[^\n]*\n)*)',
        re.IGNORECASE
    )
    steps = list(step_re.finditer(caption))
    if steps and len(steps) >= 3:
        post["layout"] = "rehab"
        for sm in steps:
            body = strip_emoji(re.sub(r'\s+', ' ', sm.group(3).strip()))
            post["rehab_steps"].append({
                "number": int(sm.group(1)),
                "title": strip_emoji(sm.group(2).strip()),
                "body": body[:400],
            })

    # Detect supplement fact sheet
    if post["topic"] in ("nutrition", "supplement"):
        dose_match = re.search(
            r'(?:DOSE|DOSAGE|DOSING|SUPPLEMENT\s+DOSE)[:\s]+([^\n]+)', caption, re.I)
        form_match = re.search(
            r'(?:BEST\s+FORM|FORM|TYPE)[:\s]+([^\n]+)', caption, re.I)
        timing_match = re.search(
            r'(?:TIMING|WHEN\s+TO\s+TAKE)[:\s]+([^\n]+)', caption, re.I)
        if dose_match and (form_match or timing_match):
            post["layout"] = "supplement"
            post["supplement_facts"] = {
                "dose": strip_emoji(dose_match.group(1).strip()) if dose_match else "",
                "form": strip_emoji(form_match.group(1).strip()) if form_match else "",
                "timing": strip_emoji(timing_match.group(1).strip()) if timing_match else "",
            }

    return post


# ── Height calculation ───────────────────────────────────────────────────────


def _calc_ref_height(ref, font_ref, font_doi, draw):
    """Calculate height for a reference with separate DOI/URL line."""
    # Split reference text from DOI/URL
    ref_clean = strip_emoji(ref)
    doi_match = re.search(r'(doi:\S+|https?://\S+)', ref_clean, re.I)
    if doi_match:
        main_text = ref_clean[:doi_match.start()].strip()
        doi_text = doi_match.group(1)
    else:
        main_text = ref_clean
        doi_text = ""

    h = 0
    main_lines = wrap_text_lines(main_text, font_ref, CONTENT_WIDTH - S(20), draw)
    h += len(main_lines) * S(16)
    if doi_text:
        doi_lines = wrap_text_lines(doi_text, font_doi, CONTENT_WIDTH - S(30), draw)
        h += len(doi_lines) * S(14)
    h += S(5)
    return h


def calculate_page_height(post, draw):
    y = MARGIN_TOP

    # Top accent bar
    y += S(6)

    # Author header
    y += S(28 + 22 + 22 + 12)

    # Red divider
    y += S(10)

    # Topic badge + title
    y += S(30)  # badge
    font_title = get_font(32, bold=True)
    title = strip_emoji(post["title"]).upper()
    title_lines = wrap_text_lines(title, font_title, CONTENT_WIDTH, draw)
    y += len(title_lines) * S(42)
    y += S(8)

    # Source line (community layouts suppress it — pill carries source info)
    if post.get("layout") not in ("reddit_thread", "forum_thread"):
        y += S(22)

    y += S(10)

    # Thin divider
    y += S(8)

    # Key stat box
    if post["key_stat"]:
        font_stat = get_font(16)
        stat_lines = wrap_text_lines(post["key_stat"], font_stat, CONTENT_WIDTH - S(50), draw)
        y += S(14) + len(stat_lines) * S(24) + S(16)
        y += S(10)

    # Overview
    if post["intro_text"]:
        y += S(28)
        font_intro = get_font(17)
        intro_lines = wrap_text_lines(post["intro_text"], font_intro, CONTENT_WIDTH - S(25), draw)
        y += len(intro_lines) * S(24)
        y += S(14)
        y += S(8)

    # Layout-specific content heights
    layout = post.get("layout", "default")
    font_head = get_font(19, bold=True)
    font_body = get_font(16)

    if layout == "program" and post["program_phases"]:
        y += S(30)  # section header
        font_phase = get_font(14)
        for phase in post["program_phases"]:
            y += S(40)  # phase header bar
            for _ in phase["bullets"]:
                y += S(22)
            y += S(12)

    if layout == "mythbust" and post["myths"]:
        y += S(30)  # section header
        for myth in post["myths"]:
            # Myth box
            myth_lines = wrap_text_lines(myth["myth"], font_body, CONTENT_WIDTH - S(80), draw)
            y += S(10) + len(myth_lines) * S(22) + S(10)
            # Fact box
            fact_lines = wrap_text_lines(myth["fact"], font_body, CONTENT_WIDTH - S(80), draw)
            y += S(10) + len(fact_lines) * S(22) + S(10)
            y += S(8)

    if layout == "rehab" and post["rehab_steps"]:
        y += S(30)  # section header
        for step in post["rehab_steps"]:
            y += S(36)  # step number + title
            body_lines = wrap_text_lines(step["body"], font_body, CONTENT_WIDTH - S(60), draw)
            y += len(body_lines) * S(22)
            y += S(10)

    if layout == "supplement" and post.get("supplement_facts"):
        y += S(30)  # header
        y += S(45) * 3  # 3 fact rows
        y += S(10)

    if layout in ("reddit_thread", "forum_thread"):
        y += _calc_community_layout_height(post, draw)

    # Numbered points
    points = post["numbered_points"][:8]
    if points:
        for pt in points:
            y += S(12)  # card top pad
            headline = strip_emoji(pt.get("headline", "")).upper()
            if headline:
                head_lines = wrap_text_lines(headline, font_head, CONTENT_WIDTH - S(60), draw)
                y += len(head_lines) * S(26)
                y += S(4)
            body = strip_emoji(pt.get("body", ""))
            if body:
                body_lines = wrap_text_lines(body, font_body, CONTENT_WIDTH - S(60), draw)
                y += len(body_lines) * S(23)
            y += S(12)  # card bottom pad
            y += S(6)
    elif post["sections"]:
        for sec in post["sections"][:8]:
            y += S(10)
            header = strip_emoji(sec.get("header", "")).upper()
            if header:
                head_lines = wrap_text_lines(header, font_head, CONTENT_WIDTH - S(25), draw)
                y += len(head_lines) * S(26) + S(4)
            body = strip_emoji(sec.get("body", ""))
            if body:
                body_lines = wrap_text_lines(body, font_body, CONTENT_WIDTH - S(25), draw)
                y += len(body_lines) * S(23)
            y += S(14)

    y += S(6)

    # Extra sections (✅/⚠️)
    if post["extra_sections"]:
        for sec in post["extra_sections"][:3]:
            y += S(10)
            header = strip_emoji(sec["header"]).upper()
            head_lines = wrap_text_lines(header, font_head, CONTENT_WIDTH - S(25), draw)
            y += len(head_lines) * S(26) + S(4)
            body = strip_emoji(sec["body"])
            body_lines = wrap_text_lines(body, font_body, CONTENT_WIDTH - S(25), draw)
            y += len(body_lines) * S(23)
            y += S(12)

    # Practical guide
    if post["practical_guide"]:
        y += S(10)
        y += S(26)
        font_bullet = get_font(15)
        for item in post["practical_guide"]:
            item_lines = wrap_text_lines(item, font_bullet, CONTENT_WIDTH - S(45), draw)
            y += len(item_lines) * S(22)
            y += S(6)
        y += S(10)

    # Summary
    if post["summary_text"]:
        y += S(10)
        y += S(12)  # box top pad
        y += S(26)
        font_summary = get_font(17)
        summary_lines = wrap_text_lines(post["summary_text"], font_summary,
                                        CONTENT_WIDTH - S(40), draw)
        y += len(summary_lines) * S(24)
        y += S(16)  # box bottom pad

    # Red divider
    y += S(10)

    # References with DOI formatting
    if post["references"]:
        y += S(26)  # header
        font_ref = get_font(11)
        font_doi = get_font(10)
        for ref in post["references"]:
            y += _calc_ref_height(ref, font_ref, font_doi, draw)
        y += S(10)

    # Divider
    y += S(8)

    # Author footer
    y += S(65)

    # Gym footer
    y += S(52)

    # Bottom bar + margin
    y += S(8) + MARGIN_TOP

    return y


# ── Rendering ────────────────────────────────────────────────────────────────


def draw_rounded_rect(draw, bbox, radius, fill):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = bbox
    r = radius
    # Corners
    draw.ellipse([x1, y1, x1 + 2*r, y1 + 2*r], fill=fill)
    draw.ellipse([x2 - 2*r, y1, x2, y1 + 2*r], fill=fill)
    draw.ellipse([x1, y2 - 2*r, x1 + 2*r, y2], fill=fill)
    draw.ellipse([x2 - 2*r, y2 - 2*r, x2, y2], fill=fill)
    # Rectangles
    draw.rectangle([x1 + r, y1, x2 - r, y2], fill=fill)
    draw.rectangle([x1, y1 + r, x2, y2 - r], fill=fill)


def _render_program_layout(draw, y, post, left_x):
    """Render program card layout with phase bars. Returns new y."""
    font_section = get_font(14, bold=True)
    font_phase_name = get_font(14, bold=True)
    font_phase_detail = get_font(11)
    font_bullet = get_font(13)

    draw.rectangle([MARGIN_X, y, MARGIN_X + S(4), y + S(20)], fill=ACCENT_RED)
    draw.text((left_x + S(12), y), "PROGRAM STRUCTURE",
              fill=ACCENT_RED, font=font_section)
    y += S(30)

    phase_colors = [
        (45, 80, 120),   # blue
        (80, 60, 120),   # purple
        (120, 55, 55),   # red
        (60, 100, 55),   # green
        (120, 90, 40),   # gold
    ]

    for i, phase in enumerate(post["program_phases"]):
        color = phase_colors[i % len(phase_colors)]

        # Phase header bar
        bar_h = S(32)
        draw_rounded_rect(draw,
                          [MARGIN_X + S(4), y, PAGE_WIDTH - MARGIN_X - S(4), y + bar_h],
                          S(5), color)

        phase_label = f"PHASE {phase['number']}"
        if phase.get("detail"):
            phase_label += f"  ({phase['detail']})"
        draw.text((left_x + S(14), y + bar_h // 2),
                  phase_label, fill=(220, 220, 240), font=font_phase_detail, anchor="lm")

        phase_name = phase["name"].upper()
        draw.text((PAGE_WIDTH - MARGIN_X - S(18), y + bar_h // 2),
                  phase_name, fill=TEXT_WHITE, font=font_phase_name, anchor="rm")
        y += bar_h + S(4)

        # Bullets
        for bullet in phase["bullets"]:
            draw.text((left_x + S(16), y + S(1)), "\u25B8",
                      fill=ACCENT_RED, font=get_font(10, bold=True))
            draw.text((left_x + S(30), y), bullet,
                      fill=TEXT_LIGHT, font=font_bullet)
            y += S(22)

        y += S(8)

    return y


def _render_mythbust_layout(draw, y, post, left_x):
    """Render myth vs fact layout. Returns new y."""
    font_section = get_font(14, bold=True)
    font_label = get_font(11, bold=True)
    font_body = get_font(15)

    draw.rectangle([MARGIN_X, y, MARGIN_X + S(4), y + S(20)], fill=ACCENT_RED)
    draw.text((left_x + S(12), y), "MYTH VS FACT",
              fill=ACCENT_RED, font=font_section)
    y += S(30)

    myth_bg = (80, 30, 30)
    fact_bg = (30, 70, 45)

    for myth in post["myths"]:
        # Myth box
        myth_lines = wrap_text_lines(myth["myth"], font_body, CONTENT_WIDTH - S(80), draw)
        myth_h = S(10) + S(18) + len(myth_lines) * S(22) + S(8)
        draw_rounded_rect(draw,
                          [MARGIN_X + S(4), y, PAGE_WIDTH - MARGIN_X - S(4), y + myth_h],
                          S(5), myth_bg)
        draw.text((left_x + S(16), y + S(10)), "MYTH",
                  fill=(230, 120, 120), font=font_label)
        my = y + S(28)
        for ml in myth_lines:
            draw.text((left_x + S(16), my), ml, fill=TEXT_LIGHT, font=font_body)
            my += S(22)
        y += myth_h + S(4)

        # Fact box
        fact_lines = wrap_text_lines(myth["fact"], font_body, CONTENT_WIDTH - S(80), draw)
        fact_h = S(10) + S(18) + len(fact_lines) * S(22) + S(8)
        draw_rounded_rect(draw,
                          [MARGIN_X + S(4), y, PAGE_WIDTH - MARGIN_X - S(4), y + fact_h],
                          S(5), fact_bg)
        draw.text((left_x + S(16), y + S(10)), "FACT",
                  fill=(120, 230, 140), font=font_label)
        fy = y + S(28)
        for fl in fact_lines:
            draw.text((left_x + S(16), fy), fl, fill=TEXT_LIGHT, font=font_body)
            fy += S(22)
        y += fact_h + S(8)

    return y


def _render_rehab_layout(draw, y, post, left_x):
    """Render rehab exercise sequence with numbered steps. Returns new y."""
    font_section = get_font(14, bold=True)
    font_step_num = get_font(18, bold=True)
    font_step_title = get_font(16, bold=True)
    font_body = get_font(14)

    draw.rectangle([MARGIN_X, y, MARGIN_X + S(4), y + S(20)], fill=ACCENT_RED)
    draw.text((left_x + S(12), y), "EXERCISE SEQUENCE",
              fill=ACCENT_RED, font=font_section)
    y += S(30)

    for step in post["rehab_steps"]:
        # Step number circle
        cx = left_x + S(18)
        cy = y + S(14)
        r = S(16)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT_RED)
        draw.text((cx, cy), str(step["number"]),
                  fill=TEXT_WHITE, font=font_step_num, anchor="mm")

        # Title
        draw.text((left_x + S(44), y + S(4)), step["title"].upper(),
                  fill=TEXT_WHITE, font=font_step_title)
        y += S(34)

        # Body
        if step["body"]:
            body_lines = wrap_text_lines(step["body"], font_body,
                                         CONTENT_WIDTH - S(50), draw)
            for bl in body_lines:
                draw.text((left_x + S(44), y), bl, fill=TEXT_LIGHT, font=font_body)
                y += S(20)

        # Connector line between steps
        if step != post["rehab_steps"][-1]:
            y += S(4)
            draw.line([(cx, y), (cx, y + S(10))], fill=ACCENT_RED_DIM, width=S(2))
            y += S(14)

    y += S(6)
    return y


def _render_supplement_facts(draw, y, post, left_x):
    """Render supplement fact sheet table. Returns new y."""
    facts = post.get("supplement_facts", {})
    if not facts:
        return y

    font_section = get_font(14, bold=True)
    font_label = get_font(12, bold=True)
    font_value = get_font(14)

    draw.rectangle([MARGIN_X, y, MARGIN_X + S(4), y + S(20)], fill=ACCENT_RED)
    draw.text((left_x + S(12), y), "SUPPLEMENT QUICK FACTS",
              fill=ACCENT_RED, font=font_section)
    y += S(30)

    rows = [
        ("DOSE", facts.get("dose", "")),
        ("BEST FORM", facts.get("form", "")),
        ("TIMING", facts.get("timing", "")),
    ]

    for label, value in rows:
        if not value:
            continue
        # Row background
        row_h = S(38)
        draw_rounded_rect(draw,
                          [MARGIN_X + S(4), y, PAGE_WIDTH - MARGIN_X - S(4), y + row_h],
                          S(4), BG_CARD)
        draw.text((left_x + S(16), y + row_h // 2), label,
                  fill=ACCENT_RED, font=font_label, anchor="lm")
        draw.text((PAGE_WIDTH // 2, y + row_h // 2), value,
                  fill=TEXT_WHITE, font=font_value, anchor="lm")
        y += row_h + S(4)

    y += S(6)
    return y


BG_COMMUNITY_OP = (30, 40, 55)
REDDIT_ORANGE = (255, 120, 70)
FORUM_BLUE = (100, 160, 220)

# Publication-freeze watermark (Task #31). Posts whose meta.json has
# audit_status == "BLOCKED" get a diagonal overlay warning humans not to
# publish. Toggle off via CLI `--no-watermark` during remediation diffs.
WATERMARK_BLOCKED = True
WATERMARK_COLOR = (255, 30, 30)
WATERMARK_BG = (15, 0, 0, 180)


def _community_body_wrap_width():
    return CONTENT_WIDTH - S(60)


def _calc_community_body_height(body, font_body, draw):
    lines = wrap_text_lines(body, font_body, _community_body_wrap_width(), draw)
    return len(lines) * S(22)


def _calc_community_layout_height(post, draw):
    font_body = get_font(14)
    font_op = get_font(15)

    y = S(56)

    if post["layout"] == "reddit_thread":
        meta = post["reddit_meta"]
        callouts = post["reddit_callouts"]
    else:
        meta = post["forum_meta"]
        callouts = post["forum_quote_chain"]

    op_body = meta.get("op_body", "")
    if op_body:
        op_lines = wrap_text_lines(op_body, font_op, _community_body_wrap_width(), draw)
        y += S(40) + len(op_lines) * S(24) + S(18)

    for callout in callouts:
        body = callout.get("body", "")
        body_h = _calc_community_body_height(body, font_body, draw) if body else 0
        y += S(32) + body_h + S(18)

    return y


def _render_community_callout(draw, y, card_data, left_x, accent_color,
                              indent=0):
    """Render one callout card: author + score + flair + body + source hint."""
    font_author = get_font(13, bold=True)
    font_meta = get_font(11)
    font_body = get_font(14)

    author = card_data.get("author", "")
    score = card_data.get("score")
    # Reddit callouts use "flair", forum quotes use "rank" — same visual slot,
    # different upstream schema. Fall-through is intentional (see source_format_design.md §3, §4).
    flair = card_data.get("flair") or card_data.get("rank")
    body = card_data.get("body", "")

    card_left = MARGIN_X + S(indent)
    card_right = PAGE_WIDTH - MARGIN_X

    body_lines = wrap_text_lines(body, font_body, _community_body_wrap_width() - S(indent),
                                 draw) if body else []
    card_h = S(10) + S(20) + len(body_lines) * S(22) + S(12)

    draw_rounded_rect(draw, [card_left, y, card_right, y + card_h], S(6), BG_CARD)
    draw.rectangle([card_left, y, card_left + S(4), y + card_h], fill=accent_color)

    header_y = y + S(12)
    header_x = card_left + S(14)
    if author:
        draw.text((header_x, header_y), author, fill=TEXT_WHITE, font=font_author)
        author_w = draw.textbbox((0, 0), author, font=font_author)[2]
        header_x += author_w + S(10)

    if flair:
        flair_bbox = draw.textbbox((0, 0), flair, font=font_meta)
        flair_w = flair_bbox[2] - flair_bbox[0] + S(12)
        flair_h = S(18)
        draw_rounded_rect(
            draw,
            [header_x, header_y + S(2), header_x + flair_w, header_y + S(2) + flair_h],
            S(4), (55, 55, 75),
        )
        draw.text((header_x + S(6), header_y + S(2) + flair_h // 2), flair,
                  fill=TEXT_LIGHT, font=font_meta, anchor="lm")

    if score is not None:
        score_text = f"\u25B2 {score}"
        draw.text((card_right - S(14), header_y), score_text,
                  fill=accent_color, font=font_author, anchor="rt")

    body_y = y + S(34)
    for bl in body_lines:
        draw.text((card_left + S(14), body_y), bl, fill=TEXT_LIGHT, font=font_body)
        body_y += S(22)

    return y + card_h + S(10)


def _render_reddit_layout(draw, y, post, left_x):
    """Render Reddit thread with OP excerpt + curated top-voted callouts."""
    font_pill = get_font(12, bold=True)
    font_section = get_font(14, bold=True)
    font_op = get_font(15)
    font_meta = get_font(11)

    meta = post["reddit_meta"]
    subreddit = meta.get("subreddit", "")
    score = meta.get("thread_score", 0)
    op_author = meta.get("op_author", "")
    op_body = meta.get("op_body", "")

    pill_text = f"r/{subreddit}  \u00B7  \u25B2 {score}"
    pill_bbox = draw.textbbox((0, 0), pill_text, font=font_pill)
    pill_w = pill_bbox[2] - pill_bbox[0] + S(20)
    pill_h = S(22)
    pill_x = MARGIN_X
    draw_rounded_rect(draw, [pill_x, y, pill_x + pill_w, y + pill_h], S(6),
                      (60, 35, 20))
    draw.text((pill_x + S(10), y + pill_h // 2), pill_text,
              fill=REDDIT_ORANGE, font=font_pill, anchor="lm")

    if op_author:
        draw.text((pill_x + pill_w + S(12), y + pill_h // 2),
                  f"Asked by {op_author}",
                  fill=TEXT_MUTED, font=font_meta, anchor="lm")
    y += pill_h + S(14)

    if op_body:
        op_lines = wrap_text_lines(op_body, font_op, _community_body_wrap_width(), draw)
        box_h = S(14) + S(22) + len(op_lines) * S(24) + S(12)
        draw_rounded_rect(draw,
                          [MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y + box_h],
                          S(6), BG_COMMUNITY_OP)
        draw.rectangle([MARGIN_X, y, MARGIN_X + S(5), y + box_h], fill=REDDIT_ORANGE)
        draw.text((left_x + S(14), y + S(12)), "ORIGINAL POST",
                  fill=REDDIT_ORANGE, font=font_section)
        op_y = y + S(36)
        for ol in op_lines:
            draw.text((left_x + S(14), op_y), ol, fill=TEXT_LIGHT, font=font_op)
            op_y += S(24)
        y += box_h + S(14)

    for callout in post["reddit_callouts"]:
        y = _render_community_callout(draw, y, callout, left_x, REDDIT_ORANGE)

    return y


def _render_forum_layout(draw, y, post, left_x):
    """Render forum thread with OP excerpt + nested quote chain."""
    font_pill = get_font(12, bold=True)
    font_section = get_font(14, bold=True)
    font_op = get_font(15)
    font_meta = get_font(11)

    meta = post["forum_meta"]
    forum_name = meta.get("forum_name", "")
    subforum = meta.get("subforum", "")
    op_author = meta.get("op_author", "")
    op_rank = meta.get("op_rank", "")
    op_post_count = meta.get("op_post_count")
    op_body = meta.get("op_body", "")

    pill_text = f"{forum_name}  \u203A  {subforum}" if subforum else forum_name
    pill_bbox = draw.textbbox((0, 0), pill_text, font=font_pill)
    pill_w = pill_bbox[2] - pill_bbox[0] + S(20)
    pill_h = S(22)
    draw_rounded_rect(draw, [MARGIN_X, y, MARGIN_X + pill_w, y + pill_h], S(6),
                      (20, 40, 60))
    draw.text((MARGIN_X + S(10), y + pill_h // 2), pill_text,
              fill=FORUM_BLUE, font=font_pill, anchor="lm")

    op_line_parts = [p for p in [op_author, op_rank,
                                 f"{op_post_count} posts" if op_post_count else None]
                     if p]
    if op_line_parts:
        draw.text((MARGIN_X + pill_w + S(12), y + pill_h // 2),
                  " \u00B7 ".join(op_line_parts),
                  fill=TEXT_MUTED, font=font_meta, anchor="lm")
    y += pill_h + S(14)

    if op_body:
        op_lines = wrap_text_lines(op_body, font_op, _community_body_wrap_width(), draw)
        box_h = S(14) + S(22) + len(op_lines) * S(24) + S(12)
        draw_rounded_rect(draw,
                          [MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y + box_h],
                          S(6), BG_COMMUNITY_OP)
        draw.rectangle([MARGIN_X, y, MARGIN_X + S(5), y + box_h], fill=FORUM_BLUE)
        draw.text((left_x + S(14), y + S(12)), "ORIGINAL POST",
                  fill=FORUM_BLUE, font=font_section)
        op_y = y + S(36)
        for ol in op_lines:
            draw.text((left_x + S(14), op_y), ol, fill=TEXT_LIGHT, font=font_op)
            op_y += S(24)
        y += box_h + S(14)

    for quoted in post["forum_quote_chain"]:
        # Single-level indent by design (source_format_design.md §4.3).
        # Deeper nesting is intentionally flattened to avoid blowing page width.
        indent = 30 if quoted.get("quoting") is not None else 0
        y = _render_community_callout(draw, y, quoted, left_x, FORUM_BLUE,
                                      indent=indent)

    return y


def _stamp_blocked_watermark(img, page_height, issue_count):
    """Overlay a publication-block warning banner on blocked posts.

    Called at the end of render_single_page when post["audit_status"] ==
    "BLOCKED" and WATERMARK_BLOCKED is True. Draws two solid bands (top and
    middle) plus a diagonal "AUDIT BLOCKED" stripe so the warning is visible
    whether someone sees the full PNG, a thumbnail, or an IG picker preview.
    """
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    banner_text = "AUDIT BLOCKED — DO NOT PUBLISH"
    detail_text = (f"{issue_count} unverified citation"
                   f"{'s' if issue_count != 1 else ''} — "
                   f"remediate before publication")

    font_banner = get_font(36, bold=True)
    font_detail = get_font(16)

    top_band_h = S(90)
    odraw.rectangle([0, 0, PAGE_WIDTH, top_band_h], fill=WATERMARK_BG)
    odraw.text((PAGE_WIDTH // 2, S(20)), banner_text,
               fill=WATERMARK_COLOR, font=font_banner, anchor="mt")
    odraw.text((PAGE_WIDTH // 2, S(65)), detail_text,
               fill=(255, 200, 200), font=font_detail, anchor="mt")

    mid_band_y = page_height // 2 - S(30)
    odraw.rectangle([0, mid_band_y, PAGE_WIDTH, mid_band_y + S(60)],
                    fill=WATERMARK_BG)
    odraw.text((PAGE_WIDTH // 2, mid_band_y + S(30)), banner_text,
               fill=WATERMARK_COLOR, font=font_banner, anchor="mm")

    bottom_band_y = page_height - S(90)
    odraw.rectangle([0, bottom_band_y, PAGE_WIDTH, bottom_band_y + S(90)],
                    fill=WATERMARK_BG)
    odraw.text((PAGE_WIDTH // 2, bottom_band_y + S(20)), banner_text,
               fill=WATERMARK_COLOR, font=font_banner, anchor="mt")
    odraw.text((PAGE_WIDTH // 2, bottom_band_y + S(65)), detail_text,
               fill=(255, 200, 200), font=font_detail, anchor="mt")

    composited = Image.alpha_composite(img.convert("RGBA"), overlay)
    return composited.convert("RGB")


def render_single_page(post, page_height):
    img = Image.new("RGB", (PAGE_WIDTH, page_height), BG_DARK)
    draw = ImageDraw.Draw(img)
    left_x = MARGIN_X + S(8)

    y = MARGIN_TOP

    # ── Top accent bar ──
    draw.rectangle([0, 0, PAGE_WIDTH, S(6)], fill=ACCENT_RED)
    y += S(8)

    # ── Author header ──
    font_author = get_font(20, bold=True)
    font_author_title = get_font(13)
    font_gym_sm = get_font(12)

    draw.text((PAGE_WIDTH // 2, y), AUTHOR_NAME,
              fill=TEXT_WHITE, font=font_author, anchor="mt")
    y += S(26)
    draw.text((PAGE_WIDTH // 2, y), AUTHOR_TITLE,
              fill=ACCENT_RED, font=font_author_title, anchor="mt")
    y += S(22)
    draw.text((PAGE_WIDTH // 2, y), f"{GYM_NAME}  |  {GYM_LOCATION}",
              fill=TEXT_MUTED, font=font_gym_sm, anchor="mt")
    y += S(20)

    # ── Red divider ──
    draw.line([(MARGIN_X, y), (PAGE_WIDTH - MARGIN_X, y)], fill=ACCENT_RED, width=S(3))
    y += S(12)

    # ── Topic badge ──
    topic = post.get("topic", "training")
    badge_bg, badge_text_color = TOPIC_COLORS.get(topic, TOPIC_COLORS["training"])
    badge_label = topic.upper()
    font_badge = get_font(10, bold=True)
    badge_bbox = draw.textbbox((0, 0), badge_label, font=font_badge)
    badge_w = badge_bbox[2] - badge_bbox[0] + S(20)
    badge_h = badge_bbox[3] - badge_bbox[1] + S(10)
    badge_x = (PAGE_WIDTH - badge_w) // 2
    badge_y = y
    draw_rounded_rect(draw, [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                      S(5), badge_bg)
    draw.text((PAGE_WIDTH // 2, badge_y + badge_h // 2), badge_label,
              fill=badge_text_color, font=font_badge, anchor="mm")
    y += badge_h + S(10)

    # ── Title ──
    font_title = get_font(32, bold=True)
    title = strip_emoji(post["title"]).upper()
    title_lines = wrap_text_lines(title, font_title, CONTENT_WIDTH, draw)
    for line in title_lines:
        draw.text((PAGE_WIDTH // 2, y), line,
                  fill=TEXT_WHITE, font=font_title, anchor="mt")
        y += S(42)
    y += S(6)

    # ── Source ──
    # Community layouts carry source info in their own header pill, so skip
    # the generic "Source: ..." line to avoid duplication.
    source = post.get("source", "")
    if source and post.get("layout") not in ("reddit_thread", "forum_thread"):
        font_source = get_font(13)
        draw.text((PAGE_WIDTH // 2, y), f"Source: {source}",
                  fill=TEXT_MUTED, font=font_source, anchor="mt")
        y += S(22)

    y += S(6)

    # ── Thin divider ──
    draw.line([(MARGIN_X + S(60), y), (PAGE_WIDTH - MARGIN_X - S(60), y)],
              fill=DIVIDER, width=S(1))
    y += S(10)

    # ── KEY STAT HIGHLIGHT BOX ──
    if post["key_stat"]:
        font_stat_label = get_font(11, bold=True)
        font_stat = get_font(16)

        stat_lines = wrap_text_lines(post["key_stat"], font_stat, CONTENT_WIDTH - S(50), draw)
        box_h = S(12) + S(20) + len(stat_lines) * S(24) + S(14)

        # Draw box with left red accent
        draw_rounded_rect(draw,
                          [MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y + box_h],
                          S(6), BG_STAT)
        draw.rectangle([MARGIN_X, y, MARGIN_X + S(5), y + box_h], fill=ACCENT_RED)

        stat_y = y + S(12)
        draw.text((left_x + S(14), stat_y), "KEY FINDING",
                  fill=ACCENT_RED, font=font_stat_label)
        stat_y += S(20)
        for sl in stat_lines:
            draw.text((left_x + S(14), stat_y), sl, fill=TEXT_WHITE, font=font_stat)
            stat_y += S(24)

        y += box_h + S(12)

    # ── OVERVIEW ──
    if post["intro_text"]:
        font_section_hdr = get_font(14, bold=True)
        font_intro = get_font(17)

        # Red accent bar + header
        draw.rectangle([MARGIN_X, y, MARGIN_X + S(4), y + S(20)], fill=ACCENT_RED)
        draw.text((left_x + S(12), y), "OVERVIEW", fill=ACCENT_RED, font=font_section_hdr)
        y += S(26)

        intro_lines = wrap_text_lines(post["intro_text"], font_intro,
                                      CONTENT_WIDTH - S(20), draw)
        for line in intro_lines:
            draw.text((left_x + S(8), y), line, fill=TEXT_LIGHT, font=font_intro)
            y += S(24)
        y += S(12)

        draw.line([(MARGIN_X + S(60), y), (PAGE_WIDTH - MARGIN_X - S(60), y)],
                  fill=DIVIDER, width=S(1))
        y += S(10)

    # ── LAYOUT-SPECIFIC SECTIONS ──
    layout = post.get("layout", "default")

    if layout == "program" and post["program_phases"]:
        y = _render_program_layout(draw, y, post, left_x)
    if layout == "mythbust" and post["myths"]:
        y = _render_mythbust_layout(draw, y, post, left_x)
    if layout == "rehab" and post["rehab_steps"]:
        y = _render_rehab_layout(draw, y, post, left_x)
    if layout == "reddit_thread":
        y = _render_reddit_layout(draw, y, post, left_x)
    if layout == "forum_thread":
        y = _render_forum_layout(draw, y, post, left_x)
    if layout == "supplement" and post.get("supplement_facts"):
        y = _render_supplement_facts(draw, y, post, left_x)

    # ── NUMBERED POINTS ──
    font_num = get_font(16, bold=True)
    font_head = get_font(19, bold=True)
    font_body = get_font(16)

    points_to_render = post["numbered_points"][:8]
    use_sections_fallback = not points_to_render and post["sections"]

    if use_sections_fallback:
        for sec in post["sections"][:8]:
            y += S(6)
            header = strip_emoji(sec.get("header", "")).upper()
            if header:
                draw.rectangle([MARGIN_X, y, MARGIN_X + S(4), y + S(20)], fill=ACCENT_RED)
                draw.text((left_x + S(12), y), header, fill=ACCENT_RED, font=font_head)
                head_lines = wrap_text_lines(header, font_head, CONTENT_WIDTH - S(25), draw)
                y += len(head_lines) * S(26) + S(4)
            body = strip_emoji(sec.get("body", ""))
            if body:
                body_lines = wrap_text_lines(body, font_body, CONTENT_WIDTH - S(25), draw)
                for bl in body_lines:
                    draw.text((left_x + S(12), y), bl, fill=TEXT_LIGHT, font=font_body)
                    y += S(23)
            y += S(10)

    for pt in points_to_render:
        num = pt.get("number", 0)
        headline = strip_emoji(pt.get("headline", "")).upper()
        body = strip_emoji(pt.get("body", ""))

        # Calculate card height for background
        card_y_start = y
        temp_y = y + S(10)
        if headline:
            h_lines = wrap_text_lines(headline, font_head, CONTENT_WIDTH - S(60), draw)
            temp_y += len(h_lines) * S(26) + S(4)
        if body:
            b_lines = wrap_text_lines(body, font_body, CONTENT_WIDTH - S(60), draw)
            temp_y += len(b_lines) * S(23)
        temp_y += S(10)
        card_h = temp_y - card_y_start

        # Draw background card
        draw_rounded_rect(draw,
                          [MARGIN_X + S(3), y, PAGE_WIDTH - MARGIN_X - S(3), y + card_h],
                          S(8), BG_CARD)

        y += S(10)

        # Number circle
        cx = left_x + S(18)
        cy = y + S(11)
        r = S(15)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT_RED)
        draw.text((cx, cy), str(num),
                  fill=TEXT_WHITE, font=font_num, anchor="mm")

        text_x = left_x + S(44)

        # Headline
        content_y = y
        if headline:
            head_lines = wrap_text_lines(headline, font_head, CONTENT_WIDTH - S(60), draw)
            for hl in head_lines:
                draw.text((text_x, content_y), hl, fill=TEXT_WHITE, font=font_head)
                content_y += S(26)
            content_y += S(3)

        # Body
        if body:
            body_lines = wrap_text_lines(body, font_body, CONTENT_WIDTH - S(60), draw)
            for bl in body_lines:
                draw.text((text_x, content_y), bl, fill=TEXT_LIGHT, font=font_body)
                content_y += S(23)

        y = card_y_start + card_h + S(6)

    y += S(4)

    # ── EXTRA SECTIONS (WHAT STAYS, WHAT TO AVOID, etc.) ──
    if post["extra_sections"]:
        for sec in post["extra_sections"][:3]:
            header = strip_emoji(sec["header"]).upper()
            body = strip_emoji(sec["body"])

            draw.rectangle([MARGIN_X, y, MARGIN_X + S(4), y + S(20)], fill=ACCENT_RED)
            draw.text((left_x + S(12), y), header, fill=ACCENT_RED, font=font_head)
            head_lines = wrap_text_lines(header, font_head, CONTENT_WIDTH - S(25), draw)
            y += len(head_lines) * S(26) + S(4)

            body_lines = wrap_text_lines(body, font_body, CONTENT_WIDTH - S(25), draw)
            for bl in body_lines:
                draw.text((left_x + S(12), y), bl, fill=TEXT_LIGHT, font=font_body)
                y += S(23)
            y += S(12)

    # ── PRACTICAL GUIDE ──
    if post["practical_guide"]:
        draw.line([(MARGIN_X, y), (PAGE_WIDTH - MARGIN_X, y)],
                  fill=ACCENT_RED, width=S(2))
        y += S(12)

        font_guide_hdr = get_font(14, bold=True)
        font_bullet = get_font(15)
        font_bullet_marker = get_font(12, bold=True)

        header_text = post["practical_guide_header"] or "PRACTICAL GUIDE"
        draw.rectangle([MARGIN_X, y, MARGIN_X + S(4), y + S(20)], fill=ACCENT_RED)
        draw.text((left_x + S(12), y), header_text.upper(),
                  fill=ACCENT_RED, font=font_guide_hdr)
        y += S(26)

        for item in post["practical_guide"]:
            draw.text((left_x + S(8), y + S(2)), "\u25B8",
                      fill=ACCENT_RED, font=font_bullet_marker)
            item_lines = wrap_text_lines(item, font_bullet,
                                         CONTENT_WIDTH - S(45), draw)
            for il in item_lines:
                draw.text((left_x + S(24), y), il, fill=TEXT_LIGHT, font=font_bullet)
                y += S(22)
            y += S(5)

        y += S(8)

    # ── SUMMARY / BOTTOM LINE ──
    if post["summary_text"]:
        draw.line([(MARGIN_X, y), (PAGE_WIDTH - MARGIN_X, y)],
                  fill=ACCENT_RED, width=S(2))
        y += S(12)

        font_sum_hdr = get_font(14, bold=True)
        font_summary = get_font(17)

        # Summary box with red left accent
        summary_lines = wrap_text_lines(post["summary_text"], font_summary,
                                        CONTENT_WIDTH - S(40), draw)
        box_h = S(10) + S(24) + len(summary_lines) * S(24) + S(12)

        draw_rounded_rect(draw,
                          [MARGIN_X, y, PAGE_WIDTH - MARGIN_X, y + box_h],
                          S(6), BG_CARD)
        draw.rectangle([MARGIN_X, y, MARGIN_X + S(5), y + box_h], fill=ACCENT_RED)

        y += S(10)
        draw.text((left_x + S(14), y), "THE BOTTOM LINE",
                  fill=ACCENT_RED, font=font_sum_hdr)
        y += S(24)

        for sl in summary_lines:
            draw.text((left_x + S(14), y), sl, fill=TEXT_WHITE, font=font_summary)
            y += S(24)

        y += S(14)

    # ── Red divider ──
    draw.line([(MARGIN_X, y), (PAGE_WIDTH - MARGIN_X, y)],
              fill=ACCENT_RED, width=S(2))
    y += S(10)

    # ── REFERENCES with DOI/URL formatting ──
    if post["references"]:
        font_ref_header = get_font(12, bold=True)
        font_ref = get_font(11)
        font_doi = get_font(10)

        draw.text((left_x, y), "REFERENCES", fill=ACCENT_RED, font=font_ref_header)
        y += S(22)

        for ref in post["references"]:
            ref_clean = strip_emoji(ref)
            # Split DOI/URL from the main reference text
            doi_match = re.search(r'(doi:\S+|https?://\S+)', ref_clean, re.I)
            if doi_match:
                main_text = ref_clean[:doi_match.start()].strip()
                doi_text = doi_match.group(1)
            else:
                main_text = ref_clean
                doi_text = ""

            # Render main reference text
            main_lines = wrap_text_lines(main_text, font_ref, CONTENT_WIDTH - S(20), draw)
            for rl in main_lines:
                draw.text((left_x + S(6), y), rl, fill=TEXT_REF, font=font_ref)
                y += S(16)

            # Render DOI/URL in accent blue
            if doi_text:
                doi_lines = wrap_text_lines(doi_text, font_doi, CONTENT_WIDTH - S(30), draw)
                for dl in doi_lines:
                    draw.text((left_x + S(14), y), dl, fill=TEXT_DOI, font=font_doi)
                    y += S(14)

            y += S(4)
        y += S(8)

    # ── Divider ──
    draw.line([(MARGIN_X, y), (PAGE_WIDTH - MARGIN_X, y)],
              fill=DIVIDER, width=S(1))
    y += S(14)

    # ── Author footer ──
    font_cta_name = get_font(16, bold=True)
    font_cta = get_font(12)

    draw.text((PAGE_WIDTH // 2, y), f"{AUTHOR_NAME}  \u2014  {AUTHOR_TITLE}",
              fill=TEXT_WHITE, font=font_cta_name, anchor="mt")
    y += S(24)
    draw.text((PAGE_WIDTH // 2, y), PERSONAL_CTA,
              fill=ACCENT_RED, font=font_cta, anchor="mt")
    y += S(20)
    draw.text((PAGE_WIDTH // 2, y),
              f"Call/Text: {AUTHOR_PHONE}  |  {GYM_WEB}",
              fill=TEXT_MUTED, font=font_cta, anchor="mt")
    y += S(26)

    # ── Gym footer ──
    font_gym_big = get_font(18, bold=True)
    font_gym_sm2 = get_font(12)

    draw.text((PAGE_WIDTH // 2, y), GYM_NAME.upper(),
              fill=ACCENT_RED, font=font_gym_big, anchor="mt")
    y += S(26)
    draw.text((PAGE_WIDTH // 2, y),
              f"{GYM_LOCATION}  |  {GYM_WEB}  |  {GYM_PHONE}",
              fill=TEXT_MUTED, font=font_gym_sm2, anchor="mt")

    # ── Bottom accent bar ──
    draw.rectangle([0, page_height - S(6), PAGE_WIDTH, page_height], fill=ACCENT_RED)

    if WATERMARK_BLOCKED and post.get("audit_status") == "BLOCKED":
        img = _stamp_blocked_watermark(
            img, page_height, post.get("audit_issue_count", 0))

    return img


# ── Main ─────────────────────────────────────────────────────────────────────


def _read_audit_meta(draft_path):
    """Load audit fields from the per-topic meta.json sibling of a draft.

    Returns a dict with `audit_status` (str) and `audit_issues` (list).
    Missing/malformed meta.json returns the safe defaults — empty status and
    empty issue list — which means no watermark will fire. Fail-safe by design:
    a corrupt meta should degrade to "render clean", not "render broken".
    """
    meta_path = Path(draft_path).parent.parent / "meta.json"
    if not meta_path.exists():
        return {"audit_status": "", "audit_issues": []}
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"audit_status": "", "audit_issues": []}
    return {
        "audit_status": meta.get("audit_status", ""),
        "audit_issues": meta.get("audit_issues", []),
    }


def _discover_topic_drafts():
    """Yield (topic_slug, draft_path, output_png_path) for each per-topic
    English draft in the new Posts/<slug>/en/ layout. Falls back to the
    legacy flat Posts/polished/ layout if no per-topic dirs exist."""
    topic_drafts = []
    for topic_dir in sorted(POSTS_DIR.iterdir()):
        if not topic_dir.is_dir():
            continue
        draft = topic_dir / "en" / "draft.txt"
        if draft.exists():
            png = topic_dir / "en" / "single_page.png"
            topic_drafts.append((topic_dir.name, draft, png))
    if topic_drafts:
        return topic_drafts

    polished_dir = POSTS_DIR / "polished"
    output_dir = POSTS_DIR / "single_pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    for txt_file in sorted(polished_dir.glob("*.txt")):
        topic_drafts.append((txt_file.stem, txt_file, output_dir / f"{txt_file.stem}.png"))
    return topic_drafts


def generate_all_single_pages():
    topic_drafts = _discover_topic_drafts()
    if not topic_drafts:
        print("[INFO] No polished posts found.")
        return

    print(f"\n{'='*60}")
    print(f"  DETAILED SINGLE-PAGE GENERATOR (3x resolution)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Author: {AUTHOR_NAME}, {AUTHOR_TITLE}")
    print(f"  Posts: {len(topic_drafts)}")
    print(f"  Output: {PAGE_WIDTH}px wide @ {SCALE}x scale")
    print(f"{'='*60}\n")

    all_pages = []
    tmp_img = Image.new("RGB", (PAGE_WIDTH, 100))
    tmp_draw = ImageDraw.Draw(tmp_img)

    for slug, txt_file, png_path in topic_drafts:
        post = parse_detailed_content(txt_file)
        audit_meta = _read_audit_meta(txt_file)
        post["audit_status"] = audit_meta["audit_status"]
        post["audit_issue_count"] = len(audit_meta["audit_issues"])
        page_height = calculate_page_height(post, tmp_draw)
        page_img = render_single_page(post, page_height)

        png_path.parent.mkdir(parents=True, exist_ok=True)
        page_img.save(png_path, "PNG", optimize=True)
        all_pages.append((png_path, page_img))

        n_pts = len(post["numbered_points"]) or len(post["sections"])
        n_extra = len(post["extra_sections"])
        n_guide = len(post["practical_guide"])
        ev_level = post.get("evidence_info", {}).get("level", "-")
        layout = post.get("layout", "default")

        audit_tag = ""
        if post.get("audit_status") == "BLOCKED":
            audit_tag = f" [BLOCKED: {post.get('audit_issue_count', 0)} issues]"
        elif post.get("audit_status") == "WARN":
            audit_tag = f" [WARN: {post.get('audit_issue_count', 0)} soft flags]"

        print(f"[PAGE] {strip_emoji(post['title'])[:55]}...{audit_tag}")
        print(f"  {n_pts} points, {n_extra} extra, {n_guide} guide, "
              f"{len(post['references'])} refs | "
              f"layout={layout} evidence={ev_level} | "
              f"intro={'Y' if post['intro_text'] else '-'} "
              f"stat={'Y' if post['key_stat'] else '-'} "
              f"summary={'Y' if post['summary_text'] else '-'} | "
              f"{page_height}px")

    tmp_img.close()

    if all_pages:
        pdf_path = POSTS_DIR / "pdfs" / "all_single_pages.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)

        first_img = all_pages[0][1].convert("RGB")
        append_imgs = [p[1].convert("RGB") for p in all_pages[1:]]

        first_img.save(
            str(pdf_path), "PDF",
            resolution=float(PDF_DPI),
            save_all=True,
            append_images=append_imgs,
        )

        first_img.close()
        for aimg in append_imgs:
            aimg.close()
        for _, pimg in all_pages:
            pimg.close()

        print(f"\n[PDF] Combined PDF: {pdf_path} ({len(all_pages)} pages)")

    print(f"\n[DONE] {len(all_pages)} detailed single-page posts written to per-topic Posts/<slug>/en/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Render all ContentPrinter posts to single-page PNGs.")
    parser.add_argument(
        "--no-watermark",
        action="store_true",
        help="Skip the AUDIT BLOCKED watermark on posts with "
             "audit_status=BLOCKED. Use for clean before/after diffing "
             "during #31 remediation. DO NOT use for posts you intend to "
             "publish.",
    )
    args = parser.parse_args()
    if args.no_watermark:
        WATERMARK_BLOCKED = False
        print("[WARN] --no-watermark: BLOCKED posts will render without "
              "warning overlay. For remediation diffs only — do not publish.")
    generate_all_single_pages()
