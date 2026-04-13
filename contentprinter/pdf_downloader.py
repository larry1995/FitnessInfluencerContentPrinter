"""Library surface for OA source-PDF downloads.

Wraps `src/pdf_downloader.py` into a batch primitive that takes a list of
reference dicts (matching the shape in `audits/training_pdf_urls.json`) and
returns the list of successfully-downloaded file paths.
"""

from __future__ import annotations

from pathlib import Path

import pdf_downloader as _pdfd
from http_utils import create_session


def download_references(
    refs: list[dict],
    out_dir: Path | str,
    *,
    delay: float = _pdfd.DEFAULT_DELAY,
    force: bool = False,
) -> list[Path]:
    """Download the `status == "ok"` entries from a reference list.

    Args:
        refs: List of reference dicts. Each must have `ref_idx` (int) and
            `status` ("ok" / "unresolved" / "pmid_only" / "no_doi"). Entries
            where status == "ok" additionally need `pdf_url` and ideally
            `citation`. Anything other than `status=="ok"` is skipped
            silently, same as the CLI. Shape matches the researcher's
            JSON format (see `audits/training_pdf_urls.json`,
            `config/upcoming_pdf_urls.json`).
        out_dir: Destination directory. Will be created if missing. Each
            successful download writes `refNN.pdf` (zero-padded ref_idx)
            into this directory alongside a `download_log.json` with
            per-reference outcome metadata.
        delay: Seconds between HTTP requests (polite-scrape default 1.0).
        force: If True, re-download even if a previously-valid PDF exists
            and re-attempt previously-failed URLs.

    Returns:
        A list of absolute Paths to successfully-downloaded PDFs. Order
        matches the input `refs` order. Skipped / failed entries are not
        in the returned list (but ARE recorded in `download_log.json`).

    Safety: every download is validated against the `%PDF` magic bytes
    before being written, so HTML fallback pages never land on disk.
    All HTTP goes through `http_utils.create_session` (timeout + retry)
    with the identified `CentralStrengthKB-Research/1.0` User-Agent.

    Stability: signature is frozen. The reference dict shape is the
    researcher's canonical format and is tracked in `API_SURFACE.md`.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = create_session()
    session.headers["User-Agent"] = _pdfd.PDF_DOWNLOADER_UA

    log_path = out_dir / "download_log.json"
    log = _pdfd._load_existing_log(log_path)
    log["topic_slug"] = out_dir.name
    entries = log["entries"]

    downloaded: list[Path] = []
    for ref in refs:
        _pdfd._process_reference(
            session, out_dir.name, ref, out_dir, entries,
            dry_run=False, force=force, delay=delay,
        )
        ref_idx = ref.get("ref_idx")
        key = f"ref{ref_idx:02d}" if isinstance(ref_idx, int) else f"ref_{ref_idx}"
        entry = entries.get(key, {})
        if entry.get("status") == "ok":
            pdf_path = out_dir / f"{key}.pdf"
            if pdf_path.exists():
                downloaded.append(pdf_path.resolve())

    _pdfd._write_log(log_path, log)
    return downloaded
