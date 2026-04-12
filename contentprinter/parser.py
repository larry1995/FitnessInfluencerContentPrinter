"""Library surface for draft-text parsing.

Wraps `src/single_page_generator.py:parse_detailed_content` with a
string-in/dict-out signature so FastAPI handlers can go draft-text →
render-time post dict without touching disk. This is the missing piece
that completes the documented § 4 consumer flow:

    scraped article → generate_draft → draft text → parse_draft_text → render_page

The underlying `parse_detailed_content` expects a Path because it stamps
`post["filename"]` on the result; this wrapper honors that contract by
writing the text to a NamedTemporaryFile, parsing, then cleaning up.
The tempfile is invisible to callers.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import single_page_generator as _spg


def parse_draft_text(text: str, *, filename_hint: str = "draft.txt") -> dict[str, Any]:
    """Parse the contents of a polished draft.txt into a render-ready post dict.

    Args:
        text: The full draft.txt contents (`CAPTION:` block + body + `REFERENCES:` block).
            Must be a non-empty string.
        filename_hint: Purely cosmetic. Stamped onto `post["filename"]` for
            logging/debugging. Defaults to `"draft.txt"`. Does not affect
            parsing behavior.

    Returns:
        A render-time `post` dict with the schema documented in API_SURFACE.md § 4.
        Safe to pass directly to `contentprinter.render_page`.

    Raises:
        ValueError: if `text` is empty or not a string.
        OSError: if the backing tempfile cannot be created (rare; surfaces
            disk-full or permission issues at system boundaries).

    No network calls. Writes exactly one tempfile which is deleted before
    returning. Safe to call concurrently.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("parse_draft_text requires a non-empty string")

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix="_" + filename_hint,
        delete=False,
    )
    try:
        tmp.write(text)
        tmp.close()
        return _spg.parse_detailed_content(Path(tmp.name))
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass
