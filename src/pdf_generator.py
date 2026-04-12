"""
PDF Generator for Central Strength Gym carousel posts.

Reads PNG carousel slides from Posts/images/, groups them by topic,
and produces per-topic PDFs plus a combined all_posts PDF with divider pages.

Uses Pillow (PIL) for image reading and native PDF export.
"""

import re
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).parent.parent
IMAGES_DIR = PROJECT_ROOT / "Posts" / "images"
PDFS_DIR = PROJECT_ROOT / "Posts" / "pdfs"

# Slide dimensions (must match image_generator.py)
WIDTH = 1080
HEIGHT = 1080

# Brand colors (must match image_generator.py)
BG_DARK = (20, 20, 20)
ACCENT_RED = (182, 29, 32)
TEXT_WHITE = (255, 255, 255)

# Font path
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Load DejaVuSans-Bold at the requested size, with a safe fallback."""
    if Path(FONT_BOLD_PATH).exists():
        return ImageFont.truetype(FONT_BOLD_PATH, size)
    return ImageFont.load_default()


def _extract_topic(folder_name: str) -> str:
    """
    Extract the topic from a post folder name.

    Examples:
        'post01_nutrition' -> 'nutrition'
        'post04_training'  -> 'training'
        'post10_techniques' -> 'techniques'

    Falls back to the full folder name if no underscore-separated
    topic suffix is found.
    """
    match = re.match(r"^post\d+_(.+)$", folder_name)
    if match:
        return match.group(1).lower()
    return folder_name.lower()


def _collect_slides_by_topic() -> dict[str, list[Path]]:
    """
    Scan Posts/images/ and group slide PNGs by topic.

    Returns a dict mapping topic names to sorted lists of slide paths.
    Topics with no slides are excluded.
    """
    topic_slides: dict[str, list[Path]] = defaultdict(list)

    if not IMAGES_DIR.is_dir():
        print(f"[PDF] Images directory not found: {IMAGES_DIR}")
        return {}

    for post_dir in sorted(IMAGES_DIR.iterdir()):
        if not post_dir.is_dir():
            continue
        topic = _extract_topic(post_dir.name)
        slides = sorted(post_dir.glob("*.png"))
        if slides:
            topic_slides[topic].extend(slides)

    return dict(topic_slides)


def _load_slide(path: Path) -> Image.Image:
    """Load a PNG slide and convert to RGB for PDF compatibility."""
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _create_divider_page(topic: str) -> Image.Image:
    """
    Create a 1080x1080 topic divider page for the all_posts PDF.

    Layout:
      - Dark background (20, 20, 20)
      - Red accent bar at top and bottom (182, 29, 32)
      - Topic name in large white bold text, centered
      - Subtitle "Central Strength Gym" in red below the topic
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Red accent bars (top and bottom)
    bar_height = 12
    draw.rectangle([0, 0, WIDTH, bar_height], fill=ACCENT_RED)
    draw.rectangle([0, HEIGHT - bar_height, WIDTH, HEIGHT], fill=ACCENT_RED)

    # Topic name — large bold white text
    font_topic = _get_font(96)
    topic_text = topic.upper()
    bbox = draw.textbbox((0, 0), topic_text, font=font_topic)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x_topic = (WIDTH - text_w) // 2
    y_topic = (HEIGHT - text_h) // 2 - 40  # offset up slightly for subtitle room

    draw.text((x_topic, y_topic), topic_text, fill=TEXT_WHITE, font=font_topic)

    # Subtitle — smaller, red text
    font_sub = _get_font(36)
    subtitle = "Central Strength Gym"
    bbox_sub = draw.textbbox((0, 0), subtitle, font=font_sub)
    sub_w = bbox_sub[2] - bbox_sub[0]
    x_sub = (WIDTH - sub_w) // 2
    y_sub = y_topic + text_h + 30

    draw.text((x_sub, y_sub), subtitle, fill=ACCENT_RED, font=font_sub)

    return img


def generate_topic_pdf(topic: str, slide_paths: list[Path]) -> Path | None:
    """
    Generate a single PDF containing all slides for one topic.

    Returns the output path, or None if there are no slides.
    """
    if not slide_paths:
        return None

    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PDFS_DIR / f"{topic}_posts.pdf"

    first_img = _load_slide(slide_paths[0])
    append_imgs = [_load_slide(p) for p in slide_paths[1:]]

    first_img.save(
        str(out_path),
        "PDF",
        resolution=100.0,
        save_all=True,
        append_images=append_imgs,
    )

    # Close images to free memory
    first_img.close()
    for img in append_imgs:
        img.close()

    print(f"[PDF] Created {out_path.name}  ({len(slide_paths)} pages)")
    return out_path


def generate_all_posts_pdf(topic_slides: dict[str, list[Path]]) -> Path | None:
    """
    Generate a combined PDF with ALL slides, grouped by topic.
    A divider page is inserted before each topic section.

    Returns the output path, or None if there are no slides at all.
    """
    # Build the ordered list of pages (dividers + slides) without loading
    # all images at once to avoid high memory usage on large runs.
    page_sources: list[Path | str] = []  # Path for slides, str (topic) for dividers

    for topic in sorted(topic_slides.keys()):
        slides = topic_slides[topic]
        if not slides:
            continue
        page_sources.append(topic)  # divider marker
        page_sources.extend(slides)

    if not page_sources:
        print("[PDF] No slides found — skipping all_posts.pdf")
        return None

    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PDFS_DIR / "all_posts.pdf"

    def _load_page(source):
        if isinstance(source, str):
            return _create_divider_page(source)
        return _load_slide(source)

    first_page = _load_page(page_sources[0])
    append_imgs = [_load_page(src) for src in page_sources[1:]]

    first_page.save(
        str(out_path),
        "PDF",
        resolution=100.0,
        save_all=True,
        append_images=append_imgs,
    )

    # Cleanup
    first_page.close()
    for img in append_imgs:
        img.close()

    print(f"[PDF] Created {out_path.name}  ({len(page_sources)} pages total)")
    return out_path


def generate_all_pdfs():
    """
    Main entry point: collect slides, generate per-topic PDFs and
    the combined all_posts PDF.
    """
    topic_slides = _collect_slides_by_topic()

    if not topic_slides:
        print("[PDF] No slide images found in Posts/images/ — nothing to do.")
        return

    print(f"[PDF] Found {len(topic_slides)} topic(s): {', '.join(sorted(topic_slides.keys()))}")

    # Per-topic PDFs
    for topic in sorted(topic_slides.keys()):
        generate_topic_pdf(topic, topic_slides[topic])

    # Combined PDF
    generate_all_posts_pdf(topic_slides)

    print(f"\n[PDF] All PDFs saved to {PDFS_DIR}/")


if __name__ == "__main__":
    generate_all_pdfs()
