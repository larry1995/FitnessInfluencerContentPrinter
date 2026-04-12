"""
Instagram Image Generator for Central Strength Gym
Creates branded carousel slide images from POLISHED posts.
Reads from Posts/polished/*.txt — the human-refined content.
Also outputs markdown files for each post.
"""

import json
import re
import shutil
import textwrap
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "Posts"

# Brand colors
COLORS = {
    "bg_dark": (20, 20, 20),
    "accent_red": (182, 29, 32),
    "text_white": (255, 255, 255),
    "text_light": (200, 200, 200),
    "text_muted": (140, 140, 140),
    "divider": (60, 60, 60),
}

# Render at 2x for sharper Instagram uploads
SCALE = 2
WIDTH = 1080 * SCALE
HEIGHT = 1080 * SCALE
MARGIN = 80 * SCALE

# Contact info loaded from config
def _load_brand_config():
    with open(CONFIG_DIR / "sources.json") as f:
        return json.load(f)["brand"]

_brand = _load_brand_config()


def S(val):
    """Scale a pixel value by the SCALE factor."""
    return int(val * SCALE)


def get_font(size, bold=False):
    """Get a font at the given logical size, scaled for output resolution."""
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


def strip_emoji(text):
    """Remove emoji characters that can't render in the font."""
    # Remove common emoji ranges
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U00002600-\U000026FF"  # misc symbols
        "\U0000FE00-\U0000FE0F"  # variation selectors
        "\U0000200D"  # zero-width joiner
        "\U00000023\U0000FE0F\U000020E3"  # keycap
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub("", text).strip()


def parse_polished_file(filepath):
    """Parse a polished .txt file and extract structured content."""
    with open(filepath) as f:
        text = f.read()

    post = {
        "filename": filepath.name,
        "title": "",
        "source": "",
        "topic": "",
        "caption": "",
        "numbered_points": [],
        "sections": [],
        "suggested_visual": "",
    }

    # Extract source line
    source_match = re.search(r"Source:\s*(.+?)(?:\s*\(|$)", text, re.MULTILINE)
    if source_match:
        post["source"] = source_match.group(1).strip()

    # Extract topic from filename
    if "nutrition" in filepath.name.lower():
        post["topic"] = "nutrition"
    elif "technique" in filepath.name.lower():
        post["topic"] = "techniques"
    else:
        post["topic"] = "training"

    # Extract caption between dash separator lines (40 dashes, not bullet dashes)
    caption_match = re.search(
        r"CAPTION:\s*\n-{10,}\n(.+?)\n-{10,}",
        text, re.DOTALL
    )
    if caption_match:
        post["caption"] = caption_match.group(1).strip()

    # Extract title (first non-empty line of caption, strip emoji prefix)
    caption_lines = post["caption"].split("\n")
    for line in caption_lines:
        line = line.strip()
        if line and not line.startswith("#"):
            post["title"] = strip_emoji(line).strip(" —-:")
            break

    # Extract numbered points with headers and descriptions
    # Patterns like: "1. WRONG GRIP WIDTH\nToo wide = shoulder stress..."
    # or "1️⃣ NARROW YOUR GRIP\nWider grip = more shoulder stress..."
    # Uses MULTILINE so ^ matches line starts, preventing title lines like
    # "5 MISTAKES KILLING YOUR BENCH" from being falsely captured as point #5
    point_pattern = re.compile(
        r'^(?:(\d)[.)\s]\s*|(\d)\uFE0F?\u20E3\s*)'    # number + separator + optional space
        r'([^\n]{1,80})\n'                                  # headline (max 80 chars — excludes long reference lines)
        r'((?:(?!\n\n|^\d[.)]\s|^\d\uFE0F?\u20E3).)*)',  # body until next point or blank line (zero-length OK)
        re.DOTALL | re.MULTILINE
    )

    for m in point_pattern.finditer(post["caption"]):
        num = m.group(1) or m.group(2)
        headline = m.group(3).strip()
        body = m.group(4).strip()
        # Clean up body — remove emoji, clean whitespace
        body = strip_emoji(body)
        body = re.sub(r'\s+', ' ', body).strip()
        if len(body) > 250:
            body = body[:247] + "..."
        post["numbered_points"].append({
            "number": int(num),
            "headline": headline,
            "body": body,
        })

    # If no structured points found, try simpler patterns
    if not post["numbered_points"]:
        # Try: lines starting with bullet-like markers
        simple_pattern = re.compile(
            r'[•✅❌⚠→]\s*(.+?)(?:\n|$)'
        )
        for i, m in enumerate(simple_pattern.finditer(post["caption"]), 1):
            text_content = strip_emoji(m.group(1)).strip()
            if len(text_content) > 15:
                post["numbered_points"].append({
                    "number": i,
                    "headline": "",
                    "body": text_content[:250],
                })
            if i >= 6:
                break

    # Extract SECTION headers (lines in ALL CAPS followed by content)
    # Matches both colon-terminated headers ("THE RESEARCH:") and
    # emoji-prefixed headers ("🍳 BREAKFAST", "🥩 MEALS 2-4")
    section_pattern = re.compile(
        r'\n(?:'
        r'([A-Z][A-Z\s0-9:&/\-]+:)'         # ALL CAPS header with colon (digits allowed)
        r'|'
        r'(?:[\U0001F300-\U0001FAFF]\uFE0F?\s*)'  # emoji prefix
        r'([A-Z][A-Z\s0-9:&/\-]+)'          # ALL CAPS header after emoji
        r')\s*\n'
        r'((?:(?!\n(?:[A-Z][A-Z\s:&/\-]+:|\S*[\U0001F300-\U0001FAFF])).)+)',  # body
        re.DOTALL
    )
    for m in section_pattern.finditer(post["caption"]):
        header = (m.group(1) or m.group(2) or "").strip().rstrip(":")
        body = m.group(3).strip()
        body = strip_emoji(body)
        body = re.sub(r'\s+', ' ', body)
        if len(body) > 20:
            post["sections"].append({"header": header, "body": body[:300]})

    # Suggested visual
    vis_match = re.search(r"SUGGESTED VISUAL:\s*(.+)", text)
    if vis_match:
        post["suggested_visual"] = vis_match.group(1).strip()

    return post


# ── Slide creation functions ──

def draw_branded_frame(draw):
    """Draw the standard branded frame (red bars top/bottom)."""
    draw.rectangle([0, 0, WIDTH, S(8)], fill=COLORS["accent_red"])
    draw.rectangle([0, HEIGHT - S(8), WIDTH, HEIGHT], fill=COLORS["accent_red"])


def draw_gym_header(draw):
    """Draw gym name at top."""
    font = get_font(28, bold=True)
    draw.text((WIDTH // 2, S(55)), "CENTRAL STRENGTH",
              fill=COLORS["accent_red"], font=font, anchor="mm")
    draw.line([(MARGIN, S(90)), (WIDTH - MARGIN, S(90))], fill=COLORS["divider"], width=S(1))


def draw_gym_footer(draw):
    """Draw gym name at bottom."""
    font = get_font(22, bold=True)
    draw.text((WIDTH // 2, HEIGHT - S(50)), "CENTRAL STRENGTH",
              fill=COLORS["accent_red"], font=font, anchor="mm")


def draw_wrapped_text(draw, text, x, y, font, fill, max_width_chars=32, line_height=None):
    """Draw text with word wrapping. Returns the y position after the last line."""
    if line_height is None:
        line_height = font.size + S(10)
    wrapped = textwrap.fill(text, width=max_width_chars)
    lines = wrapped.split("\n")
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_height), line, fill=fill, font=font, anchor="mm")
    return y + len(lines) * line_height


def create_title_slide(title, source=""):
    """Slide 1: Bold title with source."""
    img = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)
    draw_branded_frame(draw)
    draw_gym_header(draw)

    # Title — adaptive font size
    clean_title = strip_emoji(title).upper()
    if len(clean_title) > 60:
        font_size, wrap_width = 40, 26
    elif len(clean_title) > 40:
        font_size, wrap_width = 46, 22
    else:
        font_size, wrap_width = 52, 20

    font_title = get_font(font_size, bold=True)
    wrapped = textwrap.fill(clean_title, width=wrap_width)
    lines = wrapped.split("\n")
    line_h = S(font_size + 14)
    y_start = HEIGHT // 2 - (len(lines) * line_h) // 2
    for i, line in enumerate(lines):
        draw.text((WIDTH // 2, y_start + i * line_h), line,
                  fill=COLORS["text_white"], font=font_title, anchor="mm")

    # Source
    if source:
        font_src = get_font(22)
        draw.text((WIDTH // 2, HEIGHT - S(120)),
                  f"Science-backed insights from {source}",
                  fill=COLORS["text_muted"], font=font_src, anchor="mm")

    return img


def create_content_slide(number, headline, body):
    """Slide 2-N: Numbered point with headline and body text."""
    img = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)
    draw_branded_frame(draw)

    # Number circle
    cx, cy, r = WIDTH // 2, S(150), S(55)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=COLORS["accent_red"])
    draw.text((cx, cy), str(number),
              fill=COLORS["text_white"], font=get_font(48, bold=True), anchor="mm")

    # Headline
    y = S(260)
    if headline:
        clean_headline = strip_emoji(headline).upper()
        font_head = get_font(32, bold=True)
        # Wrap if long
        if len(clean_headline) > 28:
            lines = textwrap.fill(clean_headline, width=28).split("\n")
        else:
            lines = [clean_headline]
        for line in lines:
            draw.text((WIDTH // 2, y), line,
                      fill=COLORS["text_white"], font=font_head, anchor="mm")
            y += S(44)
        y += S(20)

    # Body text
    if body:
        clean_body = strip_emoji(body)
        font_body = get_font(26)
        # Calculate available space
        available_height = (HEIGHT - S(100)) - y  # footer space
        max_lines = available_height // S(38)

        wrapped = textwrap.fill(clean_body, width=36)
        lines = wrapped.split("\n")[:max_lines]
        for line in lines:
            draw.text((WIDTH // 2, y), line,
                      fill=COLORS["text_light"], font=font_body, anchor="mm")
            y += S(38)

    draw_gym_footer(draw)
    draw_branded_frame(draw)
    return img


def create_section_slide(header, body):
    """Alternative slide for section-based content (WHAT TO LOOK FOR, etc.)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg_dark"])
    draw = ImageDraw.Draw(img)
    draw_branded_frame(draw)

    # Section header in red
    font_head = get_font(34, bold=True)
    clean_header = strip_emoji(header).upper()
    draw.text((WIDTH // 2, S(160)), clean_header,
              fill=COLORS["accent_red"], font=font_head, anchor="mm")

    # Divider
    draw.line([(S(200), S(210)), (WIDTH - S(200), S(210))], fill=COLORS["divider"], width=S(2))

    # Body
    clean_body = strip_emoji(body)
    font_body = get_font(26)
    wrapped = textwrap.fill(clean_body, width=36)
    lines = wrapped.split("\n")[:18]
    y = S(270)
    for line in lines:
        draw.text((WIDTH // 2, y), line,
                  fill=COLORS["text_light"], font=font_body, anchor="mm")
        y += S(38)

    draw_gym_footer(draw)
    draw_branded_frame(draw)
    return img


def create_cta_slide():
    """Final slide: Call to action with contact info from config."""
    img = Image.new("RGB", (WIDTH, HEIGHT), COLORS["accent_red"])
    draw = ImageDraw.Draw(img)

    font_big = get_font(52, bold=True)
    font_med = get_font(32, bold=True)
    font_sm = get_font(24)

    gym_name = _brand.get("full_gym_name", _brand.get("gym_name", ""))
    location = _brand.get("location", "")
    website = _brand.get("website", "")
    phone = _brand.get("gym_phone", "")

    draw.text((WIDTH // 2, S(300)), "READY TO GET", fill=COLORS["text_white"],
              font=font_big, anchor="mm")
    draw.text((WIDTH // 2, S(370)), "STRONGER?", fill=COLORS["text_white"],
              font=font_big, anchor="mm")

    draw.line([(S(200), S(440)), (WIDTH - S(200), S(440))], fill=COLORS["text_white"], width=S(2))

    draw.text((WIDTH // 2, S(520)), gym_name.upper(),
              fill=COLORS["text_white"], font=font_med, anchor="mm")
    draw.text((WIDTH // 2, S(575)), location,
              fill=COLORS["text_light"], font=font_sm, anchor="mm")
    draw.text((WIDTH // 2, S(680)), website,
              fill=COLORS["text_white"], font=font_sm, anchor="mm")
    draw.text((WIDTH // 2, S(725)), phone,
              fill=COLORS["text_white"], font=font_sm, anchor="mm")
    draw.text((WIDTH // 2, S(850)), "Book your FREE intro session",
              fill=COLORS["text_white"], font=font_med, anchor="mm")
    draw.text((WIDTH // 2, S(900)), "Link in bio",
              fill=COLORS["text_light"], font=font_sm, anchor="mm")

    return img


# ── Markdown output ──

def save_markdown(post, md_dir):
    """Save a markdown version of the post."""
    fname = post["filename"].replace(".txt", ".md")
    md_path = md_dir / fname

    lines = [
        f"# {strip_emoji(post['title'])}",
        "",
        f"**Source:** {post['source']}",
        f"**Topic:** {post['topic']}",
        "",
        "---",
        "",
        "## Caption",
        "",
        post["caption"],
        "",
        "---",
        "",
    ]

    if post["numbered_points"]:
        lines.append("## Key Points\n")
        for pt in post["numbered_points"]:
            if pt["headline"]:
                lines.append(f"### {pt['number']}. {pt['headline']}")
            else:
                lines.append(f"### Point {pt['number']}")
            lines.append(f"{pt['body']}\n")

    if post["suggested_visual"]:
        lines.append(f"## Suggested Visual\n{post['suggested_visual']}\n")

    with open(md_path, "w") as f:
        f.write("\n".join(lines))

    return md_path


# ── Main generation ──

def generate_post_images(post, images_dir):
    """Generate all carousel slides for one polished post."""
    # Determine folder name from filename
    stem = post["filename"].replace(".txt", "")
    post_dir = images_dir / stem
    post_dir.mkdir(parents=True, exist_ok=True)

    slides = []
    slide_num = 1

    # Slide 1: Title
    img = create_title_slide(post["title"], post["source"])
    path = post_dir / f"slide_{slide_num:02d}.png"
    img.save(path, "PNG", optimize=True)
    slides.append(path)
    slide_num += 1

    # Decide whether to use numbered points or sections for content slides.
    # Prefer sections when: (a) points lack headlines and have sparse body text,
    # AND (b) sections would produce at least as many slides as points would.
    usable_sections = [s for s in post["sections"] if len(s["body"]) > 30]
    has_rich_points = post["numbered_points"] and any(
        pt["headline"] or len(pt["body"]) > 60 for pt in post["numbered_points"]
    )
    use_sections = (
        not has_rich_points
        and usable_sections
        and len(usable_sections) >= len(post["numbered_points"])
    )

    if use_sections:
        for sec in usable_sections[:6]:
            img = create_section_slide(sec["header"], sec["body"])
            path = post_dir / f"slide_{slide_num:02d}.png"
            img.save(path, "PNG", optimize=True)
            slides.append(path)
            slide_num += 1
    elif post["numbered_points"]:
        for pt in post["numbered_points"]:
            img = create_content_slide(pt["number"], pt["headline"], pt["body"])
            path = post_dir / f"slide_{slide_num:02d}.png"
            img.save(path, "PNG", optimize=True)
            slides.append(path)
            slide_num += 1
    elif usable_sections:
        for sec in usable_sections[:6]:
            img = create_section_slide(sec["header"], sec["body"])
            path = post_dir / f"slide_{slide_num:02d}.png"
            img.save(path, "PNG", optimize=True)
            slides.append(path)
            slide_num += 1

    # Final slide: CTA
    img = create_cta_slide()
    path = post_dir / f"slide_{slide_num:02d}.png"
    img.save(path, "PNG", optimize=True)
    slides.append(path)

    return slides


def generate_all_images():
    """Generate images from all polished posts."""
    polished_dir = POSTS_DIR / "polished"
    images_dir = POSTS_DIR / "images"
    md_dir = POSTS_DIR / "markdown"

    # Clean old images
    if images_dir.exists():
        shutil.rmtree(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(polished_dir.glob("*.txt"))
    if not txt_files:
        print("[INFO] No polished posts found in Posts/polished/. Polish your drafts first.")
        return

    print(f"\n{'='*60}")
    print(f"  IMAGE GENERATOR — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Polished posts: {len(txt_files)}")
    print(f"{'='*60}\n")

    total_images = 0
    for txt_file in txt_files:
        post = parse_polished_file(txt_file)
        print(f"[IMAGE] {post['title'][:55]}...")
        print(f"  Points extracted: {len(post['numbered_points'])}, Sections: {len(post['sections'])}")

        slides = generate_post_images(post, images_dir)
        total_images += len(slides)
        print(f"  Created {len(slides)} slides")

        # Also save markdown
        md_path = save_markdown(post, md_dir)
        print(f"  Markdown: {md_path.name}")

    print(f"\n[DONE] {total_images} images -> {images_dir}/")
    print(f"[DONE] Markdown files -> {md_dir}/")


if __name__ == "__main__":
    generate_all_images()
