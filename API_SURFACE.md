# ContentPrinter — Public API Surface

**Version:** 0.4.0
**Status:** Stable — see § Stability Promise below.
**Consumers:** CentralStrengthKB iOS app (via its FastAPI backend), any future integrations.

---

## 1. Scope

This document describes the **supported import path** for consuming ContentPrinter as a library. Anything documented here is covered by the stability promise. Anything in `src/*` (the internal pipeline modules) may change without notice — **do not import from `src.*` directly**.

All public functions live under the `contentprinter` package at the repository root. Typical usage:

```python
from contentprinter import (
    generate_draft,
    generate_grounded_draft,
    parse_draft_text,
    generate_chinese_from_english,
    render_page,
    download_references,
    verify_citations,
    is_blocking,
    is_llm_configured,
    refresh_audit_meta,
)
```

The package is lightweight (~400 lines of shim code). Under the hood it imports from the internal `src/` modules by prepending `src/` to `sys.path` on first import. Consumers do not need to manage `sys.path` themselves.

---

## 2. Public functions

### `generate_draft(article, *, brand=None, post_number=1) -> Post`

Generate an Instagram post draft dict from a scraped-article dict.

| Arg | Type | Description |
|---|---|---|
| `article` | `dict` | Required. Must contain `title` and `full_text`. Other recognized fields: `topic`, `source`, `url`, `summary`, `structured_content`. Same shape as scraper output under `work/raw/*.json`. |
| `brand` | `dict \| None` | Optional override. Defaults to `config/sources.json` brand block. |
| `post_number` | `int` | Sequential post number. Default `1`. |

**Returns:** `Post` dict (see § 3).

**Raises:** `ValueError` if `article` has no title.

**Side effects:** None. Pure function — no network, no file writes. Safe to call from request handlers.

---

### `generate_grounded_draft(article, *, max_retries=1, slug=None) -> str | None`

Produce a draft.txt body whose REFERENCES block is grounded in citations extracted (and verified) from the source article. This is the **publication-safe** drafter — Layer 1 of the citation-hallucination defense (see § 11).

| Arg | Type | Description |
|---|---|---|
| `article` | `dict` | Required. Must contain `title`. Recognized: `full_text`, `structured_content` (PubMed shape: `pmid`, `doi`, `authors`, `journal`, `year`), `source`, `url` / `source_url`, `topic`, `slug`, `source_type`. |
| `max_retries` | `int` | Retries after the first attempt fails Layer A (allow-list byte-check) or Layer B (`verify_citations`). Default `1`. |
| `slug` | `str \| None` | Optional topic slug for log lines and the `.needs_research` signal file. Defaults to `article.get("slug")` / `article.get("topic")` / `""`. |

**Returns:** The draft.txt text body on success — caption + REFERENCES block, ready to write to disk. **Returns `None` on three distinct paths**:

- **`INSUFFICIENT_SOURCE_DATA`** — the source article had zero extractable verified citations. A signal file is written to `work/.needs_research/<slug>.json` for operational triage.
- **LLM not configured** — `is_llm_configured()` returned `False` (no `ANTHROPIC_API_KEY`).
- **`DROP`** — the LLM produced output that failed allow-list or `verify_citations` on every retry.

**Callers cannot distinguish the three None paths from the return value alone.** Log lines on stdout describe which path was taken; for programmatic disambiguation, call `is_llm_configured()` first.

**Raises:** `ValueError` if `article` is not a dict or has no `title`.

**Side effects:** One or more outbound HTTPS requests to `api.anthropic.com` (LLM call, retried at most `max_retries + 1` times). Crossref / PubMed lookups via `verify_citations` for inline-DOI extraction (Layer A) and post-LLM defense-in-depth (Layer B). May write a single file under `work/.needs_research/<slug>.json` on the INSUFFICIENT_SOURCE_DATA path. **Total runtime budget 30-60 seconds end-to-end** — see § 11 for the "background worker only, never request handler" rule.

---

### `parse_draft_text(text, *, filename_hint="draft.txt") -> dict`

Parse the contents of a polished `draft.txt` into a render-time `post` dict (the dict shape documented in § 4). This is the bridge between `generate_draft`'s `Post` shape and `render_page`'s input requirement.

| Arg | Type | Description |
|---|---|---|
| `text` | `str` | Required. Full draft.txt contents — `CAPTION:` block, body, `REFERENCES:` block. Must be non-empty. |
| `filename_hint` | `str` | Cosmetic only. Stamped onto `post["filename"]` for logging. Default `"draft.txt"`. |

**Returns:** A render-time `post` dict (§ 4 schema) ready to hand to `render_page`.

**Raises:** `ValueError` if `text` is empty or not a string. `OSError` if the backing tempfile cannot be created (disk-full / permissions).

**Side effects:** Writes exactly one tempfile to the system temp dir and deletes it before returning. No network. Safe to call concurrently. Callers receive no tempfile paths — the function cleans up after itself.

---

### `generate_chinese_from_english(english_draft, *, temperature=0.7, retry_on_validation_failure=True) -> str | None`

Convert an English post draft into Bruce-Lu-voice Simplified Chinese via Anthropic's Messages API.

| Arg | Type | Description |
|---|---|---|
| `english_draft` | `str` | Full English draft text — caption + REFERENCES block. Must be at least 50 chars. |
| `temperature` | `float` | LLM sampling temperature. Default `0.7`. |
| `retry_on_validation_failure` | `bool` | Retry once at lower temperature if output fails validation (English lift loanwords, missing `参考文献` block). Default `True`. |

**Returns:** Generated Chinese text, or **`None`** if:
- No `ANTHROPIC_API_KEY` is configured (env or `.env`), OR
- The API call ultimately failed after retries, OR
- The output failed validation after retry.

**Callers MUST handle the `None` case — do not crash on missing keys.**

**Raises:** `ValueError` if `english_draft` is shorter than 50 chars.

**Side effects:** One or two outbound HTTPS requests to `api.anthropic.com`. No file writes. The Central Strength gym CTA is **not** included in the returned string — append it separately if needed.

**Related:** `is_llm_configured() -> bool` — preflight check for whether an API key is available.

---

### `render_page(post, output_path=None) -> Path`

Render a parsed-post dict to a single-page PNG (~1080px wide × variable height, 3x scale for print quality).

| Arg | Type | Description |
|---|---|---|
| `post` | `dict` | Required. Schema described in § 4. |
| `output_path` | `Path \| str \| None` | Where to write the PNG. If `None`, writes to a named temp file — **caller is responsible for deletion**. |

**Returns:** Absolute `Path` to the written PNG.

**Raises:** `ValueError` if `post` has no title.

**Side effects:** Writes one PNG file. No network calls. Safe to call concurrently provided each call passes a distinct `output_path`.

---

### `download_references(refs, out_dir, *, delay=1.0, force=False) -> list[Path]`

Batch-download open-access PDFs for a list of reference entries produced by the researcher's URL-resolver.

| Arg | Type | Description |
|---|---|---|
| `refs` | `list[dict]` | Reference entries. Shape documented in § 5. |
| `out_dir` | `Path \| str` | Destination directory. Created if missing. |
| `delay` | `float` | Seconds between HTTP requests. Default `1.0`. |
| `force` | `bool` | Re-download even if a previously-valid PDF exists, and re-attempt previously-failed URLs. Default `False`. |

**Returns:** List of absolute `Path` objects for successfully-downloaded PDFs. Order matches the input. Skipped / failed entries are **not** in the returned list but **are** recorded in `<out_dir>/download_log.json`.

**Raises:** Nothing under normal operation — individual download failures are logged, not raised.

**Side effects:**
- Writes `refNN.pdf` files to `out_dir` (zero-padded ref_idx).
- Writes/updates `<out_dir>/download_log.json` with per-reference outcome metadata.
- Outbound HTTPS via `http_utils` session with the identified `CentralStrengthKB-Research/1.0` User-Agent. Every download is `%PDF`-magic-byte validated before being written — HTML fallback pages never land on disk.
- **Never touches paywalled content.** Only entries with `status == "ok"` are attempted; everything else is silently skipped.

---

### `verify_citations(draft, *, slug="") -> list[CitationIssue]`

Verify every REFERENCES entry in a draft against Crossref + PubMed and return a list of issue rows. **This is the F-0 publication safety gate.** A draft is unsafe to publish if any returned row's severity is in `BLOCKING_SEVERITIES`.

| Arg | Type | Description |
|---|---|---|
| `draft` | `str \| Path` | The draft.txt **contents** as a string, OR a `Path`/path-like string pointing to a draft.txt file on disk. Strings that look like paths but don't exist on disk are treated as draft text. |
| `slug` | `str` | Optional topic slug for traceability. Stamped onto each returned row's `slug` field so consumers can group issues by post. Default `""`. |

**Returns:** A list of `CitationIssue` dicts (TypedDict, see § 10.2), one per REFERENCES entry. Empty list if the draft has no REFERENCES block. Order matches the draft's reference numbering (1-based `ref_idx`).

**Raises:** `ValueError` if `draft` is empty or not a string/Path. `FileNotFoundError` if `draft` is a Path that doesn't exist.

**Side effects:** Outbound HTTPS to `api.crossref.org`, `doi.org`, `eutils.ncbi.nlm.nih.gov`. Each REFERENCES entry triggers 1-3 lookups (~1-2 seconds per citation). **A 5-ref draft takes ~10 seconds — run this in a background job, NOT a request handler.** No file writes.

**Graceful degradation:** if Crossref or PubMed are unreachable (network failure, rate limit, DNS, timeout), the affected row is returned with `severity = "VERIFICATION_UNAVAILABLE"` and a `notes` field. The function does NOT raise on network errors. `VERIFICATION_UNAVAILABLE` is NOT in `BLOCKING_SEVERITIES` — treat it as "unknown, escalate to human", not as pass or fail.

---

### `is_blocking(severity, *, allowed=None, unknown_blocks=True) -> bool`

Return True iff a citation severity should fail an F-0 publication gate. Convenience helper that wraps the `BLOCKING_SEVERITIES` frozenset with consumer-override and forward-compat support.

| Arg | Type | Description |
|---|---|---|
| `severity` | `str` | A severity string from a `CitationIssue.severity` field. |
| `allowed` | `frozenset[str] \| None` | Optional override for the blocking set. Pass your own collection to use a stricter or looser policy than `BLOCKING_SEVERITIES`. |
| `unknown_blocks` | `bool` | When True (default), severities not in `BLOCKING_SEVERITIES`, `SOFT_FLAG_SEVERITIES`, or `{"OK", "VERIFICATION_UNAVAILABLE"}` are treated as blocking. Forward-compat: future audit module revisions may emit new severities, and a publication gate should over-block on unknown. |

**Returns:** `bool`.

**Side effects:** None. Pure function, safe to call from any context.

Typical usage:

```python
from contentprinter import verify_citations, is_blocking

issues = verify_citations(draft_text, slug="nutrition_creatine")
blocked = [i for i in issues if is_blocking(i["severity"])]
if blocked:
    job.status = "verification_failed"
    job.failed_citations = blocked
else:
    job.status = "verified"
```

---

### `refresh_audit_meta(slug, *, dry_run=False) -> str`

Re-audit a single post's `draft.txt` and re-stamp its `meta.json` with the result. **The only sanctioned mechanism** to update audit fields after a remediation edit — see § 10.5 for the rule and § 11.3 for the CSKB job-runner integration.

| Arg | Type | Description |
|---|---|---|
| `slug` | `str` | Required. Topic slug (per-post directory name under `work/`). The function reads `work/<slug>/en/draft.txt` and writes `work/<slug>/meta.json`. |
| `dry_run` | `bool` | When True, run verification but skip the meta.json write. Returns a status string describing what would have been written. Default `False`. |

**Returns:** A status string — one of `"refreshed: <slug> -> <status>"`, `"unchanged: <slug>"`, `"missing-draft: <slug>"`, or `"dry-run: <slug> -> <would-be-status>"`. The set of return strings may grow; existing strings will not be renamed.

**Raises:** `ValueError` if `slug` is empty or not a string. `FileNotFoundError` if the topic directory itself doesn't exist.

**Side effects:** Reads `work/<slug>/en/draft.txt`. Outbound HTTPS to Crossref + PubMed via `verify_citations` (1-2 seconds per REFERENCES entry; ~10 seconds for a 5-ref post). Writes `work/<slug>/meta.json` unless `dry_run=True` or the merged content is byte-equal to what's already on disk. **Synchronous and not safe to call from a FastAPI request handler** — run in a background worker.

---

### `scrape_for_topic(topic, *, category=None, max_sources=5, languages=None, timeout_seconds=30.0) -> list[dict]`

Run an on-demand PubMed query and return up to `max_sources` canonical Article dicts ready to feed into `generate_grounded_draft`. Added in 0.4.0 to bridge the CSKB job-runner gap — the existing scrapers in `src/*_scraper.py` are batch entry points that walk config files and write `work/raw/*.json` dumps; that shape doesn't fit a request handler that needs "give me N articles about creatine, now."

**v1 is PubMed-only by design.** Only PubMed yields `structured_content` with DOI/PMID/authors/year, which is the only path that gives the grounded drafter a non-empty allow-list deterministically. bioRxiv/RSS/YouTube/Reddit handlers are deferred — adding them would just push more jobs into `INSUFFICIENT_SOURCE_DATA` without improving drafter output.

| Arg | Type | Description |
|---|---|---|
| `topic` | `str` | Required. Free-text search query, passed verbatim to NCBI's esearch. |
| `category` | `str \| None` | Caller record-keeping label. Stamped into each returned dict's `topic` field but **not used as a search filter** — PubMed relevance ranking is good enough in v1. Defaults to `None`, in which case the stamped topic falls back to `"training"`. |
| `max_sources` | `int` | Upper bound on returned articles. The function overfetches 2x at the esearch layer to absorb efetch parse failures, then slices to exactly `max_sources`. Default `5`. |
| `languages` | `list[str] \| None` | Reserved for future use. Ignored in v1. |
| `timeout_seconds` | `float` | Per-request network timeout. Currently advisory — the underlying `http_utils` session uses its own default. Default `30.0`. |

**Returns:** A list of Article dicts, length `≤ max_sources`. Each dict matches the canonical shape consumed by `generate_grounded_draft` — see `src/pubmed_scraper.build_entry_from_article` for the field-by-field definition. Required fields: `title`, `url`, `source`, `source_type="pubmed"`, `topic`, `summary`, `full_text`, `structured_content` (with `pmid`, `doi`, `authors`, `year`, `journal`, `mesh_terms`), `scraped_at`, `hash`. **Empty list on zero results — not an error**, so the caller can land a job in a deterministic `failed` state with a useful message rather than catching an exception.

**Raises:** `ValueError` if `topic` is empty or not a string, or if `max_sources` is not a positive int. `TopicScraperError` if the PubMed esearch or efetch call itself fails (network down, NCBI 5xx, etc.); the `__cause__` of the raised exception is the original transport error.

**Side effects:** Two outbound HTTPS requests to `eutils.ncbi.nlm.nih.gov` per call (one esearch, one efetch), with a 1-second rate-limit sleep between them per NCBI's unauthenticated-client guidance. No disk writes. **Synchronous and not safe to call from a FastAPI request handler** — run in a background worker (same constraint as `generate_grounded_draft` and `refresh_audit_meta`).

**F-0 interaction:** This function does NOT call `verify_citations` on the sources it returns. Verification happens at the drafter allow-list layer (`grounded_drafter.extract_allowed_citations`), which is the single chokepoint for what gets cited. A topic query that yields PubMed records with unverifiable DOIs will produce an empty allow-list downstream and the job will drop to `INSUFFICIENT_SOURCE_DATA` cleanly — no double-verification, no drift.

### `TopicScraperError`

`RuntimeError` subclass raised by `scrape_for_topic` on transport failures only. Not raised on zero results — see above. Catch this at the job-runner layer and surface as a `failed` job with the underlying cause in `meta.error`.

---

## 3. The `Post` dict shape

Returned by `generate_draft` and consumed by `render_page` (after an additional structuring pass — see § 4 for the render-time shape). Fields:

| Field | Type | Notes |
|---|---|---|
| `post_number` | `int` | Sequential index. |
| `topic` | `str` | One of `training`, `nutrition`, `techniques`, `rehab`, `supplements`, etc. |
| `source` | `str` | Source publication / channel name. |
| `source_url` | `str` | URL of the original article. |
| `title` | `str` | Post title (used as carousel slide 1 headline). |
| `caption` | `str` | Full Instagram caption with key findings, practical tips, CTA, hashtags. |
| `key_points` | `list[str]` | Up to 4 extracted key takeaways. |
| `carousel_slides` | `list[dict]` | Slide specs — each has `slide`, `type`, `headline`, `text`. First slide is title; last is CTA. |
| `suggested_visual` | `str` | Editorial hint for accompanying imagery. |
| `drafted_at` | `str` | ISO-8601 timestamp. |

---

## 4. The render-time `post` dict shape (input to `render_page`)

The renderer expects a more structured dict than `generate_draft` produces — it's the output of parsing a saved `draft.txt` file, and captures layout-specific fields (`numbered_points`, `sections`, `evidence_info`, community-source sidecar data, etc.) that the initial draft doesn't carry.

**For the KB app's use case, the typical flow is:**

```
scraped article → generate_draft → draft.txt string → parse_draft_text → render_page
```

In code:

```python
from contentprinter import generate_draft, parse_draft_text, render_page

post = generate_draft(article)                     # Post dict from § 3
draft_text = render_post_as_text(post)             # your code: serializes Post to draft.txt format
render_post = parse_draft_text(draft_text)         # render-time post dict (§ 4 schema)
png_path = render_page(render_post, output_path=your_dest)
```

`parse_draft_text` is the public library entry point — **consumers never import `parse_detailed_content` from `src.*`**. The tempfile bookkeeping it does internally is invisible.

The renderer dict must have at minimum:

| Field | Type | Required? |
|---|---|---|
| `title` | `str` | yes |
| `topic` | `str` | yes |
| `topic_emoji` | `str` | optional |
| `intro_text` | `str` | optional |
| `key_stat` | `str` | optional |
| `sections` | `list[dict]` | one of `sections` or `numbered_points` must be non-empty |
| `numbered_points` | `list[dict]` | each has `headline` and `body` |
| `extra_sections` | `list[dict]` | optional (what-to-avoid, signs, etc.) |
| `practical_guide` | `list[str]` | optional |
| `summary_text` | `str` | optional |
| `references` | `list[dict]` | each has `citation` |
| `layout` | `str` | `"default"`, `"program"`, `"mythbust"`, `"rehab"`, `"supplement"`, or community variants (TBD Task #13) |
| `evidence_info` | `dict` | pass `{}` for community sources |

**Expansion for community sources (Reddit / forum) lands under Task #13** — the schema will gain `reddit_meta`, `reddit_callouts`, `forum_meta`, `forum_quote_chain` fields documented in `config/source_format_design.md`. Consumers can ignore those today.

---

## 5. The reference dict shape (input to `download_references`)

Matches the researcher's pre-resolved JSON format in `audits/training_pdf_urls.json` and `config/upcoming_pdf_urls.json`. Fields:

| Field | Type | Notes |
|---|---|---|
| `ref_idx` | `int` | Required. Used as the output filename (`refNN.pdf`, zero-padded). |
| `status` | `str` | Required. One of `"ok"`, `"unresolved"`, `"pmid_only"`, `"no_doi"`. Only `"ok"` is attempted. |
| `pdf_url` | `str \| None` | Required when `status == "ok"`. |
| `citation` | `str` | Recommended — appears in `download_log.json`. |
| `doi` | `str \| None` | Optional — preserved in log for traceability. |
| `pmid` | `str \| None` | Optional. |
| `source` | `str \| None` | Optional — resolver provenance (e.g. `"unpaywall:publisher"`, `"pmc:PMC2931407"`). |

Any additional keys in a ref dict are preserved in `download_log.json` but not used for the download.

---

## 6. Graceful degradation guarantees

1. **No API key → `generate_chinese_from_english` returns `None`.** Never crashes. Callers must handle.
2. **`download_references` filters out failures.** It returns a list of Paths for **successful downloads only** — the list is a subset of the input, preserving input order. Individual HTTP errors, missing `%PDF` magic, publisher 403s, and non-ok researcher statuses are all recorded in `download_log.json` and skipped from the return list. **Callers must compare `len(result)` against `len(refs)` (filtered to `status == "ok"`) to detect failures**, then inspect `download_log.json` for per-reference reasons. `generate_chinese_from_english` returns `None` on any unrecoverable failure; `generate_draft` and `parse_draft_text` are pure and unaffected by network state.
3. **Unreachable publisher (403 / timeout) → recorded in `download_log.json` with reason, not raised.**
4. **HTML fallback served instead of a PDF → rejected by magic-byte validation, recorded as `failed`, not raised.**
5. **Write failures raise.** `render_page` will raise `OSError` if the backing disk is full, permissions are wrong, or `output_path`'s parent can't be created. It does **not** silently drop — a returned `Path` always points to a file that was written successfully. Same guarantee for `parse_draft_text`'s internal tempfile: if the tempdir is unwritable, `OSError` surfaces rather than returning a half-parsed dict.
6. **`verify_citations` never raises on network failure.** When Crossref or PubMed are unreachable (DNS, timeout, 5xx, rate limit), the affected reference row is returned with `severity = "VERIFICATION_UNAVAILABLE"` and a `notes` field explaining the failure. The function does NOT raise on individual network errors. `VERIFICATION_UNAVAILABLE` is **not** in `BLOCKING_SEVERITIES` — consumers should treat it as "unknown, escalate to a human reviewer", not as either pass or fail. The only `verify_citations` exceptions are `ValueError` (empty/invalid input) and `FileNotFoundError` (Path arg pointing at a missing file). **Callers MUST check `len(blocked) > 0` rather than catching exceptions** — the gate is data-driven, not exception-driven.
7. **`generate_grounded_draft` returns `None` on three distinct failure paths**: INSUFFICIENT_SOURCE_DATA (zero extractable verified citations from the source article), no `ANTHROPIC_API_KEY`, or DROP (allow-list / verify_citations rejected the LLM output on every retry). The function never raises on the network round-trip itself — Anthropic API failures fall through to DROP after `max_retries + 1` attempts, and Crossref / PubMed failures during inline-DOI extraction skip the candidate without raising. The only `generate_grounded_draft` exception is `ValueError` (article missing required `title`). **Callers MUST handle `None`** — and SHOULD log-and-skip rather than retry the same article without a topic-source change, since the three None paths are not transient. The INSUFFICIENT_SOURCE_DATA path is the only one that writes a side-effect file (`work/.needs_research/<slug>.json`); the LLM-not-configured and DROP paths are silent on the filesystem.

---

## 7. Stability Promise

This API surface is **version 0.4.0**. While we're in 0.x:

- **Function signatures** (name + positional/keyword args + return type) are **frozen** within a minor version. If a signature must change, the minor version bumps and the old signature stays as a compatibility shim for one release.
- **Return dict shapes** may **gain new fields** without a version bump. **Existing fields and their types will not change** without a version bump.
- **Graceful degradation behaviors** (the § 6 list) are frozen — None-returning paths stay None-returning, log-and-continue paths stay log-and-continue.
- **Enumerated string values** (like `layout`, `status`) may **gain new variants** without a version bump; existing values will not be renamed or removed.
- **Exception types are part of the signature.** The concrete exception class raised by each function (`ValueError` for input validation, `OSError` for disk I/O, `FileNotFoundError` as the specific `OSError` subclass for missing paths) is stable within a minor version. A function that currently raises `ValueError` for bad input will not start raising `TypeError` without a minor version bump. Callers may write `except ValueError` with confidence.
- **Documented caller obligations are part of the stability promise.** If this doc says "caller is responsible for deletion" (tempfile fallback in `render_page`), or "callers MUST handle `None`" (`generate_chinese_from_english`), or "append the gym CTA separately" — those obligations will not silently change to "the library handles it". If the library starts auto-handling something, the old obligation-bearing path still works (backward compat), and the new auto-handling is additive.
- **`__version__` bump policy:** the patch component (`0.1.0` → `0.1.1`) bumps when new symbols are added, docstrings are clarified, or internal refactors happen — additive only. The minor component (`0.1.x` → `0.2.0`) bumps when any of the above rules require it: signature change, return-shape field removal/rename, exception-type change, degradation-path change, enum rename/removal, or caller-obligation change. Major (`0.x.y` → `1.0.0`) is reserved for the 1.0 tightening (see below).

At 1.0 the promise tightens: major version bump required for any signature change, and compatibility shims are mandatory for at least one major release.

**Breaking changes since 0.1.0:** *none.* All version bumps to date have been additive.

- **0.1.0 → 0.1.1** (additive): added `parse_draft_text` to complete the § 4 consumer flow, tightened § 6 degradation wording for `download_references` return semantics and write-failure behavior, added exception-type / caller-obligation / version-bump clauses to § 7. No existing signatures, return shapes, or degradation paths were changed.
- **0.1.1 → 0.2.0** (additive, but minor-bump because new exports): added `verify_citations`, `is_blocking`, `BLOCKING_SEVERITIES` (frozenset), `SOFT_FLAG_SEVERITIES` (frozenset), `VERIFICATION_UNAVAILABLE` (str constant), and `CitationIssue` (TypedDict). New § 10 documents the citation verification severity ladder. § 6 added a new degradation guarantee #6 covering `verify_citations` network-failure behavior. **No existing signatures, return shapes, or degradation paths were changed.** The minor bump (rather than patch) reflects that the new public surface introduces a load-bearing F-0 gate that consumers will build against — even though the change is strictly additive, the policy document for `is_blocking()` (which severities count as blocking) is now part of the stability promise and a future change to that set requires another minor bump.
- **0.2.0 → 0.3.0** (additive, but minor-bump because new export with load-bearing semantics): added `generate_grounded_draft(article, *, max_retries=1, slug=None) -> str | None`. New § 11 documents the grounded LLM drafting workflow as Layer 1 of the citation-hallucination defense (Layer 2 = `verify_citations`, Layer 3 = `audit_meta_writer`). § 6 added a new degradation guarantee #7 covering the three None paths (INSUFFICIENT_SOURCE_DATA, no API key, DROP). **No existing signatures, return shapes, or degradation paths were changed.** The minor bump (rather than patch) reflects that the new export is the canonical safe-drafter API for any consumer wanting publication-grade output — the existing `generate_draft` template path is preserved unchanged but is no longer the recommended entry point for content destined for the Central Strength brand.
- **0.3.0 → 0.3.1** (additive patch): promoted `refresh_audit_meta` from "src/-shim escape hatch" to a first-class `contentprinter.refresh_audit_meta` export via a thin `contentprinter/audit.py` wrapper. CSKB consumers now write `from contentprinter import refresh_audit_meta` instead of `from audit_meta_writer import refresh_audit_meta` — the unsanctioned-import grep gate stays clean and the §11.3 CSKB handler sketch no longer needs an escape-hatch exception. § 9.1 leak list also updated to add `audit_meta_writer` and `grounded_drafter` as transitional bare-top-level names (still importable via the `pip install -e .` shim, but officially unsanctioned). Patch bump (not minor) because no new public semantics are introduced — the wrapper is a 1:1 delegation to the existing `audit_meta_writer.refresh_audit_meta` function with the same signature and return-string set. The wrapper file is trivially removable when Task #33 (next sprint, required) collapses `src/` into `contentprinter._internal` — the public import path stays the same; only the internal `import audit_meta_writer as _amw` line gets rewritten.
- **0.3.1 → 0.4.0** (additive, but minor-bump because new export with load-bearing semantics): added `scrape_for_topic(topic, *, category=None, max_sources=5, languages=None, timeout_seconds=30.0) -> list[dict]` and the accompanying `TopicScraperError` exception class. Bridges the on-demand topic-query gap that the existing batch scrapers (`src/*_scraper.py`) couldn't fill — they walk config files and write `work/raw/*.json` dumps, which doesn't fit a request handler that needs "give me N PubMed articles about X, now." v1 is **PubMed-only by design**; the returned dicts use the same canonical Article shape the batch path already produces (extracted from `scrape_pubmed`'s inner loop into a reusable `pubmed_scraper.build_entry_from_article` helper, so there's a single source of truth for the field mapping that `grounded_drafter._structured_to_citation` reads). **No existing signatures, return shapes, or degradation paths were changed.** The minor bump (rather than patch) reflects that `scrape_for_topic` is the canonical entry point for any downstream that wants to feed `generate_grounded_draft` from a free-text query rather than a pre-scraped JSON dump — once CSKB's job runner adopts it, future changes to the function or its `TopicScraperError` semantics are part of the stability promise. Empty-list-on-zero-results vs. exception-on-transport-failure is the load-bearing semantic and is now frozen per § 7.

### URL matching for round-trip topic lookup

When `contentprinter.drafter.generate_draft` produces a draft for an article whose `source_url` matches an existing topic's `meta.json`, it reuses the existing `topic_slug` instead of generating a new one. URL matching is done on a canonicalized form that:

1. Lower-cases the scheme and host.
2. Drops fragment anchors (`#comments`).
3. Drops trailing slashes.
4. **Strips common tracking query parameters** (`utm_*`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`, `ref`, `ref_src`, `igshid`, `yclid`, `msclkid`, `_hsenc`, `_hsmi`).
5. **Preserves real content query parameters** (`?id=123`, `?page=2`, `?v=<youtube-id>`, `?t=week`, etc.).

This means `https://barbend.com/creatine?utm_source=feed` and `https://barbend.com/creatine` map to the same topic, but `https://example.com/post?id=1` and `https://example.com/post?id=2` remain distinct. The tracking-param list may be extended in a future minor version; callers can rely on existing entries staying stripped.

---

## 8. Consumer checklist for the KB app FastAPI service

- [ ] Install ContentPrinter repo as a sibling directory of the service repo, or as a git submodule.
- [ ] Add the ContentPrinter repo root to `PYTHONPATH`, or `pip install -e .` once a `pyproject.toml` exists (TBD — if the KB app needs this, file a task and I'll add it).
- [ ] Import from `contentprinter`, never from `src.*`.
- [ ] Check `is_llm_configured()` at startup and surface a warning if False — don't let users submit Chinese-generation requests if the key is missing.
- [ ] Pass a stable `output_path` to `render_page` (don't rely on the temp-file fallback in production — you'll leak tempfiles).
- [ ] Treat `download_references` as an async-worthy I/O operation. Running it in a FastAPI request handler will block the event loop for up to several seconds per reference — move it to a background task / Celery / RQ.
- [ ] For Chinese drafts: the pure Bruce-Lu output does NOT include the gym CTA. Append your own CTA downstream based on the app's editorial rules.

---

## 9. Internal stability notes (not part of the promise)

Things that *might* change and that consumers should not depend on:

- The `src/` module layout and filenames.
- The exact log format of `download_log.json` (stable keys: `entries.<refKey>.status`, `entries.<refKey>.path`; other keys may churn).
- The `work/` on-disk scratch directory structure (tracked by `posts_layout.py` helpers, which are internal — if the KB app needs layout introspection, file a task). Final published output under `Posts/<category>/` is routed via `output_layout.finalize`.
- The exact prompt text in `config/chinese_prompt_template.md`. The *voice* is stable; the prompt wording is not.

If you find yourself reaching into `src/*` to get something done, file a task to expose it properly here.

### 9.1 Top-level module leak from `pip install -e .` — DO NOT IMPORT

When this package is installed via `pip install -e .` (or a wheel install), the following module names become importable at the top level of the consumer's Python environment as a pragmatic workaround for the contentprinter shim layer:

```
audit_meta_writer, biorxiv_scraper, chinese_drafter, drafter, forum_scraper,
grounded_drafter, http_utils, llm_client, main, pdf_downloader, posts_layout,
pubmed_scraper, recursive_discovery, reddit_scraper, reorganize_posts, scraper,
single_page_generator, source_promoter, text_utils, youtube_scraper
```

These names exist in the venv namespace because the `contentprinter/*.py` shim modules do bare absolute imports (e.g. `import drafter as _drafter`) that need to resolve in both dev mode and install mode. The cleaner long-term layout collapses these into a private `contentprinter._internal` subpackage — see Task #33 for the planned refactor, **scheduled for the next sprint as required work** rather than the deferred 1.0 cleanup. The atomic refactor (~25 intra-src import rewrites + a CLI invocation switch from `python src/main.py` to `python -m src.main`) is cheaper than wrapping `src/*` modules one at a time and is a hard prerequisite for any consumer that wants to write a clean grep-gate against unsanctioned imports.

**Consumers MUST NOT import these names directly.** They are NOT part of the public API. They may disappear without a version bump the moment Task #33 lands. Use `from contentprinter import ...` exclusively. If you find yourself writing `import drafter` from a CSKB handler, that is a contract violation and a bug — file a task to expose the symbol you need through the `contentprinter.*` namespace instead.

**No sanctioned escape hatches as of 0.3.1.** `audit_meta_writer.refresh_audit_meta` previously required a bare top-level import; that escape hatch is closed by the `contentprinter.refresh_audit_meta` wrapper added in 0.3.1. `grounded_drafter` is wrapped by `contentprinter.generate_grounded_draft`. Both modules remain in the leak list above because the `pip install -e .` shim layer makes them importable at the top level — but **no consumer code should reference them by their bare top-level names**, period. The grep-gate below should reject every name in the leak list without exception. Task #33 (next sprint, required) will collapse `src/` into a private `contentprinter._internal` subpackage and eliminate the leak entirely; until then, the grep-gate is the enforcement mechanism.

The leak is not detectable at runtime (the names work), so this section is the only place it is documented. Code-reviewer should grep PRs in any consumer repo for `^(?:from|import) (?:audit_meta_writer|biorxiv_scraper|chinese_drafter|drafter|forum_scraper|grounded_drafter|http_utils|llm_client|main|pdf_downloader|posts_layout|pubmed_scraper|recursive_discovery|reddit_scraper|reorganize_posts|scraper|single_page_generator|source_promoter|text_utils|youtube_scraper)\b` and reject any matches.

---

## 10. Citation verification (the F-0 publication gate)

`verify_citations` returns a list of `CitationIssue` rows. Each row carries a `severity` string drawn from a closed enumeration documented here. Severities split into three buckets: **blocking** (publication-unsafe, F-0 fails the job), **soft flag** (worth a human glance but not blocking), and **OK / unavailable** (not blocking).

### 10.1 Severity ladder

| Severity | Bucket | Meaning | Code path |
|---|---|---|---|
| `OK` | clean | Author surname matches, year within ±1, ≥25% title-word overlap, journal family matches. | `_citation_audit.py:classify` happy path |
| `DOI_FABRICATED` | **BLOCKING** | DOI does not exist anywhere — neither Crossref nor doi.org HEAD can resolve it. The DOI string was invented. | `audit_draft` exception branch when `doi_exists()` returns False |
| `DOI_WRONG` | **BLOCKING** | DOI resolves to a real paper, but it's a completely different paper (different author AND title overlap < 25%). The DOI was either copied at random or fabricated to look plausible. | `classify` |
| `DOI_MISATTRIBUTED` | **BLOCKING** | The "title theft" pattern: DOI resolves to a paper whose title matches the draft (≥80% word overlap), but the first author differs. The drafter invented an author name and attached it to a real paper's title + DOI. **Defeats casual human review.** | `classify` |
| `NO_VERIFIABLE_SOURCE` | **BLOCKING** | No DOI, no PMID in the draft, and PubMed search on (first_author, year, title keywords) returned nothing. Cannot verify the paper exists. | `audit_draft` no-DOI no-PMID no-hit branch |
| `PMID_NOT_FOUND` | **BLOCKING** | The draft cites a PMID, but PubMed returned an empty record for it. PMID is fake or malformed. | `audit_draft:350` |
| `AUTHOR_WRONG` | **BLOCKING** | DOI resolves to a paper whose title overlap with the draft is in the 25%-80% range, but the first-author surname differs. Possibly a partial title-theft variant. | `classify` line 284 |
| `TITLE_MISMATCH` | **BLOCKING** | Author and year match, but title overlap < 25%. The draft is making a claim about a real paper's title that doesn't match the actual title. | `classify` line 290 |
| `JOURNAL_MISMATCH` | soft flag | Everything else matches but the cited journal name differs from the actual venue. Usually a transcription error, not a hallucination. | `classify` |
| `YEAR_WRONG` | soft flag | Author and title match, year off by >1. Usually a transcription error. | `classify` |
| `NOT_PUBMED_INDEXED` | soft flag | Textbook, institutional report, blog post, YouTube video, or non-peer-reviewed source. Not verifiable via Crossref/PubMed by design. Editor must confirm by hand. | `audit_draft:361` |
| `DOI_UNRESOLVABLE` | soft flag | Crossref returns 404 for the DOI, but doi.org accepts it (redirect 200-range). Paper may be genuine but not yet indexed by Crossref. Rare. | `audit_draft:331` |
| `VERIFICATION_UNAVAILABLE` | escalate-to-human | **Wrapper-emitted, not from the audit module.** Crossref or PubMed lookup failed at verify time (network outage, DNS, rate limit, timeout). The citation may still be valid — a human reviewer should retry or check by hand. NOT in `BLOCKING_SEVERITIES`. Two emission paths: (1) `verify_citations` exception handler (audit_draft itself raises); (2) `verify_citations` post-processing normalization when the audit module reports `PMID_FETCH_ERROR` or a `DOI_FABRICATED` whose `fetch_error` text indicates a network outage rather than a real Crossref 4xx response. In the second case the original audit-module label is preserved on the row's `original_severity` field for traceability. | `verify_citations` exception handler + normalization helper |

The blocking set `BLOCKING_SEVERITIES` is a public `frozenset[str]` exported from the package:

```python
from contentprinter import BLOCKING_SEVERITIES
# frozenset({
#     "DOI_FABRICATED", "DOI_WRONG", "DOI_MISATTRIBUTED",
#     "NO_VERIFIABLE_SOURCE", "PMID_NOT_FOUND", "AUTHOR_WRONG",
#     "TITLE_MISMATCH",
# })
```

The soft-flag set `SOFT_FLAG_SEVERITIES` is similarly exported. Both sets are part of the stability promise: a future minor version may **add** new severities, but **will not remove or reclassify** existing entries.

**Forward compatibility:** four of the seven blocking severities (`DOI_FABRICATED`, `DOI_WRONG`, `DOI_MISATTRIBUTED`, `NO_VERIFIABLE_SOURCE`) were observed in the 2026-04-12 audit dataset. The other three (`PMID_NOT_FOUND`, `AUTHOR_WRONG`, `TITLE_MISMATCH`) are emitted by code paths in `audits/_citation_audit.py` that did not fire on that specific dataset but will fire on future drafts with different hallucination patterns. They are included in `BLOCKING_SEVERITIES` from the start because the asymmetric cost of error (false negative = published hallucination = reputation event) demands over-blocking on a publication gate.

**Consumer override:** `is_blocking(severity, allowed=...)` accepts a custom blocking set if a consumer needs a stricter or looser policy than the default. The default is the safe maximum-block set; only override with explicit reasoning.

### 10.2 `CitationIssue` schema

```python
class CitationIssue(TypedDict, total=False):
    slug: str                      # topic slug, "" if caller passed raw text
    ref_idx: int                   # 1-based index in the REFERENCES block
    raw: str                       # original citation line from the draft
    severity: str                  # see § 10.1
    draft: dict                    # what was parsed from the draft text
    fetched: dict | None           # what Crossref/PubMed returned
    verify: dict                   # match flags + title overlap fraction
    notes: str | None              # human-readable explanation
    fetch_error: str               # truncated error msg if a network call failed
    original_severity: str         # only present on normalized rows; see § 10.4
```

The `draft` sub-dict has six keys: `first_author`, `year`, `title`, `journal`, `doi`, `pmid`. The `fetched` sub-dict has four keys: `first_author`, `year`, `title`, `journal` (no `doi`/`pmid` because Crossref/PubMed lookups return the canonical record, not the draft's identifier). `verify` has `author_match: bool|None`, `year_match: bool|None`, `title_overlap: float`, `journal_match: bool`.

**`draft` schema is consistent across all code paths**, including the `VERIFICATION_UNAVAILABLE` exception path — earlier versions had a 5-key drift (no `journal`) on the exception path; that was fixed in the #36 patch and is now regression-tested.

All schema fields except `slug`, `ref_idx`, `raw`, and `severity` may be missing or None depending on which audit code path produced the row. Consumers should defensively check for key presence rather than assume.

### 10.3 The CSKB F-0 gate pattern

The canonical job-runner integration:

```python
from contentprinter import verify_citations, is_blocking

def run_verification_step(job, draft_text):
    issues = verify_citations(draft_text, slug=job.topic_slug)
    blocked = [i for i in issues if is_blocking(i["severity"])]
    unavailable = [i for i in issues if i["severity"] == "VERIFICATION_UNAVAILABLE"]

    if blocked:
        job.status = "verification_failed"
        job.failed_citations = blocked
        return

    if unavailable:
        job.status = "verification_pending_review"
        job.unavailable_citations = unavailable
        # Surface in iOS UI for human reviewer; do NOT auto-publish
        return

    job.status = "verified"
```

**Three-bucket outcome.** Don't collapse `verification_pending_review` into either `verified` or `verification_failed`. The whole point of the `VERIFICATION_UNAVAILABLE` severity is that the system **doesn't know** whether the citation is real, and a human needs to look at it. Auto-treating it as either pass or fail re-introduces the failure mode that #21 caught.

### 10.4 Network-failure normalization

The audit module catches its own network exceptions inside the Crossref / PubMed lookup branches and emits classification-style severity labels even when the underlying problem was a network outage. Two specific cases:

1. **`PMID_FETCH_ERROR`** — emitted at `_citation_audit.py:358` when PubMed `_get()` raises. This severity has no legitimate non-network meaning and is unconditionally normalized.

2. **`DOI_FABRICATED` with a network error in `fetch_error`** — emitted at `_citation_audit.py:334` when Crossref `_get()` raises AND `doi_exists()` returns False. The `doi_exists` HEAD check is best-effort: if doi.org is also unreachable, `_head` returns None, `doi_exists` returns False, and the row gets the same `DOI_FABRICATED` label as a real fabrication. The disambiguating signal is the recorded `fetch_error` text:

   - **Real fabrication** (preserve `DOI_FABRICATED`): Crossref returned an HTTP 4xx (not 429) — `"HTTP Error 404: Not Found"`, `"HTTP Error 410: Gone"`, etc. The verifier successfully reached the server, the DOI just doesn't exist.
   - **Network outage** (normalize to `VERIFICATION_UNAVAILABLE`): URLError, timeout, DNS failure, 5xx, or 429 rate limit. Pattern matches are documented in `contentprinter/verify.py:_NETWORK_ERROR_PATTERNS`.

`verify_citations` post-processes every row from `audit_draft` and applies this normalization automatically. Normalized rows carry their original audit-module label in a new `original_severity` field for traceability:

```python
{
    "severity": "VERIFICATION_UNAVAILABLE",
    "original_severity": "DOI_FABRICATED",
    "fetch_error": "<urlopen error [Errno -3] Temporary failure in name resolution>",
    "notes": "Network failure during verification (audit module reported "
             "`DOI_FABRICATED` but the underlying error indicates an outage, "
             "not a classification result). ...",
    ...
}
```

**Why this matters for remediation:** without normalization, a VPN drop during a citation audit run would produce spurious `DOI_FABRICATED` labels on real citations. A remediation operator (Task #31) seeing the label would burn lookup time chasing a non-problem. The normalization is safe-direction in both directions: real fabrications stay flagged (preserved), network outages don't trap legitimate citations in BLOCKED state (normalized + escalated to human via `VERIFICATION_UNAVAILABLE`).

Consumers reading `severity` see the normalized value and route through `is_blocking`. Consumers wanting to surface the original audit-module label for debugging can check `original_severity` (only present on normalized rows; absent on rows that came through clean).

### 10.5 Per-post re-audit after remediation (`refresh_audit_meta`)

When a draft.txt is edited (e.g. a remediation pass that drops a fabricated citation and renumbers the remaining refs), the `meta.json`'s `audit_status`, `publication_allowed`, and `audit_issues` fields become stale relative to the new draft state. The `refresh_audit_meta` helper is the **only sanctioned mechanism** to bring `meta.json` back into sync after a draft edit.

```python
from contentprinter import refresh_audit_meta
status_msg = refresh_audit_meta("nutrition_vegan_creatine")
```

CLI form for the remediation workflow:

```bash
# After editing work/<slug>/en/draft.txt:
python src/audit_meta_writer.py --refresh nutrition_vegan_creatine
```

Pipeline (from the helper's docstring):

1. Read `work/<slug>/en/draft.txt`
2. Call `contentprinter.verify_citations(draft_path, slug=slug)` for fresh rows
3. Build audit fields with today's date via `build_audit_fields`
4. Merge into existing `meta.json` via `posts_layout.merge_meta` (preserves unrelated fields like `tags`, `references`, `source_name`)
5. Skip the write if the new fields match the existing ones exactly (idempotent)

**DO NOT** manually patch `audit_issues` indices or any other audit field after a draft edit. Manual patches drift from the actual draft state and re-introduce the trust-the-edit-instead-of-the-source failure pattern that the F-0 gate exists to prevent. Always call `refresh_audit_meta` (or the `--refresh` CLI form).

**Network behavior:** `refresh_audit_meta` makes outbound HTTPS calls via `verify_citations` (1-2 sec per citation). A 5-citation post refresh takes ~10 seconds. Run as a background operation, not in a request handler.

**CSKB reuse path:** the CSKB job runner's `verifying` lifecycle step (Objective F-0) calls `contentprinter.refresh_audit_meta(slug)` as its core verification mechanism — same code path as the ContentPrinter remediation workflow, no per-environment re-implementation. The full handler sketch lives in § 11.3.

**Stability promise:** `refresh_audit_meta` is a **public library export as of 0.3.1** (`from contentprinter import refresh_audit_meta`). The signature is `refresh_audit_meta(slug: str, *, dry_run: bool = False) -> str` and is frozen per § 7. The returned status-string set may grow; existing strings will not be renamed. Implementation lives in `src/audit_meta_writer.py` and is bridged via the thin `contentprinter/audit.py` wrapper; both file locations may move when Task #33 lands but the public import path (`from contentprinter import refresh_audit_meta`) is permanent.

---

## 11. Grounded LLM drafting

`generate_grounded_draft` is the publication-safe LLM drafter and Layer 1 of the three-layer citation-hallucination defense:

| Layer | Function | Role |
|---|---|---|
| **1. Source-grounded generation** | `generate_grounded_draft` (this section) | Extract verified citations from the source article, pass as a hard allow-list to the LLM, reject any non-allow-listed output. |
| **2. Verification gate** | `verify_citations` (§ 10) | Re-verify every reference in any draft against Crossref / PubMed. Catches hallucinations regardless of how they entered the draft. |
| **3. Audit-state stamping** | `refresh_audit_meta` (§ 10.5) | Persist the verification result to `meta.json` so downstream renderers and the F-0 publication gate see a single source of truth. |

The three layers compose: a draft produced by Layer 1 is verified by Layer 2 and stamped by Layer 3. A draft produced *outside* Layer 1 (e.g. via the existing template path or a manual edit) is still caught by Layers 2 and 3 — defense in depth.

### 11.1 Why grounded vs. template

The repository ships two drafter entry points with intentionally different contracts:

| Function | Output | Citations | Use when |
|---|---|---|---|
| `generate_draft(article)` | Pure-Python template assembly. No LLM. | Zero citations — the template path does not produce a REFERENCES block at all. | You want deterministic output for testing, fixtures, or any flow where the LLM round-trip is undesirable. CSKB iOS app's offline-mode preview can use this. |
| `generate_grounded_draft(article)` | LLM-assisted, citation-grounded. | Only citations extractable + verifiable from the source article. Empty allow-list → INSUFFICIENT_SOURCE_DATA. | You want publication-grade content for the Central Strength brand. The CSKB iOS app's `drafting` lifecycle step calls this. |

### 11.2 The three None paths

`generate_grounded_draft` can return `None` in three semantically distinct cases. Because the return type doesn't disambiguate them, callers reading the return value alone cannot tell which happened — log lines on stdout describe each. For programmatic disambiguation:

| None path | Programmatic check | Operator action |
|---|---|---|
| **No `ANTHROPIC_API_KEY`** | Call `is_llm_configured()` first; treat False as "skip the LLM path entirely". | Set the env var, retry the same article. |
| **`INSUFFICIENT_SOURCE_DATA`** | Check for the existence of `work/.needs_research/<slug>.json` after the call. If present, the source article had zero extractable citations. | Find a richer source for the topic, or mark the topic as practitioner-only and skip generation. The signal file is gitignored — operational state, not source-controlled. |
| **`DROP`** | Neither check above succeeds. The LLM produced output, but every retry failed allow-list (Layer A) or `verify_citations` (Layer B). | Investigate via the prompt logs. May indicate the source article has citations the LLM can't fit cleanly into a 4-bullet post — try a different source or a different topic framing. |

The three cases are deliberately not collapsed into an exception type or a structured result object. Callers that need fine-grained outcome info can call `is_llm_configured()` and inspect `work/.needs_research/<slug>.json` after the call. This keeps the return type a simple `str | None` and matches the stability shape of `generate_chinese_from_english` — both LLM functions look identical to a consumer reading the signature.

### 11.3 Library wiring for the CSKB job runner

The CSKB iOS app's FastAPI job runner (`api/app/jobs/runner.py` when api-engineer spawns) needs three calls in sequence to implement the v1.1 lifecycle described in `/opt/home/buckcenter.org/hcheng/CentralStrengthKB/docs/ARCHITECTURE.md` §3:

```python
# CSKB api/app/jobs/runner.py (sketch)

from contentprinter import (
    generate_grounded_draft,
    verify_citations,
    is_blocking,
    is_llm_configured,
    refresh_audit_meta,
)

def run_drafting_step(job, article):
    """Lifecycle: scraping → drafting → rendering → verifying → done"""
    if not is_llm_configured():
        job.status = "failed"
        job.reason = "no_api_key"
        return

    draft_text = generate_grounded_draft(article, slug=job.slug)
    if draft_text is None:
        # One of the three None paths — see § 11.2
        signal_path = POSTS_DIR / ".needs_research" / f"{job.slug}.json"
        if signal_path.exists():
            job.status = "failed"
            job.reason = "insufficient_source_data"
        else:
            job.status = "failed"
            job.reason = "drafter_drop"
        return

    (POSTS_DIR / job.slug / "en" / "draft.txt").write_text(draft_text)
    job.status = "drafting_done"

def run_verification_step(job):
    """F-0 gate: every non-OK citation fails the job."""
    refresh_audit_meta(job.slug)
    meta = json.loads((POSTS_DIR / job.slug / "meta.json").read_text())
    if meta["audit_status"] == "BLOCKED":
        job.status = "verification_failed"
        job.failed_citations = meta["audit_issues"]
    elif any(i["severity"] == "VERIFICATION_UNAVAILABLE" for i in meta["audit_issues"]):
        job.status = "verification_pending_review"
    else:
        job.status = "verified"
```

The full v1.1 contract on the consumer side — including `failed_citation_count` / `pending_citation_count` / `verified_citation_count` summary fields, the per-citation `verification.citations[]` shape, and the three remediation endpoints (`/reverify`, `/approve`, `PATCH /draft`) — is documented in `CentralStrengthKB/docs/ARCHITECTURE.md` §3 v1.1. CSKB api-engineer reads both ends of the wire when wiring the lifecycle.

### 11.4 Runtime budget — background-worker only

`generate_grounded_draft` has a wall-clock budget of **30-60 seconds end-to-end**:

- Allow-list extraction: 5-15 seconds (1.5 sec × 1-8 candidate citations through `verify_citations`)
- LLM call: 5-15 seconds (Anthropic API round trip, retried at most twice)
- Layer B re-verification: 5-15 seconds (same per-citation cost as extraction)

This budget is not enforceable from the library side — `llm_client.complete` and `verify_citations` are both synchronous. **Calling `generate_grounded_draft` from a FastAPI request handler will block the event loop for up to a minute.** CSKB's job runner is async by design (POST /v1/generate returns 202 with a job_id, iOS polls for completion), so the budget fits the existing lifecycle. Any future consumer that wants synchronous content generation needs to rethink the architecture, not work around this function.

### 11.5 What this design does not do

- **No automatic fallback to the template path.** If `generate_grounded_draft` returns `None`, it does NOT silently fall back to `generate_draft` — that would re-introduce the un-cited-content problem. Failure is loud and explicit.
- **No "minimum 2 references" pressure.** The retracted editorial rule from `config/content_strategy.md` was the root cause of the hallucination crisis. The grounded drafter accepts 0, 1, or N citations as the source article supports — quality over quantity.
- **No content strategy retconning.** The grounded drafter does not back-fill citations into the 27 hard-blocked posts caught by the #21 audit. That's the #31 remediation territory and uses `refresh_audit_meta` after manual draft edits.
- **No CTA injection, hashtag insertion, or post-processing.** What the LLM emits is what gets written to disk. Brand-voice tuning happens entirely in `config/grounded_drafter_prompt.md`.
