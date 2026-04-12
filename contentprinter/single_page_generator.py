"""Library surface for single-page PNG rendering.

Wraps `src/single_page_generator.py`'s two-step render+save flow into one
function call that returns a `Path` to the written PNG.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

import single_page_generator as _spg


def render_page(
    post: dict[str, Any],
    output_path: Path | str | None = None,
) -> Path:
    """Render a parsed-post dict to a single-page PNG.

    Args:
        post: The post dict produced by `parse_detailed_content()` on a
            `draft.txt` file. For programmatic construction, the required
            fields are: `title`, `intro_text`, `sections` OR
            `numbered_points`, `references`, `layout`, `evidence_info`
            (can be `{}` for community sources). See `_discover_topic_drafts`
            in the underlying module for the full schema.
        output_path: Where to write the PNG. If None, writes to a temp file
            and returns that path — the caller is responsible for deletion.

    Returns:
        The absolute path to the written PNG.

    Side effects: writes one PNG file. No network calls. Safe to call
    concurrently provided each call passes a distinct `output_path`.

    Stability: signature is frozen. The `post` dict schema may gain fields;
    the required fields listed above will not change.
    """
    if not isinstance(post, dict) or not post.get("title"):
        raise ValueError("post must be a dict with a non-empty 'title'")

    tmp_img = Image.new("RGB", (_spg.PAGE_WIDTH, 100))
    tmp_draw = ImageDraw.Draw(tmp_img)
    try:
        page_height = _spg.calculate_page_height(post, tmp_draw)
    finally:
        tmp_img.close()

    img = _spg.render_single_page(post, page_height)

    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(
            prefix="contentprinter_", suffix=".png", delete=False
        )
        tmp.close()
        dst = Path(tmp.name)
    else:
        dst = Path(output_path)
        dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        img.save(dst, "PNG", optimize=True)
    finally:
        img.close()

    return dst.resolve()
