"""
Open-access PDF downloader for training-method posts.

Reads `Posts/training_pdf_urls.json` (produced by the researcher's half of
Task #3) and downloads every reference with `status == "ok"` into the
per-topic `Posts/<slug>/pdfs/refN.pdf`. Each download is validated against
the `%PDF` magic bytes — some repository URLs return HTML fallback pages,
and we never want those on disk masquerading as PDFs.

Per-topic outcomes are written to `Posts/<slug>/pdfs/download_log.json` so
a re-run can skip already-verified downloads (idempotent).

Usage:
    python src/pdf_downloader.py                   # download all topics
    python src/pdf_downloader.py --topic training_warmups
    python src/pdf_downloader.py --dry-run         # list what would be fetched
    python src/pdf_downloader.py --force           # re-download existing files

Conventions honored:
- All HTTP goes through `http_utils.create_session` (timeout + retry).
- Never touches entries with `status != "ok"` — those are unresolved /
  pmid-only / no-doi and are left for the researcher or a human follow-up.
- No absolute paths — `PROJECT_ROOT` constant is the only anchor.
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from http_utils import create_session, get as http_get

PROJECT_ROOT = Path(__file__).parent.parent
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize
URLS_JSON = PROJECT_ROOT / "audits" / "training_pdf_urls.json"

PDF_MAGIC = b"%PDF"
DEFAULT_DELAY = 1.0
MAX_PDF_BYTES = 40 * 1024 * 1024  # 40 MB sanity cap

# Sticky-failure auto-retry horizon. Failures older than this are re-attempted
# automatically — gives publishers a chance to fix transient bot-protection
# issues or temporary DNS flakes without forcing `--force` (which re-downloads
# the successful entries too, wasting bandwidth).
DEFAULT_RETRY_AFTER_HOURS = 168  # 1 week

PDF_DOWNLOADER_UA = (
    "CentralStrengthKB-Research/1.0 "
    "(+https://centralstrengthgyms.com/research; contentprinter@centralstrengthgyms.com)"
)

# Narrow per-host override: europepmc.org's upstream service closes the TCP
# connection on identified research UAs (confirmed by researcher during #17
# retry work — not a ToS violation, it's a misconfig on their edge). We send
# a real browser UA for europepmc.org ONLY; every other host still sees the
# identified UA above. Do NOT generalize this override — treat it as a
# one-host workaround, not a spoofing policy.
_EUROPEPMC_HOST = "europepmc.org"
_EUROPEPMC_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_PMC_DIRECT_PDF_RE = re.compile(
    r"^https?://(?:www\.)?(?:pmc\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov)"
    r"/(?:articles|pmc/articles)/(PMC\d+)/pdf/?",
    re.IGNORECASE,
)


def _rewrite_pmc_to_europepmc(url: str) -> str:
    """Rewrite NCBI PMC direct-PDF URLs to the europepmc.org equivalent.

    NCBI's `pmc.ncbi.nlm.nih.gov/.../pdf/` endpoints are now fronted by a
    JavaScript proof-of-work challenge (the `cloudpmc-viewer-pow` cookie
    interstitial), which no `requests`-based client can pass. Europe PMC
    hosts the same OA content at `europepmc.org/articles/<PMCID>?pdf=render`
    and responds with the raw PDF bytes.

    `ptpmcrender.fcgi` is dead from this IP — only the `?pdf=render` query
    form works. This rewrite is applied transparently at fetch time; callers
    never need to know.
    """
    m = _PMC_DIRECT_PDF_RE.match(url or "")
    if not m:
        return url
    pmcid = m.group(1)
    return f"https://europepmc.org/articles/{pmcid}?pdf=render"


def load_url_manifest(path: Path | None = None) -> dict:
    """Load a URL manifest from `path` or the default `training_pdf_urls.json`.

    Researcher's retry JSONs (e.g. `training_pdf_urls_retry.json`) share the
    same schema and can be passed in directly by the CLI's `--manifest` flag.
    """
    manifest_path = path or URLS_JSON
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"{manifest_path} not found — researcher half of Task #3 has not been run yet."
        )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _load_existing_log(log_path: Path) -> dict:
    if not log_path.exists():
        return {"topic_slug": "", "entries": {}, "last_run_at": None}
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
        if "entries" not in data:
            data["entries"] = {}
        return data
    except (json.JSONDecodeError, OSError):
        return {"topic_slug": "", "entries": {}, "last_run_at": None}


def _write_log(log_path: Path, data: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _relpath(path: Path) -> str:
    """Render a path relative to POSTS_DIR when possible, else as-is."""
    try:
        return str(path.relative_to(POSTS_DIR))
    except ValueError:
        return str(path)


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _fetch_pdf(session, url: str) -> tuple[bytes | None, str]:
    """Return (pdf_bytes, error_string). On success error is empty.

    Applies two host-specific workarounds transparently:
    - NCBI PMC direct-PDF URLs are rewritten to europepmc.org (which hosts
      the same OA content without a JS PoW gate).
    - For europepmc.org specifically, a browser User-Agent is sent instead
      of the identified research UA, because EPMC's upstream closes TCP on
      non-browser clients. Every other host continues to see the identified
      UA — this is not a general spoofing policy, just a narrow workaround.
    """
    fetch_url = _rewrite_pmc_to_europepmc(url)
    from urllib.parse import urlparse
    host = urlparse(fetch_url).netloc.lower()
    per_request_headers = None
    if host == _EUROPEPMC_HOST or host.endswith("." + _EUROPEPMC_HOST):
        per_request_headers = {"User-Agent": _EUROPEPMC_UA}

    try:
        resp = http_get(
            session, fetch_url,
            timeout=60, stream=True,
            headers=per_request_headers,
        )
    except Exception as e:
        return None, f"http error: {e}"

    content_type = resp.headers.get("content-type", "").lower()
    content_length = resp.headers.get("content-length")
    if content_length:
        try:
            declared = int(content_length)
        except (TypeError, ValueError):
            declared = None
        if declared is not None and declared > MAX_PDF_BYTES:
            return None, f"declared size {declared} exceeds {MAX_PDF_BYTES}"

    buf = bytearray()
    try:
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) > MAX_PDF_BYTES:
                return None, f"body exceeded {MAX_PDF_BYTES} bytes"
    except Exception as e:
        return None, f"stream error: {e}"
    finally:
        resp.close()

    if not buf:
        return None, "empty response body"
    if not bytes(buf[:4]).startswith(PDF_MAGIC):
        peek = bytes(buf[:80]).decode("utf-8", errors="replace").strip()
        return None, f"missing %PDF magic (content-type={content_type or 'unknown'}; peek={peek[:60]!r})"

    return bytes(buf), ""


def _existing_is_valid(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 4:
        return False
    with open(path, "rb") as f:
        return f.read(4).startswith(PDF_MAGIC)


def _prior_failure_is_stale(prior: dict, retry_after_hours: float) -> bool:
    """Return True iff a prior-failure log entry is older than the retry horizon.

    Reads `attempted_at` (ISO-8601, written by `_process_reference` on
    failure) and compares against `datetime.now()`. Missing or unparseable
    timestamps are treated as stale — we'd rather retry than trap forever.
    """
    ts = prior.get("attempted_at") if prior else None
    if not ts:
        return True
    try:
        when = datetime.fromisoformat(ts)
    except ValueError:
        return True
    age_hours = (datetime.now() - when).total_seconds() / 3600.0
    return age_hours >= retry_after_hours


def _process_reference(session, slug: str, ref: dict, pdfs_dir: Path,
                       log_entries: dict, dry_run: bool, force: bool,
                       delay: float,
                       retry_after_hours: float = DEFAULT_RETRY_AFTER_HOURS) -> str:
    ref_idx = ref.get("ref_idx")
    url = ref.get("pdf_url")
    citation = ref.get("citation", "")[:80]
    key = f"ref{ref_idx:02d}" if isinstance(ref_idx, int) else f"ref_{ref_idx}"
    dst = pdfs_dir / f"{key}.pdf"

    if ref.get("status") != "ok":
        log_entries[key] = {
            "status": "skipped",
            "reason": f"researcher status={ref.get('status')!r}",
            "citation": citation,
            "url": url,
        }
        return f"{key}: skip (status={ref.get('status')})"

    if not url:
        log_entries[key] = {
            "status": "skipped",
            "reason": "no pdf_url despite status=ok",
            "citation": citation,
        }
        return f"{key}: skip (no url)"

    if not force and _existing_is_valid(dst):
        log_entries[key] = {
            "status": "ok",
            "path": _relpath(dst),
            "sha256_16": _sha256_of(dst),
            "bytes": dst.stat().st_size,
            "citation": citation,
            "url": url,
            "reused_existing": True,
            "verified_at": datetime.now().isoformat(timespec="seconds"),
        }
        return f"{key}: already-downloaded ({dst.stat().st_size} bytes)"

    if not force:
        prior = log_entries.get(key)
        if prior and prior.get("status") == "failed" and prior.get("url") == url:
            if not _prior_failure_is_stale(prior, retry_after_hours):
                return f"{key}: prior-failure ({prior.get('reason', '')[:60]}) — use --force to retry"
            # Fall through: prior failure is old enough to auto-retry.
            print(f"  [STALE] {key}: prior failure older than {retry_after_hours}h — auto-retrying")

    if dry_run:
        log_entries[key] = {"status": "planned", "url": url, "citation": citation}
        return f"{key}: would-fetch {url[:70]}"

    time.sleep(delay)
    pdf_bytes, err = _fetch_pdf(session, url)
    if pdf_bytes is None:
        log_entries[key] = {
            "status": "failed",
            "reason": err,
            "citation": citation,
            "url": url,
            "attempted_at": datetime.now().isoformat(timespec="seconds"),
        }
        return f"{key}: FAIL — {err}"

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(pdf_bytes)
    log_entries[key] = {
        "status": "ok",
        "path": _relpath(dst),
        "sha256_16": hashlib.sha256(pdf_bytes).hexdigest()[:16],
        "bytes": len(pdf_bytes),
        "citation": citation,
        "url": url,
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    return f"{key}: ok ({len(pdf_bytes)} bytes)"


def download_topic(session, slug: str, refs: list, dry_run: bool, force: bool,
                   delay: float,
                   retry_after_hours: float = DEFAULT_RETRY_AFTER_HOURS) -> dict:
    topic_dir = POSTS_DIR / slug
    pdfs_dir = topic_dir / "pdfs"
    pdfs_dir.mkdir(parents=True, exist_ok=True)

    log_path = pdfs_dir / "download_log.json"
    log = _load_existing_log(log_path)
    log["topic_slug"] = slug
    log["last_run_at"] = datetime.now().isoformat(timespec="seconds")
    entries = log["entries"]

    print(f"\n[TOPIC] {slug} ({len(refs)} refs)")

    summary = {"ok": 0, "planned": 0, "skipped": 0, "failed": 0}
    for ref in refs:
        ref_idx = ref.get("ref_idx")
        key = f"ref{ref_idx:02d}" if isinstance(ref_idx, int) else f"ref_{ref_idx}"
        status_line = _process_reference(
            session, slug, ref, pdfs_dir, entries,
            dry_run=dry_run, force=force, delay=delay,
            retry_after_hours=retry_after_hours,
        )
        print(f"  {status_line}")
        final_status = entries.get(key, {}).get("status", "skipped")
        if final_status == "ok":
            summary["ok"] += 1
        elif final_status == "failed":
            summary["failed"] += 1
        elif final_status == "planned":
            summary["planned"] += 1
        else:
            summary["skipped"] += 1

    log["summary"] = summary
    if not dry_run:
        _write_log(log_path, log)
    return summary


def download_all(only: str | None = None, dry_run: bool = False,
                 force: bool = False, delay: float = DEFAULT_DELAY,
                 manifest_path: Path | None = None,
                 retry_after_hours: float = DEFAULT_RETRY_AFTER_HOURS) -> dict:
    manifest = load_url_manifest(manifest_path)

    session = create_session()
    session.headers["User-Agent"] = PDF_DOWNLOADER_UA

    slugs = [k for k in manifest.keys() if k != "_meta"]
    if only:
        if only not in slugs:
            print(f"[ERROR] topic {only!r} not in manifest. Available: {slugs}")
            return {}
        slugs = [only]

    meta = manifest.get("_meta", {})
    print(f"\n{'='*60}")
    print(f"  PDF DOWNLOADER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Manifest: {meta.get('total_references', '?')} refs across {len(slugs)} topics")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}{' (force)' if force else ''}")
    print(f"{'='*60}")

    totals = {"ok": 0, "planned": 0, "skipped": 0, "failed": 0}
    for slug in slugs:
        refs = manifest[slug]
        s = download_topic(
            session, slug, refs,
            dry_run=dry_run, force=force, delay=delay,
            retry_after_hours=retry_after_hours,
        )
        for k in totals:
            totals[k] += s.get(k, 0)

    print(f"\n{'='*60}")
    print(f"  Totals: ok={totals['ok']} planned={totals['planned']} "
          f"skipped={totals['skipped']} failed={totals['failed']}")
    print(f"{'='*60}\n")
    return totals


def main():
    parser = argparse.ArgumentParser(description="Download OA PDFs for training-method posts")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="Path to a URL manifest JSON (default: Posts/training_pdf_urls.json). "
                             "Pass Posts/training_pdf_urls_retry.json for the researcher retry pass.")
    parser.add_argument("--topic", default=None, help="Single topic slug to process")
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no network writes")
    parser.add_argument("--force", action="store_true", help="Re-download even if a valid PDF exists")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between HTTP requests")
    parser.add_argument("--retry-after-hours", type=float, default=DEFAULT_RETRY_AFTER_HOURS,
                        help="Auto-retry failures older than this many hours "
                             f"(default: {DEFAULT_RETRY_AFTER_HOURS}, i.e. 1 week). "
                             "Set to 0 to retry every failure; set very high to match old strict behavior.")
    args = parser.parse_args()
    totals = download_all(
        only=args.topic, dry_run=args.dry_run, force=args.force,
        delay=args.delay, manifest_path=args.manifest,
        retry_after_hours=args.retry_after_hours,
    )
    sys.exit(0 if totals.get("failed", 0) == 0 else 1)


if __name__ == "__main__":
    main()
