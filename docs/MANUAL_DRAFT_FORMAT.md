# Manual Draft Format

This document describes the format expected by `parse_detailed_content`
(in `src/single_page_generator.py`, exposed as `contentprinter.parse_draft_text`)
so you can write posts by hand without invoking the LLM drafter.

The `singlepage` CLI command will happily consume any hand-written draft
that matches this format — no `ANTHROPIC_API_KEY` required, no PubMed
scrape required, nothing imported from `grounded_drafter`.

---

## File layout

```
work/<slug>/en/draft.txt        ← English caption (required)
work/<slug>/zh/draft.txt        ← Chinese caption (optional, plain text)
work/<slug>/pdfs/<anything>.pdf ← Optional reference PDFs, promoted as-is
work/<slug>/meta.json           ← Optional; safe to omit for manual drafts
```

The slug is the directory name. It is used verbatim by
`output_layout.classify()` to pick a destination category under
`Posts/<category>/`, and the `clean_slug` (category-stripped form) becomes
the final filename. See the `classify()` docstring for the prefix-based
heuristics; prefer slugs like `supplements_creatine_basics`,
`nutrition_protein_timing`, `warmup_mobility_sequence`, etc.

For explicit control, add an entry under `config/categories.json` →
`mapping` that points your slug at a `[category, clean_slug]` pair.

---

## draft.txt structure

A draft has three parts: a header block, a `CAPTION:` block, and a
`REFERENCES:` block. Everything outside these blocks is ignored by the
parser.

### 1. Header (optional, cosmetic)

```
============================================================
POST #99 — SUPPLEMENT
Source: Some attribution you want on the post
Drafted: 2026-04-14
============================================================
```

The `Source:` line is parsed into `post["source"]` and shown in the
PNG header. The rest of the header is ignored by `parse_detailed_content`.

### 2. CAPTION block (required)

The caption is everything between two lines of 10+ dashes. This is the
only block where the parser extracts content for rendering:

```
CAPTION:
----------------------------------------
[EMOJI] [HEADLINE LINE — first non-hashtag, non-empty line becomes the title]

[Opening hook — 1-2 sentences, becomes intro_text, capped at ~800 chars]

1. NUMBERED POINT ONE
Body paragraph. Can span multiple lines until the next numbered point or
an ALL-CAPS section header. Capped at ~600 chars per point.

2. NUMBERED POINT TWO
...

3. NUMBERED POINT THREE
...

PRACTICAL TAKEAWAYS:
- bullet one
- bullet two
- bullet three

THE BOTTOM LINE:
One or two sentence summary. Becomes summary_text.

👉 Save this post and share with a training partner.

#hashtag1 #hashtag2 #hashtag3
----------------------------------------
```

**Required elements for a useful render:**

- At least one non-empty non-hashtag line → becomes the title
- 3–6 numbered points (`1. `, `2. `, …) with short headlines and
  multi-line bodies. Fewer than 3 is allowed but the layout looks
  sparse.

**Optional elements the parser will detect if present:**

- **Intro text** — lines between the title and the first numbered point
  (excluding hashtags and `Book ...` lines). Flows into `intro_text`.
- **Practical guide** — any ALL-CAPS header matching `PRACTICAL ...`,
  `HOW TO ...`, `SAMPLE ...`, `DOSING ...`, `SUPPLEMENTATION ...`,
  `ACTION ...`, `KEY ...`, `WHEN TO ...`, `WHO SHOULD ...`, `WHAT TO ...`,
  `THE PRACTICAL ...`, `WHAT TO LOOK ...`, `WHAT TO AVOID ...`,
  `HOW TO SUPPLEMENT ...`, `HOW TO OPTIMIZE ...`, or `PRO TIP ...`
  followed by a block of `-`, `•`, `→`, `➔`, `➜`, or `‣` bullets.
  Max 12 bullets are rendered.
- **Takeaway arrows** — a block under `THE TAKEAWAY FOR YOU:` or
  `TIPS FOR ...` with `→` bullets is captured as `KEY TAKEAWAYS`.
- **Summary** — `THE BOTTOM LINE:`, `KEY TAKEAWAY:`, `THE TAKEAWAY:`,
  `TAKEAWAY:`, or `SUMMARY:` followed by a block of text. Rendered as
  the footer summary. Capped at ~600 chars.
- **Key stat** — picked up by `extract_key_stat(caption)`; a standout
  number/fact pulled from the caption body. Leave it to the parser,
  don't try to force a specific value.
- **Emoji-prefixed sections** — lines starting with ✅ / ⚠️ / 📊 / 💡 / 🔥
  followed by an `ALL-CAPS HEADER` then a body paragraph become
  `extra_sections` shown as callouts.
- **Evidence info** — `extract_evidence_info()` reads the caption + refs
  and stamps an evidence tier (`strong` / `moderate` / `anecdotal`) in
  the header strip. Driven by ref count + phrasing — no manual markup.

**Layout auto-detection** — the parser infers the layout from content shape:

- `program` — ≥2 `PHASE 1 — NAME` or `WEEK 1 — NAME` headers
- `mythbust` — ≥2 `MYTH: ...` / `FACT: ...` pairs
- `rehab` — ≥3 `STEP N:` sections
- `supplement` — topic is `nutrition`/`supplement` AND caption has
  both `DOSE:` and one of `FORM:` / `TIMING:`
- `default` — anything else

Topic is inferred from the slug filename: slugs containing `nutrition`,
`technique`, `rehab`, or `supplement` get that topic; everything else
falls back to `training`.

### 3. REFERENCES block (optional but strongly recommended)

```
REFERENCES:
1. Forbes SC et al. (2025). Effects of Creatine Supplementation on Upper- and Lower-Body Strength and Power: A Systematic Review and Meta-Analysis. Nutrients, 17(17), 2748. doi:10.3390/nu17172748
2. Candow DG et al. (2024). Effects of Creatine Supplementation and Resistance Training on Muscle Strength Gains in Adults Under 50 Years: A Systematic Review and Meta-Analysis. J Int Soc Sports Nutr, 21(1). PMID:39519498
```

**Hard parser requirements** (from `parse_detailed_content` line ~495 and
`audits/_citation_audit.py::parse_refs_block`):

- The block must start with a line `REFERENCES:` (case-sensitive).
- Each reference must begin with `<digit>.` — e.g. `1. `, `2. `, `10. `.
  Other numbering styles (`[1]`, `(1)`, `1) `) are silently ignored.
- The block ends at end-of-file or at a line of 5+ dashes (`-----`).
- Blank lines inside the block are skipped, not fatal.

**Citation text conventions** the renderer and downstream tools parse:

- **DOI**: include as `doi:10.XXXX/YYY` or `https://doi.org/10.XXXX/YYY`.
  The downstream `_normalize_references` in the CSKB runner and the
  `grounded_drafter._INLINE_DOI` regex both match `10.\d{4,9}/[^\s)\]]+`
  after the `doi:` or `doi.org/` prefix.
- **PMID**: include as `PMID: 12345678` or `PMID:12345678`. Matches
  `PMID[:\s]+(\d{5,9})`.
- Having DOI or PMID is what lets the F-0 verify gate (which runs
  automatically on every `singlepage` — see section below) do a
  round-trip check against Crossref and PubMed. A reference with no
  DOI or PMID lands as `NO_VERIFIABLE_SOURCE`, which is a **blocking**
  severity — the slug will be held by the gate and will not finalize
  until the reference is given a verifiable identifier.

**Canonical citation shape** (matches `_format_citation_text` in
`grounded_drafter.py`):

```
<First Author> et al. (<Year>). <Paper title>. <Journal>. doi:<DOI> PMID:<PMID>
```

You don't have to match this byte-for-byte — the parser is lenient and
just treats each line as a free-text citation — but if you intend to
re-run `verify_citations` on the draft later, this shape gives Crossref
the cleanest signal.

---

## What rendering does and doesn't do without an LLM in the loop

**Does:**

- Parses your hand-written `draft.txt` via `parse_detailed_content` —
  100% deterministic, no network calls, no API keys.
- Renders a single-page Instagram PNG at 3240px wide (3× scale) via
  `render_single_page` / `PIL`. Fonts, layout, accent colors, topic
  badge, evidence tier, author header — all from templates + the parsed
  post dict.
- Combines all rendered pages for the run into one PDF at
  `work/pdfs/all_single_pages.pdf`.
- Finalizes: moves `work/<slug>/en/single_page.png` →
  `Posts/<category>/<clean_slug>.png`. Moves any `work/<slug>/pdfs/*.pdf`
  → `Posts/<category>/pdfs/<clean_slug>_*.pdf`. Converts any
  `work/<slug>/zh/draft.txt` to markdown and writes
  `Posts/<category>/<clean_slug>.zh.md`.

**Does NOT:**

- Call any LLM. The CLI paths `singlepage` and `finalize` never touch
  `llm_client`. No `ANTHROPIC_API_KEY` needed.
- Auto-generate Chinese. If you want a Chinese version of a hand-written
  post, write `work/<slug>/zh/draft.txt` yourself; `finalize_topic` will
  convert it to markdown and copy it to `Posts/`. Running
  `python src/main.py zh` attempts LLM translation and **does** need
  `ANTHROPIC_API_KEY`.
- Scrape anything. The `singlepage` CLI command only reads existing
  `draft.txt` files under `work/`.

**DOES (since task #49, contentprinter 0.5.0):**

- **Run the F-0 verify gate on every rendered draft.** See next
  section — manual drafts are now protected by the same verification
  discipline as LLM-generated drafts.

---

## F-0 citation verification (automatic since 0.5.0)

As of `contentprinter` 0.5.0 the `singlepage` CLI path runs
`contentprinter.run_verify_gate` on every draft immediately after
rendering the PNG. The gate classifies each reference against
Crossref + PubMed and writes one sidecar file per slug:

| Sidecar (under `work/<slug>/`) | Meaning | Finalize behavior |
|---|---|---|
| `_done.json` | all references verified OK | promoted to `Posts/` |
| `_warn.json` | soft flags (`JOURNAL_MISMATCH`, `YEAR_WRONG`, `NOT_PUBMED_INDEXED`, `DOI_UNRESOLVABLE`) or `VERIFICATION_UNAVAILABLE` (network down) | promoted to `Posts/` — review recommended |
| `_blocked.json` | at least one blocking severity (`DOI_FABRICATED`, `DOI_WRONG`, `DOI_MISATTRIBUTED`, `NO_VERIFIABLE_SOURCE`, `PMID_NOT_FOUND`, `AUTHOR_WRONG`, `TITLE_MISMATCH`) | **HELD** — PNG stays in `work/`, never reaches `Posts/` |

Blocked slugs stay in `work/` so you can inspect the PNG, look up the
problem citations in the sidecar JSON, fix them in `draft.txt`, and
re-run `singlepage`. The gate clears any stale sidecar before writing
the new one, so a slug that previously blocked and is now correct will
promote cleanly without manual cleanup.

**Fail-closed discipline:** any severity the classifier doesn't
recognize (e.g. a new audit-module severity shipped in a future
release) is treated as blocking. The gate's routing is byte-identical
to the CSKB job runner's `app/jobs/verify_gate.py::run_verify_gate` —
same classifier protects the CLI and the FastAPI background runner.

**Network cost:** the gate calls Crossref and PubMed once per
reference, roughly 1-2 seconds each. A 5-reference post adds ~10
seconds to `singlepage`; a 20-reference post adds ~40. If Crossref or
PubMed is unreachable, the affected row lands as
`VERIFICATION_UNAVAILABLE` and the slug goes to `_warn.json`, NOT
`_blocked.json` — the gate never blocks on infrastructure failures.

### Escape hatch: `--skip-verify`

If you need to preview a render without running the gate (rapid
iteration on a layout, offline environment, etc.), the `singlepage`
command accepts two **deliberately tedious** flags that must be passed
together:

```bash
python3 src/main.py singlepage --skip-verify --i-know-what-i-am-doing
```

Both flags are required — `--skip-verify` alone prints a warning and
is ignored. When both are set, the gate is bypassed entirely, a
`_skip_verify.json` marker is written into each slug directory, and a
loud `[WARN] F-0 verify gate SKIPPED` banner goes to stderr. Do NOT
publish output produced in this mode to Instagram — the whole point of
the double-flag friction is to keep this path out of normal use.

### Re-running the gate on its own

If you want to re-verify an existing draft without re-rendering the
PNG, either of these works:

```bash
# Option A: call the gate directly
python3 -c "
from contentprinter import run_verify_gate
draft = open('work/<slug>/en/draft.txt').read()
outcome = run_verify_gate(draft, slug='<slug>')
print(outcome['status'], outcome['counts'])
"

# Option B: re-run singlepage (idempotent; overwrites the PNG + sidecar)
python3 src/main.py singlepage
```

---

## Copy-paste template

Save this as `work/<your_slug>/en/draft.txt` and fill in the blanks.
Slug picks category: use `supplements_*`, `nutrition_*`, `training_*`,
`warmup_*`, `cardio_*`, or add an explicit mapping to
`config/categories.json`.

```
============================================================
POST #<N> — <TOPIC>
Source: <attribution, e.g. "Central Strength Gym coaching notes">
Drafted: <YYYY-MM-DD>
============================================================

CAPTION:
----------------------------------------
💪 CREATINE BASICS: WHAT THE DATA ACTUALLY SHOWS

Creatine monohydrate is the most-studied sports supplement on the planet. Here's what 30+ years of research say you should know.

1. IT WORKS — FOR STRENGTH AND POWER
Creatine supplementation reliably increases upper- and lower-body strength, power output, and lean mass when combined with resistance training. The effect size is small-to-moderate but consistent across dozens of trials.

2. MONOHYDRATE IS THE GOLD STANDARD
Despite marketing for "novel" forms (HCl, ethyl ester, buffered), creatine monohydrate remains the most effective and cheapest option. No other form has shown superiority in head-to-head trials.

3. LOADING IS OPTIONAL
You can load with 20g/day for 5-7 days to saturate muscle stores faster, or simply take 3-5g/day and reach saturation in ~28 days. Both paths converge on the same endpoint.

PRACTICAL TAKEAWAYS:
- Take 3-5g/day of creatine monohydrate
- Timing doesn't matter — daily consistency does
- Pair with resistance training for the full effect
- Expect 1-2kg of water weight in the first month

THE BOTTOM LINE:
Creatine is cheap, safe, and effective. If you lift weights and aren't taking it, you're leaving progress on the table.

👉 Save this post and share with a training partner.

#creatine #strengthtraining #sportsnutrition #powerlifting #supplementscience

REFERENCES:
1. Forbes SC et al. (2025). Effects of Creatine Supplementation on Upper- and Lower-Body Strength and Power: A Systematic Review and Meta-Analysis. Nutrients, 17(17), 2748. doi:10.3390/nu17172748
2. Candow DG et al. (2024). Effects of Creatine Supplementation and Resistance Training on Muscle Strength Gains in Adults Under 50 Years: A Systematic Review and Meta-Analysis. J Int Soc Sports Nutr, 21(1). PMID:39519498
----------------------------------------
```

---

## End-to-end workflow recap

```bash
# 1. Write the draft
mkdir -p work/supplements_creatine_basics/en
$EDITOR work/supplements_creatine_basics/en/draft.txt   # paste + edit template

# 2. Render + verify + finalize (one command, F-0 gate runs automatically)
python3 src/main.py singlepage
# → work/supplements_creatine_basics/en/single_page.png
# → work/supplements_creatine_basics/_done.json   (or _warn.json / _blocked.json)
# → Posts/supplements/creatine_basics.png          (if not blocked)

# 3. If any slug blocked, inspect and fix
cat work/supplements_creatine_basics/_blocked.json   # see which refs failed
$EDITOR work/supplements_creatine_basics/en/draft.txt  # correct the citations
python3 src/main.py singlepage                       # re-run — clears old sidecar

# 4. (Optional) Write a Chinese version by hand
$EDITOR work/supplements_creatine_basics/zh/draft.txt
python3 src/main.py finalize
# → Posts/supplements/creatine_basics.zh.md
```

Re-running `singlepage` or `finalize` is idempotent — overwrites the
existing PNG and markdown. Safe to iterate.
