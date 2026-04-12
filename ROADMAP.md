# ContentPrinter — Project Roadmap & Agent Instructions

**Last updated:** 2026-04-12
**Working directory:** `/opt/home/buckcenter.org/hcheng/ContentPrinter`
**Audience:** Team agents (project-manager, frontend-writer, backend-writer, code-reviewer, cicd-engineer, researcher) and future contributors.

---

## 1. Project Vision

ContentPrinter is a **recursive content pipeline** that ingests information from Reddit, strength-sport forums, YouTube channels, blog RSS feeds, PubMed, and bioRxiv, then distills it into **high-resolution, Instagram-ready single-page graphics** with captions and citations. The output feeds the social media presence of **Central Strength Gyms** (Santa Clara / Bay Area).

**Primary deliverables per topic:**
1. An English single-page PNG (1080×1350 or 1080×1920) with caption + references.
2. A Chinese-language companion post matching the tone of the YouTuber [Bruce Lu (bruce_lu_1993)](https://www.youtube.com/@bruce_lu_1993): concise, science-grounded, conversational Traditional/Simplified Chinese.
3. Any source PDFs (studies cited for training-method posts) downloaded into a topic subdirectory.
4. A polished text draft (English) archived in `Posts/polished/<topic>/`.

---

## 2. Current Repo Layout (as of 2026-04-12)

```
ContentPrinter/
├── ROADMAP.md                  ← this file
├── requirements.txt
├── powerlifting_research.md    ← background research doc
├── config/
│   ├── config.json
│   ├── content_strategy.md
│   ├── sources.json            ← RSS feeds list
│   └── youtube_sources.json
├── src/
│   ├── main.py                 ← pipeline entrypoint
│   ├── scraper.py              ← generic RSS scraper
│   ├── biorxiv_scraper.py
│   ├── pubmed_scraper.py
│   ├── youtube_scraper.py
│   ├── drafter.py              ← LLM draft generation
│   ├── single_page_generator.py ← PIL image renderer (evidence badge lives here)
│   ├── image_generator.py
│   ├── pdf_generator.py
│   ├── http_utils.py
│   └── __pycache__/
├── Posts/
│   ├── raw/                    ← scraped raw content
│   ├── polished/               ← 31 English post drafts (flat, to be reorganized)
│   ├── single_pages/           ← 31 PNG outputs (flat, to be reorganized)
│   ├── chinese/                ← 31 Chinese post drafts (flat, to be reorganized)
│   ├── pdfs/                   ← combined PDF + (soon) downloaded source PDFs
│   ├── transcripts/            ← YouTube transcripts
│   ├── .seen_hashes.json
│   └── .seen_yt_hashes.json
├── assets/
└── templates/
```

---

## 3. Active Objectives (Sprint: 2026-04-12 →)

### Objective A — Remove "STRONG/WEAK EVIDENCE" header badge
**Owner:** frontend-writer
**Files:** `src/single_page_generator.py`
The evidence-level badge (`extract_evidence_info`, `_draw_evidence_badge`, `BG_EVIDENCE`, and the call sites around lines 434-435, 561-563, 1024+) must be removed from the rendered single-page output. Keep the underlying reference-parsing logic intact — only the visual badge and the text "STRONG EVIDENCE" / "WEAK EVIDENCE" are to be removed from the header area. Regenerate all 31 existing PNGs after the change.

### Objective B — Reorganize Posts/ into per-topic subdirectories
**Owner:** backend-writer
**Target structure:**
```
Posts/
├── <topic_slug>/
│   ├── en/
│   │   ├── draft.txt
│   │   └── single_page.png
│   ├── zh/
│   │   └── draft.txt
│   ├── pdfs/         ← downloaded source PDFs (training-method posts only)
│   └── meta.json     ← source URL, date, tags, references
```
Topic slug examples (derived from existing filenames): `nutrition_vegan_creatine`, `training_hafthor_diet`, `training_bench_mistakes`, `yt_deadlift_accessories`, etc. Write a one-shot migration script in `src/reorganize_posts.py` that moves existing files without losing data. **Idempotent** — safe to re-run.

### Objective C — Download source PDFs for training-method posts
**Owner:** researcher (find) + backend-writer (download)
For every post in `Posts/polished/` that is a **training method** post (topic slug starts with `training_` or references specific programs like Texas Method, 5/3/1, Juggernaut, etc.), parse the references block, resolve DOIs / PubMed IDs to open-access PDFs where possible, and save them to `Posts/<topic_slug>/pdfs/`. Prefer: unpaywall API → PMC OA → bioRxiv → publisher landing page. Record successes/failures in `Posts/<topic_slug>/pdfs/download_log.json`. Never scrape behind paywalls.

### Objective D — Chinese posts matching Bruce Lu style
**Owner:** researcher (style study) + frontend-writer (prompt template) + backend-writer (integrate into drafter)
Reference channel: https://www.youtube.com/@bruce_lu_1993
Bruce Lu's voice: Mainland Simplified Chinese, bodybuilding-scene slang (智商税/避坑/水很深), science-first, no hype, frequent pattern of "研究发现 → 实际意义 → 你该怎么做" (finding → meaning → action). Existing `Posts/chinese/post*.txt` (31 files) are a reasonable baseline but lack his conversational warmth and the signature 锐评 closer. See `config/bruce_lu_style_guide.md` for the authoritative voice study. Tasks:
1. Researcher watches ≥5 recent Bruce Lu videos, extracts tonal markers (opening hooks, transition phrases, closing CTAs) into `config/bruce_lu_style_guide.md`.
2. Frontend-writer drafts an LLM prompt template (`config/chinese_prompt_template.md`) that maps English draft → Bruce-Lu-style Chinese draft.
3. Backend-writer integrates into `drafter.py` so new posts auto-generate both EN and ZH variants into the per-topic subdir.

### Objective E — Recursive scraping expansion
**Owner:** researcher + backend-writer
Extend scrapers to cover:
- Reddit: `r/powerlifting`, `r/weightroom`, `r/StrongerByScience`, `r/Fitness` (top/week via old.reddit.com JSON, no auth needed for public listings).
- Forums: T-Nation, Starting Strength, Reddit-like phpBB strength forums.
- YouTube: expand `config/youtube_sources.json` (Bruce Lu added), use existing `youtube_scraper.py`.
Recursive = each surfaced post's references/links are themselves queued as candidate sources up to depth 2. Implement a visited-set keyed by URL hash to prevent cycles.

---

## 4. Engineering Conventions

- **Python:** 3.10+, requirements pinned in `requirements.txt`.
- **No new top-level dirs** without PM approval — extend existing layout. *(PM-approved exceptions: `tests/` — pytest collection + CI fixtures, added 2026-04-11.)*
- **Idempotent pipelines:** every script re-runnable without duplicating outputs (use `.seen_hashes.json` pattern).
- **PRs:** code-reviewer must sign off before merge. Reviewer checks: (1) no hardcoded absolute paths except the project root constant, (2) `http_utils.py` is used for all outbound HTTP (timeout + retry), (3) new config in `config/`, not inlined.
- **CI/CD:** cicd-engineer owns `.github/workflows/`. Current workflows (set up 2026-04-11):
  - `lint.yml` — runs `ruff check src/` on push/PR to `main` (Python 3.10, pinned `actions/checkout@v4`, `actions/setup-python@v5`).
  - `smoke.yml` — installs `requirements.txt` + `pytest`, imports every pipeline module (`scraper`, `*_scraper`, `drafter`, `*_generator`, `http_utils`), and runs `pytest tests/` if any `test_*.py` files exist. No live network. Fixture-based deeper tests to be added once `tests/fixtures/` exists (coordinated with backend-writer).
  - `artifact.yml` — triggers after a successful `smoke` run (or on `workflow_dispatch`); collects any `Posts/**/*.png` produced and uploads them as a workflow artifact (`contentprinter-pngs`, 14-day retention).
  - `.pre-commit-config.yaml` at repo root pins `ruff` + `black` hooks scoped to `src/*.py` (install locally with `pre-commit install`).
  - `tests/test_imports.py` is the initial smoke test (import every pipeline module).
  - **No scheduled (`cron:`) triggers** — live feeds are rate-limited and expensive; smoke tests must stay fixture-only.
- **Secrets:** any API keys (YouTube Data API, Unpaywall email) live in `.env` which is gitignored. Never commit keys.
- **Commit messages:** `<area>: <imperative verb> <what>` — e.g. `single_page_generator: remove evidence badge from header`.

---

## 5. Team Roles & Hand-off Protocol

| Role | Owns | Hand-off to |
|---|---|---|
| **project-manager** | Task breakdown, priority, merge decisions | all |
| **researcher** | Source discovery, style study, PDF URL resolution | backend-writer, frontend-writer |
| **backend-writer** | Scrapers, drafter, file I/O, reorg scripts | code-reviewer |
| **frontend-writer** | `single_page_generator.py`, image templates, Chinese prompt templates | code-reviewer |
| **code-reviewer** | Review PRs, enforce conventions, run smoke tests | cicd-engineer (for merge-ready) |
| **cicd-engineer** | GitHub Actions, lint, reproducibility, release packaging | project-manager |

**Hand-off rule:** Use `TaskUpdate` to mark completion + set next owner. Use `SendMessage` for short clarifications. Never edit another agent's in-flight files without a message first.

---

## 6. How a Future Agent Should Onboard

1. Read this file end to end.
2. `TaskList` to see current state.
3. Read `config/content_strategy.md` for the editorial voice.
4. Skim 2-3 files in `Posts/polished/` to understand the post format.
5. Look at `src/single_page_generator.py` top comment block — it documents the rendering pipeline.
6. Claim the lowest-ID pending task matching your role, or ask project-manager.

---

## 6.5. Downstream consumer — CentralStrength Knowledgebase

As of 2026-04-12, ContentPrinter is also consumed as a **library** by a new sibling project: **CentralStrengthKB** (`/opt/home/buckcenter.org/hcheng/CentralStrengthKB`). That project wraps this codebase in a FastAPI backend + SwiftUI iOS app for on-demand post generation. Implications for this team:

1. **Public API surface.** A new doc `API_SURFACE.md` (to be written) will list the stable functions CentralStrengthKB imports. Don't break their signatures without a version bump.
2. **Graceful degradation on missing `ANTHROPIC_API_KEY`** is load-bearing — the app will sometimes run without one, and ZH output should return `None` rather than crash. Already implemented in `src/chinese_drafter.py`.
3. **Hardening tasks #14 and #15** (reddit RobotsCache gating, forum allow/blocklist plumbing) must land before the app runs live jobs — the on-demand flow will hit those code paths hard.
4. **Cross-team asks** from CentralStrengthKB arrive tagged `blocks-kb` in our task list.

See `/opt/home/buckcenter.org/hcheng/CentralStrengthKB/ROADMAP.md` for the consumer's own plan.

---

## 7. Out of Scope (for now)

- Auto-posting to Instagram (we generate files; humans upload).
- Paid API scraping (keep it free-tier only).
- Video generation (images + text only).
- Any content outside strength sports / powerlifting / evidence-based fitness.

---

*Questions, ambiguities, or scope changes → message `team-lead` (project-manager).*
