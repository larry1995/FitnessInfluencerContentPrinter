"""
Stamp citation-audit results into Posts/<slug>/meta.json (Task #29).

Reads `audits/citation_integrity_2026-04-12.json` (or any audit JSON with
the same row schema), groups rows by slug, computes a per-slug
publication-readiness status, and writes the result into each topic's
`meta.json` file via `posts_layout.merge_meta` so unrelated meta fields
(tags, references, source_name, etc.) are preserved.

Output schema added to each meta.json:

    audit_status:        "OK" | "WARN" | "BLOCKED"
    audit_date:          ISO date of the audit run
    publication_allowed: bool — convenience: (audit_status != "BLOCKED")
    audit_issues:        list of {ref_idx, severity, raw, notes} dicts,
                         non-OK rows only

Status precedence (priority-based):
    any issue.severity in BLOCKING_SEVERITIES → "BLOCKED"
    else any issue.severity in SOFT_FLAG_SEVERITIES → "WARN"
    else (all OK, or no REFERENCES block) → "OK"

DO NOT change this precedence to "majority wins" or "first-issue wins" —
a single hard severity must dominate even if there are 10 OK refs.
Allowing a remediation pass to leave one blocking severity in place and
expect WARN behavior would re-introduce the publication-leak failure
mode that #21/#27/#29 exist to prevent.

The writer is idempotent. Re-running on a meta.json that already has
matching audit_date + identical audit_issues + identical audit_status is
a no-op (no file write, no mtime touch). This makes
`python src/audit_meta_writer.py --all` safe to schedule from CI.

Run:
    python src/audit_meta_writer.py                              # all topics
    python src/audit_meta_writer.py --slug nutrition_vegan_creatine
    python src/audit_meta_writer.py --dry-run                    # diff only
    python src/audit_meta_writer.py --audit audits/other_audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from posts_layout import merge_meta

# Imported lazily so the script doesn't pull the whole contentprinter package
# import chain into a side-effect-free CLI tool. The audit module lives in
# audits/ at the repo root; we add it to sys.path here.
PROJECT_ROOT = Path(__file__).parent.parent
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize
AUDIT_DIR = PROJECT_ROOT / "audits"
DEFAULT_AUDIT_JSON = AUDIT_DIR / "citation_integrity_2026-04-12.json"

if str(AUDIT_DIR) not in sys.path:
    sys.path.insert(0, str(AUDIT_DIR))

# Pull severity classification from contentprinter.verify (which itself wraps
# audits/_citation_audit.py). This is the single authoritative source for
# what counts as blocking vs soft — keep it in sync via import, not by
# duplicating the constant.
_CP_DIR = PROJECT_ROOT / "contentprinter"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from contentprinter.verify import BLOCKING_SEVERITIES, SOFT_FLAG_SEVERITIES  # noqa: E402


# ── Status derivation ──────────────────────────────────────────────────────


def derive_status(issues: list[dict]) -> str:
    """Compute audit_status from a list of CitationIssue rows for one post.

    Priority-based:
        any blocking severity → "BLOCKED"
        else any soft flag → "WARN"
        else (all OK or empty) → "OK"

    DO NOT change this to majority-wins or first-issue-wins — a single
    hard severity MUST dominate even if there are 10 OK refs.
    """
    has_blocking = False
    has_soft = False
    for issue in issues:
        sev = issue.get("severity", "")
        if sev in BLOCKING_SEVERITIES:
            has_blocking = True
            break  # short-circuit: blocking dominates
        if sev in SOFT_FLAG_SEVERITIES:
            has_soft = True
    if has_blocking:
        return "BLOCKED"
    if has_soft:
        return "WARN"
    return "OK"


_FETCH_ERROR_MAX_CHARS = 120


def trim_issue_for_meta(row: dict) -> dict:
    """Project the full audit row down to the fields meta.json carries.

    The full audit row has verbose `verify`, `fetched`, and `draft` sub-dicts
    that are useful for diagnostics but bloat meta.json. The meta.json copy
    keeps only what the iOS UI and `grep -r DOI_FABRICATED Posts/*/meta.json`
    workflows actually need.

    Includes `fetch_error` (truncated to 120 chars) when the row carries one
    — primarily for `VERIFICATION_UNAVAILABLE` rows where the iOS UI wants
    to surface "network was down during this audit" messaging without
    re-running the audit. Truncated to keep meta.json compact.
    """
    trimmed = {
        "ref_idx": row.get("ref_idx"),
        "severity": row.get("severity", ""),
        "raw": row.get("raw", ""),
        "notes": row.get("notes"),
    }
    fetch_error = row.get("fetch_error")
    if fetch_error:
        trimmed["fetch_error"] = str(fetch_error)[:_FETCH_ERROR_MAX_CHARS]
    return trimmed


# ── Per-slug processing ────────────────────────────────────────────────────


def group_rows_by_slug(audit_data: dict) -> dict[str, list[dict]]:
    """Index the flat audit row list by topic slug."""
    rows = audit_data.get("rows", [])
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        slug = row.get("slug")
        if slug:
            grouped[slug].append(row)
    return dict(grouped)


def build_audit_fields(slug_rows: list[dict], audit_date: str) -> dict:
    """Build the four-field audit dict for a single post.

    `audit_issues` is sorted by `ref_idx` to make `_audit_fields_match`
    order-insensitive (#40). The current audit module happens to emit rows
    in `ref_idx` order so the sort is a no-op today, but if researcher ever
    re-sorts (e.g. by severity-first for diagnostic display), the
    idempotency check would otherwise produce spurious re-writes until the
    lists agree on order. Explicit sort here pins the invariant.
    """
    issues = [trim_issue_for_meta(r) for r in slug_rows if r.get("severity") != "OK"]
    issues.sort(key=lambda r: (r.get("ref_idx") or 0))
    status = derive_status(slug_rows)
    return {
        "audit_status": status,
        "audit_date": audit_date,
        "publication_allowed": status != "BLOCKED",
        "audit_issues": issues,
    }


def _audit_fields_match(existing: dict, new_fields: dict) -> bool:
    """Idempotency check: True iff the existing meta already has these
    audit fields exactly. Skip the write if so.

    Comparison is on `audit_date`, `audit_status`, `publication_allowed`,
    and the issues list (compared as a list, order matters because the
    writer always emits in ref_idx order). Other meta.json fields are
    irrelevant to the comparison.
    """
    for key in ("audit_status", "audit_date", "publication_allowed"):
        if existing.get(key) != new_fields.get(key):
            return False
    if existing.get("audit_issues") != new_fields.get("audit_issues"):
        return False
    return True


def process_slug(
    slug: str,
    slug_rows: list[dict],
    audit_date: str,
    *,
    dry_run: bool = False,
) -> str:
    """Stamp one topic's meta.json with audit fields. Returns a status string."""
    topic_dir = POSTS_DIR / slug
    meta_path = topic_dir / "meta.json"

    if not topic_dir.is_dir():
        return f"missing-topic-dir ({topic_dir.relative_to(POSTS_DIR)})"

    new_fields = build_audit_fields(slug_rows, audit_date)
    n_blocking = sum(1 for r in slug_rows if r.get("severity") in BLOCKING_SEVERITIES)
    n_soft = sum(1 for r in slug_rows if r.get("severity") in SOFT_FLAG_SEVERITIES)
    n_ok = sum(1 for r in slug_rows if r.get("severity") == "OK")

    existing: dict = {}
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    if _audit_fields_match(existing, new_fields):
        return (
            f"[{new_fields['audit_status']}] {slug}: "
            f"{n_blocking} hard + {n_soft} soft + {n_ok} ok (already up-to-date)"
        )

    merged = merge_meta(existing, new_fields)

    if dry_run:
        return (
            f"[{new_fields['audit_status']}] {slug}: "
            f"{n_blocking} hard + {n_soft} soft + {n_ok} ok (would-write)"
        )

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return (
        f"[{new_fields['audit_status']}] {slug}: "
        f"{n_blocking} hard + {n_soft} soft + {n_ok} ok"
    )


# ── Single-post re-audit (#39) ────────────────────────────────────────────


def refresh_audit_meta(slug: str, *, dry_run: bool = False) -> str:
    """Re-audit a single post's draft.txt and re-stamp its meta.json.

    **This is the ONLY sanctioned way to update audit fields after a
    remediation edit to draft.txt.** The remediation workflow (#31) MUST
    call `refresh_audit_meta(slug)` immediately after editing
    `Posts/<slug>/en/draft.txt`. Do NOT manually patch `audit_issues`
    indices or any other audit field — manual patches drift from the
    actual draft state and re-introduce the trust-the-edit-instead-of-the
    -source failure pattern that #21/#27/#29 exist to prevent.

    Pipeline:
        1. Read `Posts/<slug>/en/draft.txt`
        2. Call `contentprinter.verify_citations(text, slug=slug)` for fresh rows
        3. Build audit fields with today's date via `build_audit_fields`
        4. Merge into existing meta.json via `posts_layout.merge_meta`
        5. Write back (or skip if idempotent re-call produces no change)

    **Network behavior:** this function makes outbound HTTPS calls to
    Crossref and PubMed via `verify_citations`. Each REFERENCES entry
    triggers 1-3 lookups (~1-2 sec per citation). A 5-citation post
    refresh takes ~10 seconds. Run as a background operation, not in a
    request handler.

    **CSKB reuse:** the CSKB job runner's `verifying` lifecycle step
    (Objective F-0) calls this exact helper for per-job verification.
    Same code path, both environments. The audit logic is centralized;
    consumers don't re-implement verification per-environment.

    Args:
        slug: Topic slug. Must correspond to an existing
            `Posts/<slug>/en/draft.txt` file.
        dry_run: If True, build the new fields but do not write to disk.
            Returns a status string describing what would happen.

    Returns:
        A status string of the form
        `[STATUS] slug: N hard + M soft + K ok` (or
        `... (already up-to-date)` if idempotent, or an error message
        on missing slug / missing draft / verify failure).

    Raises:
        Nothing — all errors are caught and surfaced via the return string.
        Network failures during `verify_citations` come back as
        `VERIFICATION_UNAVAILABLE` rows (see API_SURFACE.md §10.4) and
        are stamped into meta.json's `audit_issues` for human triage.
    """
    topic_dir = POSTS_DIR / slug
    draft_path = topic_dir / "en" / "draft.txt"

    if not topic_dir.is_dir():
        return f"missing-topic-dir ({slug})"
    if not draft_path.exists():
        return f"missing-draft ({slug}/en/draft.txt)"

    # Lazy import: contentprinter has its own sys.path shim. Importing it at
    # module load time would force the whole library package into memory for
    # the simple `python src/audit_meta_writer.py` CLI use case (which only
    # needs the static-JSON stamping path). Defer to call time so the CLI
    # stays lightweight when refresh_audit_meta is not invoked.
    from contentprinter.verify import verify_citations

    try:
        rows = verify_citations(draft_path, slug=slug)
    except Exception as e:
        return f"verify-failed ({slug}): {str(e)[:120]}"

    audit_date = datetime.now().date().isoformat()
    new_fields = build_audit_fields(rows, audit_date)
    n_blocking = sum(1 for r in rows if r.get("severity") in BLOCKING_SEVERITIES)
    n_soft = sum(1 for r in rows if r.get("severity") in SOFT_FLAG_SEVERITIES)
    n_ok = sum(1 for r in rows if r.get("severity") == "OK")

    meta_path = topic_dir / "meta.json"
    existing: dict = {}
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    if _audit_fields_match(existing, new_fields):
        return (
            f"[{new_fields['audit_status']}] {slug}: "
            f"{n_blocking} hard + {n_soft} soft + {n_ok} ok (already up-to-date)"
        )

    if dry_run:
        return (
            f"[{new_fields['audit_status']}] {slug}: "
            f"{n_blocking} hard + {n_soft} soft + {n_ok} ok (would-refresh)"
        )

    merged = merge_meta(existing, new_fields)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return (
        f"[{new_fields['audit_status']}] {slug}: "
        f"{n_blocking} hard + {n_soft} soft + {n_ok} ok (refreshed)"
    )


# ── Top-level run ──────────────────────────────────────────────────────────


def stamp_audit(
    *,
    audit_path: Path = DEFAULT_AUDIT_JSON,
    only: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Stamp the audit JSON into all topic meta.json files (or a single one).

    Returns a summary dict with counts: blocked, warn, ok, missing, no_op.
    """
    if not audit_path.exists():
        raise FileNotFoundError(f"audit JSON not found: {audit_path}")

    audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_date = audit_data.get("generated_at", datetime.now().date().isoformat())
    grouped = group_rows_by_slug(audit_data)

    print(f"\n{'='*60}")
    print(f"  AUDIT META WRITER {'(DRY RUN)' if dry_run else ''}")
    print(f"  Source: {audit_path.relative_to(PROJECT_ROOT)}")
    print(f"  Audit date: {audit_date}")
    print(f"  Topics in audit: {len(grouped)}")
    print(f"{'='*60}\n")

    summary = {"BLOCKED": 0, "WARN": 0, "OK": 0, "missing": 0, "no_op": 0}

    target_slugs = [only] if only else sorted(grouped.keys())
    if only and only not in grouped:
        print(f"[ERROR] slug {only!r} not in audit data")
        return summary

    for slug in target_slugs:
        rows = grouped.get(slug, [])
        if not rows:
            print(f"[SKIP] {slug}: no rows in audit JSON")
            summary["missing"] += 1
            continue
        msg = process_slug(slug, rows, audit_date, dry_run=dry_run)
        print(f"  {msg}")
        if "already up-to-date" in msg:
            summary["no_op"] += 1
            # Also count by status for the summary tally
            for status in ("BLOCKED", "WARN", "OK"):
                if msg.startswith(f"[{status}]"):
                    summary[status] += 1
                    break
        elif msg.startswith("missing-topic-dir"):
            summary["missing"] += 1
        else:
            for status in ("BLOCKED", "WARN", "OK"):
                if msg.startswith(f"[{status}]"):
                    summary[status] += 1
                    break

    print(f"\n{'='*60}")
    print(
        f"  Totals: BLOCKED={summary['BLOCKED']} "
        f"WARN={summary['WARN']} OK={summary['OK']} "
        f"missing={summary['missing']} no-op={summary['no_op']}"
    )
    print(f"{'='*60}\n")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Stamp citation-audit results into Posts/<slug>/meta.json"
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=DEFAULT_AUDIT_JSON,
        help=f"Audit JSON path (default: {DEFAULT_AUDIT_JSON.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument("--slug", default=None, help="Stamp only this topic slug")
    parser.add_argument(
        "--refresh",
        metavar="SLUG",
        default=None,
        help="Re-audit the named slug's draft.txt via verify_citations and re-stamp "
             "its meta.json. Use this immediately after a remediation edit to "
             "draft.txt — it is the only sanctioned way to update audit fields "
             "post-remediation. Makes outbound HTTPS calls; ~1-2 sec per citation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without modifying any files",
    )
    args = parser.parse_args()

    if args.refresh:
        msg = refresh_audit_meta(args.refresh, dry_run=args.dry_run)
        print(msg)
        # Exit non-zero on error so remediation tooling can branch on it
        is_error = (
            msg.startswith("missing-")
            or msg.startswith("verify-failed")
        )
        sys.exit(1 if is_error else 0)

    summary = stamp_audit(audit_path=args.audit, only=args.slug, dry_run=args.dry_run)
    sys.exit(0 if summary.get("missing", 0) == 0 else 1)


if __name__ == "__main__":
    main()
