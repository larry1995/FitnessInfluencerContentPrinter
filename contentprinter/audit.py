"""Library surface for audit-state refresh.

Wraps `src/audit_meta_writer.py::refresh_audit_meta` as a stable
public function. The CSKB iOS app's FastAPI job runner calls this in
its `verifying` lifecycle step — same code path as the ContentPrinter
remediation workflow, no per-environment re-implementation.

Why this function lives in the public surface even though it has
filesystem side effects (most other public functions are pure):
`refresh_audit_meta` is the load-bearing bridge between draft edits
and the F-0 publication gate's view of audit state. Manual patches
to `meta.json::audit_issues` re-introduce the trust-the-edit-instead-
of-the-source failure pattern. Exposing this as a public function
makes the sanctioned path obvious from the import line — anyone
reaching into `src/*` to update audit fields by hand is a contract
violation that's grep-able from a CSKB code review.

The wrapper is intentionally thin — `src/audit_meta_writer.py` carries
the implementation, this module just adds the type signature and the
docstring obligations to the stability promise. When Task #33 lands
(next sprint), the bare `import audit_meta_writer as _amw` below
becomes `from contentprinter._internal import audit_meta_writer as _amw`
and this wrapper file stays at the same public path, signature
unchanged.
"""

from __future__ import annotations

import audit_meta_writer as _amw


def refresh_audit_meta(slug: str, *, dry_run: bool = False) -> str:
    """Re-audit a single post's draft.txt and re-stamp its meta.json.

    Args:
        slug: Topic slug (the per-post directory name under `Posts/`).
            The function reads `Posts/<slug>/en/draft.txt` and writes
            `Posts/<slug>/meta.json`.
        dry_run: If True, run the verification but do not write meta.json.
            Returns a status string describing what WOULD have been written.

    Returns:
        A status string describing the outcome — one of:
        - `"refreshed: <slug> -> <status>"` (e.g. `"refreshed: foo -> OK"`)
        - `"unchanged: <slug>"` (idempotent re-call, no write)
        - `"missing-draft: <slug>"` (no draft.txt on disk)
        - `"dry-run: <slug> -> <would-be-status>"`

    Raises:
        `ValueError` if `slug` is not a non-empty string.
        `FileNotFoundError` if the topic directory itself doesn't exist.

    Side effects:
        - Reads `Posts/<slug>/en/draft.txt`
        - Outbound HTTPS to Crossref + PubMed via `verify_citations`
          (1-2 seconds per REFERENCES entry; ~10 sec for a 5-ref post)
        - Writes `Posts/<slug>/meta.json` (unless `dry_run=True` or
          the merged content is byte-equal to what's already on disk)

    **Network behavior**: this function makes synchronous outbound HTTPS
    calls and is **not safe to call from a FastAPI request handler** —
    it will block the event loop for up to ~10 seconds. CSKB's job
    runner is async by design (POST /v1/generate returns 202 with a
    job_id) and calls this from the background `verifying` lifecycle
    step, which fits the budget.

    **DO NOT manually patch `audit_issues` indices or any other audit
    field after a draft edit.** Always call `refresh_audit_meta(slug)`
    immediately after editing `Posts/<slug>/en/draft.txt`. Manual
    patches drift from the actual draft state and re-introduce the
    trust-the-edit-instead-of-the-source failure pattern that the F-0
    gate exists to prevent.

    Stability: signature and return-type frozen at 0.3.1. The set of
    return-status strings is part of the contract — new strings may be
    added without a version bump but existing strings will not be
    renamed. The `dry_run` keyword default (`False`) will not change.
    """
    if not isinstance(slug, str) or not slug:
        raise ValueError("slug must be a non-empty string")
    return _amw.refresh_audit_meta(slug, dry_run=dry_run)
