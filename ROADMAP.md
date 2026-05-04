# ContentPrinter — Project Roadmap & Agent Instructions

**Last updated:** 2026-04-12 (post-refactor)
**Working directory:** `/opt/home/buckcenter.org/hcheng/ContentPrinter`
**Audience:** future agents picking up tomorrow or next session.

---

## 0. START HERE — what to do next session

**The code + output layout was refactored on 2026-04-12. Before doing anything, read §2 (new layout) and §3 (next actions) so you don't regenerate stale structure.**

**State at end of 2026-04-12:**
- ✅ 6-category `Posts/` layout live (31 carried-over PNGs + ZH markdowns + 15 reference PDFs)
- ✅ Pipeline code refactored to route internal scratch to `work/`, final output to `Posts/<category>/<clean_slug>.*`
- ✅ 127/127 tests passing
- ✅ `src/output_layout.py` + `config/categories.json` = new finalize layer
- ⏸️ No `ANTHROPIC_API_KEY` yet → grounded drafter + Chinese drafter both return `None` gracefully
- ⏸️ `work/raw/scraped_20260412_134311.json` has 23 fresh articles from end-of-day scrape, not yet drafted/rendered

**What to do first thing tomorrow:**

1. **Read this file end to end.** Then read `config/categories.json` (editorial taxonomy), `src/output_layout.py` (finalize logic), and `API_SURFACE.md` (library contract).
2. **Check if user has provisioned `ANTHROPIC_API_KEY`** in `/opt/home/buckcenter.org/hcheng/ContentPrinter/.env`. If yes → path A. If no → path B.
3. **Path A (API key present):** run the full grounded pipeline end-to-end against the 23 fresh scraped articles:
   ```bash
   python src/main.py draft --llm     # grounded drafter (citation-safe)
   python src/main.py singlepage      # renders to work/ then auto-finalizes into Posts/<category>/
   python src/main.py zh              # Chinese drafter (Bruce-Lu voice)
   python src/main.py sourcepdfs      # download reference PDFs
   ```
4. **Path B (no API key):** use the template drafter (non-LLM, no hallucinations, lower quality but safe):
   ```bash
   python src/main.py draft           # template drafter, no --llm flag
   python src/main.py singlepage      # renders + finalizes
   ```
   Chinese drafts + grounded citations will be skipped gracefully (returns None, logs `[SKIP]`).
5. **Always run `python -m pytest tests/ -q` before committing.** Current baseline: 127 passing.
6. **Do NOT recreate the old `Posts/<slug>/en/draft.txt` layout.** The refactor was explicitly to get rid of it. All drafts/scratch go to `work/`; only finalized outputs go to `Posts/<category>/`.

---

## 1. Project Vision

ContentPrinter is a **recursive content pipeline** that ingests information from Reddit, strength-sport forums, YouTube channels, blog RSS feeds, PubMed, and bioRxiv, then distills it into **high-resolution, Instagram-ready single-page graphics** with captions and citations. The output feeds the social media presence of **Central Strength Gyms** (Santa Clara / Bay Area).

**Primary deliverables per topic:**
1. An English single-page PNG (1080×1350 or 1080×1920) with caption + references.
2. A Chinese-language companion post in markdown format, matching the tone of [Bruce Lu (@bruce_lu_1993)](https://www.youtube.com/@bruce_lu_1993) — concise, science-grounded, Mainland Simplified Chinese with bodybuilding-scene slang.
3. Downloaded reference PDFs for any cited journal papers, stored next to the post in the same category folder.

**Brand:** Central Strength Gyms. Dark brand palette anchored on `#1A1A2E` bg + `#E94560` accent red.

---

## 2. Current Repo Layout (POST-REFACTOR, 2026-04-12)

```
ContentPrinter/
├── ROADMAP.md                  ← this file
├── API_SURFACE.md              ← contentprinter library public contract (v0.3.1)
├── requirements.txt
├── pyproject.toml              ← pip install -e . for the contentprinter package
├── .gitignore                  ← ignores work/ and .env
├── .pre-commit-config.yaml
├── .github/workflows/          ← lint, smoke, artifact CI workflows
│
├── config/
│   ├── categories.json         ← ★ 6-category editorial taxonomy + slug mapping
│   ├── content_strategy.md     ← editorial calendar (Posts 22-41 target sources)
│   ├── sources.json            ← RSS feeds
│   ├── youtube_sources.json    ← YouTube channels (incl. Bruce Lu)
│   ├── bruce_lu_style_guide.md ← Chinese voice reference
│   ├── chinese_prompt_template.md ← LLM prompt for ZH generation
│   ├── grounded_drafter_prompt.md ← LLM prompt for grounded EN drafter
│   ├── reddit_sources.json
│   └── forum_sources.json
│
├── src/                        ← all POSTS_DIR constants now = PROJECT_ROOT / "work"
│   ├── main.py                 ← CLI: scrape/draft/singlepage/zh/sourcepdfs/finalize/...
│   ├── output_layout.py        ← ★ NEW: classify() + finalize_topic() + finalize_all()
│   ├── posts_layout.py         ← slug derivation + meta merge (scratch dir helpers)
│   ├── drafter.py              ← template drafter (no LLM, no hallucinations)
│   ├── grounded_drafter.py     ← grounded LLM drafter (needs ANTHROPIC_API_KEY)
│   ├── chinese_drafter.py      ← Chinese drafter (needs ANTHROPIC_API_KEY)
│   ├── llm_client.py           ← thin Anthropic Messages API client
│   ├── single_page_generator.py ← PIL renderer (reads work/, writes work/, then finalize)
│   ├── text_utils.py           ← strip_emoji helper shared by renderers
│   ├── pdf_downloader.py       ← downloads cited papers from audits/training_pdf_urls.json
│   ├── audit_meta_writer.py    ← citation audit state + refresh_audit_meta(slug)
│   ├── source_promoter.py      ← reddit/forum raw → per-topic draft.txt sidecar
│   ├── scraper.py              ← generic RSS scraper
│   ├── biorxiv_scraper.py
│   ├── pubmed_scraper.py
│   ├── youtube_scraper.py
│   ├── reddit_scraper.py
│   ├── forum_scraper.py
│   ├── recursive_discovery.py  ← visited-set + URL normalization
│   └── http_utils.py
│
├── contentprinter/             ← ★ stable public library surface (v0.3.1)
│   ├── __init__.py             ← exports: generate_draft, generate_grounded_draft,
│   │                             parse_draft_text, render_page, download_references,
│   │                             generate_chinese_from_english, verify_citations,
│   │                             is_blocking, BLOCKING_SEVERITIES, refresh_audit_meta
│   ├── drafter.py              ← thin wrapper around src/drafter
│   ├── grounded_drafter.py     ← thin wrapper around src/grounded_drafter
│   ├── chinese_drafter.py      ← thin wrapper around src/chinese_drafter
│   ├── parser.py               ← parse_draft_text wrapper
│   ├── single_page_generator.py ← render_page wrapper
│   ├── pdf_downloader.py       ← download_references wrapper
│   ├── verify.py               ← verify_citations + is_blocking + BLOCKING_SEVERITIES
│   └── audit.py                ← refresh_audit_meta wrapper (closes #10.5 escape hatch)
│
├── Posts/                      ← ★ FINAL OUTPUT ONLY — 6 categories
│   ├── training_methods/
│   │   ├── <clean_slug>.png    ← Instagram single-page (1080×1350+)
│   │   ├── <clean_slug>.zh.md  ← Chinese markdown
│   │   └── pdfs/
│   │       └── <clean_slug>_refNN.pdf
│   ├── sample_programming/     ← beginner program, Texas Method, PL program
│   ├── nutrition/              ← diet, macros, meal timing, food myths
│   ├── supplements/            ← creatine, caffeine, beta-alanine, omega-3, etc.
│   ├── cardio/                 ← concurrent training, Zone 2
│   └── warmup/                 ← dynamic warmups, prehab
│
├── work/                       ← ★ GITIGNORED, regenerable internal scratch
│   ├── raw/                    ← scraped article JSONs
│   ├── transcripts/            ← YouTube transcripts
│   ├── <slug>/en/draft.txt     ← drafter output (pre-finalize)
│   ├── <slug>/en/single_page.png ← renderer output (pre-finalize)
│   ├── <slug>/zh/draft.txt     ← Chinese drafter output (pre-finalize)
│   ├── <slug>/pdfs/            ← downloaded PDFs (pre-finalize)
│   ├── <slug>/meta.json        ← audit state
│   └── .seen_*.json            ← scraper visited-state
│
├── audits/                     ← research outputs, root-cause investigations
│   ├── _citation_audit.py      ← reusable audit module (imported by verify.py)
│   ├── citation_integrity_2026-04-12.{json,md}  ← the 38% hallucination finding
│   ├── drafter_root_cause_2026-04-12.md         ← run_polish root-cause report
│   ├── grounded_drafter_design.md               ← Layer 1 design doc
│   ├── layer1_smoke_test_plan.md                ← API-key-ready smoke plan
│   ├── training_pdf_urls.json                   ← 68 training-method refs, 18 verified ok
│   └── training_pdf_urls_retry.json             ← re-resolved 11 failures via PMC
│
├── tests/
│   ├── fixtures/               ← recorded scraper inputs for offline smoke tests
│   ├── test_imports.py         ← every src/ module imports cleanly
│   ├── test_verify_citations.py
│   ├── test_audit_meta_writer.py
│   ├── test_grounded_drafter.py
│   ├── test_reddit_scraper.py
│   ├── test_source_promoter.py
│   ├── test_posts_layout.py
│   ├── test_pdf_downloader.py
│   ├── test_library_surface.py
│   └── test_chinese_drafter.py
│
├── assets/
└── templates/
```

**What changed in the 2026-04-12 refactor:**
- `POSTS_DIR = PROJECT_ROOT / "Posts"` → `POSTS_DIR = PROJECT_ROOT / "work"` in 15 `src/*.py` files (name preserved for minimum churn, value routes all scratch to `work/`)
- Deleted `src/reorganize_posts.py` (obsolete; was for the old flat→per-slug migration)
- Added `src/output_layout.py` with `classify()`, `finalize_topic()`, `finalize_all()`, `zh_draft_to_markdown()`
- Added `config/categories.json` with 6-category taxonomy + explicit slug mapping + fallback heuristics
- Added `python src/main.py finalize` subcommand; `singlepage` and `full_pipeline` auto-call it
- Updated `.gitignore` to ignore `work/` (final output under `Posts/` is tracked)
- Updated `src/pdf_downloader.py::URLS_JSON` to point at `audits/training_pdf_urls.json` (moved during the restructure)
- Updated tests (`test_imports.py` removed `reorganize_posts`, `test_reddit_scraper.py` tracks `work/`)
- `Posts/` itself migrated from 31 per-slug dirs to 6 category folders (earlier in the day, via `/tmp/migrate_posts.py` one-shot script — now deleted)

---

## 3. Tomorrow's actionable items

### 3.1 If `ANTHROPIC_API_KEY` is now present

**This is the happy path. Do the full grounded regeneration.**

```bash
cd /opt/home/buckcenter.org/hcheng/ContentPrinter

# Sanity check
python -m pytest tests/ -q                    # expect 127 passing
python src/output_layout.py --dry-run          # show what's currently in Posts/

# If work/raw/ already has fresh scrapes from yesterday's end-of-day run, skip the scrape
ls work/raw/                                   # check for scraped_*.json

# If empty, run a fresh scrape pass (~2 min, hits RSS feeds)
python src/main.py scrape
python src/main.py pubmed
python src/main.py biorxiv
python src/main.py youtube

# Draft via grounded pipeline (the citation-safe path)
python src/main.py draft --llm

# Generate Chinese versions (Bruce Lu voice)
python src/main.py zh

# Download cited PDFs
python src/main.py sourcepdfs

# Render + auto-finalize into Posts/<category>/
python src/main.py singlepage

# Verify the finalize produced the expected output
ls Posts/training_methods/ Posts/nutrition/ Posts/supplements/
cat Posts/supplements/*.zh.md | head -40
```

**Expected outcome:** `Posts/` contains a fresh set of PNGs and `.zh.md` files in the 6-category layout. The number of posts per category depends on what the scrapers surfaced (yesterday's run pulled 23 articles; a fresh run tomorrow will pull a different set).

**Smoke-test plan for the grounded drafter is at `audits/layer1_smoke_test_plan.md`** — backend-writer wrote it yesterday as the specific regeneration playbook. Use it.

### 3.2 If `ANTHROPIC_API_KEY` is still NOT present

**Fallback path: use the template drafter (no LLM, no API key, lower quality but safe).**

```bash
cd /opt/home/buckcenter.org/hcheng/ContentPrinter
python -m pytest tests/ -q                    # sanity

# Use existing work/raw/scraped_20260412_134311.json from yesterday's scrape
python src/main.py draft                      # template drafter, no --llm
python src/main.py singlepage                  # renders + auto-finalizes
```

The template drafter doesn't hallucinate — it does text extraction via regex on the scraped article body. The output is lower-quality than grounded LLM but structurally safe. Use this to validate the pipeline end-to-end while waiting for the user to provision an API key.

### 3.3 If user asks to regenerate content WITHOUT running the pipeline

**Direct-drafting path (Claude in session drafts individual posts via WebFetch + Write):**

The user may ask you to rewrite one or more specific posts without running the scrapers. This was the approach discussed at end of day 2026-04-12. For each post:

1. Identify the original source URL (from `config/content_strategy.md` or by reading the existing `.zh.md` for context)
2. `WebFetch` the source article
3. Extract real citations from the article body (regex for DOIs, PMIDs, paper titles)
4. Verify each citation against Crossref via `WebFetch` to `https://api.crossref.org/works/<DOI>`
5. Draft the post content yourself (you're Claude; you can do this directly)
6. Convert the draft text to `parse_draft_text`-compatible format (see `contentprinter/parser.py`)
7. Call `contentprinter.render_page(post, output_path=Posts/<category>/<clean_slug>.png)`
8. Draft the Chinese version in Bruce Lu voice (reference `config/bruce_lu_style_guide.md`)
9. Write to `Posts/<category>/<clean_slug>.zh.md`

**Why this works without an API key:** you ARE the LLM. The `llm_client.complete()` code path that needs `ANTHROPIC_API_KEY` is for AUTONOMOUS pipelines with no human in the loop. When Claude is directly in the session (via Claude Code), you can draft in the conversation and write files with the Write tool. Your Max 20× subscription covers this.

### 3.4 Deferred work (pending, not urgent)

- **Task #33** — collapse `src/` internals into `contentprinter._internal` namespace. Atomic multi-role refactor, ~1-2 hours. Elevated priority per 2026-04-12 sprint close.
- **Task #34** — editorial policy: prefer OA citations when swaps are available. Low priority.
- **Task #38** — YouTube video generator scope (A: slideshow Reels, B: Bruce-Lu scripted shorts, C: remix). Parked on user scope decision.
- **Task #43** — brighten textRef hex for wider AA margin in CSKB iOS design. Future palette refresh, non-urgent.

---

## 4. Engineering Conventions

- **Python:** 3.10+, requirements pinned in `requirements.txt`.
- **`work/` is scratch.** Anything under `work/` is gitignored and regenerable. Don't rely on it persisting.
- **`Posts/` is output.** Only final renders go here: `<clean_slug>.png`, `<clean_slug>.zh.md`, `pdfs/<clean_slug>_refNN.pdf`. No `draft.txt`, no `meta.json`, no `en/` or `zh/` subfolders. If you find yourself writing a file to `Posts/<slug>/...`, stop — that's the old layout.
- **Categories:** 6 fixed buckets in `config/categories.json`. Adding a new category = edit the config + add a folder. Don't hardcode category names in `src/`.
- **Idempotent pipelines:** every script re-runnable without duplicating outputs (use `.seen_hashes.json` pattern, and `finalize_topic()` is safe to re-call).
- **Commit messages:** `<area>: <imperative verb> <what>`.
- **Secrets:** `.env` at repo root (gitignored). `ANTHROPIC_API_KEY`, `UNPAYWALL_EMAIL`, etc.
- **CI/CD:** `.github/workflows/lint.yml` + `smoke.yml` + `artifact.yml`. No scheduled runs; everything is push/PR triggered.
- **Always run `python -m pytest tests/ -q` before committing.** Current baseline: 127 passing.
- **No new top-level dirs without approval.** Exceptions documented: `tests/`, `audits/`, `work/`, `contentprinter/`.

---

## 5. Citation verification is load-bearing

On 2026-04-12 we caught a 38% hallucination rate in the existing drafts (see `audits/citation_integrity_2026-04-12.md`). Root cause: a deprecated `run_polish` workflow fed drafts to an LLM without source-article grounding, so the LLM confabulated citations from training memory.

**The fix shipped in one sprint:**
- **Layer 1** `contentprinter.generate_grounded_draft` — grounded drafter that extracts citations from the scraped article's `structured_content` + inline DOIs, passes them as a hard allow-list, rejects any LLM output with non-allow-listed refs
- **Layer 2** `contentprinter.verify_citations` + `BLOCKING_SEVERITIES` — F-0 publication gate that catches any residual hallucination via Crossref/PubMed verification
- **Layer 3** `src.audit_meta_writer.refresh_audit_meta` — persists verification state; `contentprinter.refresh_audit_meta` is the public wrapper

**Rules that must not regress:**
- Never ship a draft that contains a citation not in the source article's allow-list
- Never re-enable `run_polish` without a human-in-loop citation check
- `is_blocking()` default must stay `unknown_blocks=True` (over-block on unknown severities for forward-compat)
- `VERIFICATION_UNAVAILABLE` is a THIRD bucket: never collapse it into either `blocked` or `ok`
- When you fix a draft via direct editing, always call `refresh_audit_meta(slug)` or `contentprinter.refresh_audit_meta(slug)` to update the audit state — do NOT manually patch `audit_issues` indices

See `audits/drafter_root_cause_2026-04-12.md` for the full analysis and `audits/grounded_drafter_design.md` for the Layer 1 architecture.

---

## 6. Downstream consumer — CentralStrength Knowledgebase

ContentPrinter is a library dependency for a sibling project: **CentralStrengthKB** at `/opt/home/buckcenter.org/hcheng/CentralStrengthKB`. That project wraps ContentPrinter in a FastAPI backend + SwiftUI iOS app for on-demand staff post generation (see its own `ROADMAP.md`).

**Implications for ContentPrinter work:**
1. **Public API stability:** `API_SURFACE.md` is the contract. Don't break function signatures without a version bump (current: 0.3.1).
2. **Graceful degradation on missing `ANTHROPIC_API_KEY`** is load-bearing — every library function that calls an LLM must return `None` (never raise) when `is_llm_configured()` is False.
3. **The iOS app's Job Detail screen** handles three publication states (`done`, `verification_failed`, `verification_pending_review`). The F-0 gate drives that distinction via `is_blocking()`. See `CentralStrengthKB/docs/ui/screens/job_detail.md`.
4. **Cross-team asks** from CSKB arrive tagged `blocks-kb` in the task list.

CSKB team is not yet spawned — blocked on user decisions (Apple Developer Program, Anthropic API key). When spawned, the first task is `CentralStrengthKB/docs/ARCHITECTURE.md` §3 v1.1 implementation.

---

## 7. Out of scope (unless user explicitly asks)

- Auto-posting to Instagram (we generate files; humans upload).
- Paid API scraping (keep it free-tier only).
- Video generation (#38 is parked pending user scope decision).
- Content outside strength sports / powerlifting / evidence-based fitness.
- Any rebuild of the 31 historical hallucinated posts from the old sprint. They're in `Posts/<category>/<clean_slug>.png` from the 2026-04-12 migration; treat as legacy until a fresh generation overwrites them.

---

## 8. How a future agent should onboard

1. Read this file end-to-end (especially §0, §2, §3).
2. `python -m pytest tests/ -q` → confirm baseline 127 passing.
3. Check `.env` for `ANTHROPIC_API_KEY` to decide Path A or Path B in §3.
4. Read `API_SURFACE.md` for the library contract.
5. Read `audits/layer1_smoke_test_plan.md` for the regeneration playbook.
6. Read `audits/citation_integrity_2026-04-12.md` for the hallucination context and why the fix layers matter.
7. Look at 2-3 files in `Posts/supplements/` to understand what the final output looks like (both `.png` and `.zh.md`).
8. Check `TaskList` if it exists; if not, this ROADMAP is the source of truth.

**If you're about to write a file to `Posts/<something>/en/draft.txt` or `Posts/<something>/meta.json`, STOP.** That's the old layout. Drafts and meta go to `work/`, final outputs go to `Posts/<category>/<clean_slug>.*`.

---

*Questions → leave a note at the top of this file with `[2026-MM-DD]` prefix; the next agent will see it.*
