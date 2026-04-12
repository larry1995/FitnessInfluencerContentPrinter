# ContentPrinter — Public API Surface

**Version:** 0.1.1
**Status:** Stable — see § Stability Promise below.
**Consumers:** CentralStrengthKB iOS app (via its FastAPI backend), any future integrations.

---

## 1. Scope

This document describes the **supported import path** for consuming ContentPrinter as a library. Anything documented here is covered by the stability promise. Anything in `src/*` (the internal pipeline modules) may change without notice — **do not import from `src.*` directly**.

All public functions live under the `contentprinter` package at the repository root. Typical usage:

```python
from contentprinter import (
    generate_draft,
    parse_draft_text,
    generate_chinese_from_english,
    render_page,
    download_references,
    is_llm_configured,
)
```

The package is lightweight (~400 lines of shim code). Under the hood it imports from the internal `src/` modules by prepending `src/` to `sys.path` on first import. Consumers do not need to manage `sys.path` themselves.

---

## 2. Public functions

### `generate_draft(article, *, brand=None, post_number=1) -> Post`

Generate an Instagram post draft dict from a scraped-article dict.

| Arg | Type | Description |
|---|---|---|
| `article` | `dict` | Required. Must contain `title` and `full_text`. Other recognized fields: `topic`, `source`, `url`, `summary`, `structured_content`. Same shape as scraper output under `Posts/raw/*.json`. |
| `brand` | `dict \| None` | Optional override. Defaults to `config/sources.json` brand block. |
| `post_number` | `int` | Sequential post number. Default `1`. |

**Returns:** `Post` dict (see § 3).

**Raises:** `ValueError` if `article` has no title.

**Side effects:** None. Pure function — no network, no file writes. Safe to call from request handlers.

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

Matches the researcher's pre-resolved JSON format in `Posts/training_pdf_urls.json` and `config/upcoming_pdf_urls.json`. Fields:

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

---

## 7. Stability Promise

This API surface is **version 0.1.1**. While we're in 0.x:

- **Function signatures** (name + positional/keyword args + return type) are **frozen** within a minor version. If a signature must change, the minor version bumps and the old signature stays as a compatibility shim for one release.
- **Return dict shapes** may **gain new fields** without a version bump. **Existing fields and their types will not change** without a version bump.
- **Graceful degradation behaviors** (the § 6 list) are frozen — None-returning paths stay None-returning, log-and-continue paths stay log-and-continue.
- **Enumerated string values** (like `layout`, `status`) may **gain new variants** without a version bump; existing values will not be renamed or removed.
- **Exception types are part of the signature.** The concrete exception class raised by each function (`ValueError` for input validation, `OSError` for disk I/O, `FileNotFoundError` as the specific `OSError` subclass for missing paths) is stable within a minor version. A function that currently raises `ValueError` for bad input will not start raising `TypeError` without a minor version bump. Callers may write `except ValueError` with confidence.
- **Documented caller obligations are part of the stability promise.** If this doc says "caller is responsible for deletion" (tempfile fallback in `render_page`), or "callers MUST handle `None`" (`generate_chinese_from_english`), or "append the gym CTA separately" — those obligations will not silently change to "the library handles it". If the library starts auto-handling something, the old obligation-bearing path still works (backward compat), and the new auto-handling is additive.
- **`__version__` bump policy:** the patch component (`0.1.0` → `0.1.1`) bumps when new symbols are added, docstrings are clarified, or internal refactors happen — additive only. The minor component (`0.1.x` → `0.2.0`) bumps when any of the above rules require it: signature change, return-shape field removal/rename, exception-type change, degradation-path change, enum rename/removal, or caller-obligation change. Major (`0.x.y` → `1.0.0`) is reserved for the 1.0 tightening (see below).

At 1.0 the promise tightens: major version bump required for any signature change, and compatibility shims are mandatory for at least one major release.

**Breaking changes since 0.1.0:** *none.* The 0.1.1 bump is additive — added `parse_draft_text` to complete the § 4 consumer flow, tightened § 6 degradation wording for `download_references` return semantics and write-failure behavior, added exception-type / caller-obligation / version-bump clauses to § 7. No existing signatures, return shapes, or degradation paths were changed.

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
- The `Posts/` on-disk directory structure (tracked by `posts_layout.py` helpers, which are internal — if the KB app needs layout introspection, file a task).
- The exact prompt text in `config/chinese_prompt_template.md`. The *voice* is stable; the prompt wording is not.

If you find yourself reaching into `src/*` to get something done, file a task to expose it properly here.

### 9.1 Top-level module leak from `pip install -e .` — DO NOT IMPORT

When this package is installed via `pip install -e .` (or a wheel install), the following module names become importable at the top level of the consumer's Python environment as a pragmatic workaround for the contentprinter shim layer:

```
biorxiv_scraper, chinese_drafter, drafter, forum_scraper, http_utils,
image_generator, llm_client, main, pdf_downloader, pdf_generator,
posts_layout, pubmed_scraper, recursive_discovery, reddit_scraper,
reorganize_posts, scraper, single_page_generator, source_promoter,
youtube_scraper
```

These names exist in the venv namespace because the `contentprinter/*.py` shim modules do bare absolute imports (e.g. `import drafter as _drafter`) that need to resolve in both dev mode and install mode. The cleaner long-term layout collapses these into a private `contentprinter._internal` subpackage — see Task #33 for the planned refactor — but that requires ~25 intra-src import rewrites + a CLI invocation switch from `python src/main.py` to `python -m src.main`, which is a multi-role coordination task scheduled for the 1.0 cleanup pass.

**Consumers MUST NOT import these names directly.** They are NOT part of the public API. They may disappear without a version bump the moment Task #33 lands. Use `from contentprinter import ...` exclusively. If you find yourself writing `import drafter` from a CSKB handler, that is a contract violation and a bug — file a task to expose the symbol you need through the `contentprinter.*` namespace instead.

The leak is not detectable at runtime (the names work), so this section is the only place it is documented. Code-reviewer should grep PRs in any consumer repo for `^(?:from|import) (?:drafter|single_page_generator|pdf_downloader|chinese_drafter|llm_client|http_utils|posts_layout|recursive_discovery|reddit_scraper|forum_scraper|scraper|pubmed_scraper|biorxiv_scraper|youtube_scraper|image_generator|pdf_generator|source_promoter|reorganize_posts|main)\b` and reject any matches.
