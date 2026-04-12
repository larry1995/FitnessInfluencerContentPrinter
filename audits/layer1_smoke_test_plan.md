# Layer 1 Grounded Drafter — Smoke Test Plan

**Date:** 2026-04-12
**Status:** OPTIONAL — pure standby plan, not blocking. Executes the moment `ANTHROPIC_API_KEY` is provisioned.
**Author:** backend-writer (post-#35 idle work, per team-lead instruction)
**Companion:** `audits/grounded_drafter_design.md` (the contract this plan validates).

---

## 1. Goal

Validate that `generate_grounded_draft(article)` produces publication-grade drafts against three currently-clean posts (`nutrition_fat_myth`, `supplements_beta_alanine`, `training_hafthor_diet`), and fails loudly in the right ways when given degenerate input. The smoke test is **end-to-end** — it exercises the LLM round-trip, not just the offline graceful-degradation path the unit tests cover.

**Why these three posts:** they are the 3 of 31 in the publication-freeze cohort that survived researcher's #21 audit with `audit_status: "OK"` and zero blocking issues. Every other post is BLOCKED or WARN, so re-drafting them via the grounded path would make remediation comparisons noisy. The clean cohort gives a clean baseline: if the grounded drafter produces output that re-verifies clean against the same source article, that's evidence the new path is at least as safe as the old (audited) one.

**Non-goal:** prove the grounded drafter produces *better* prose than the existing drafts. Editorial quality is human-eyeball territory; this plan only validates citation correctness and pipeline plumbing.

---

## 2. Pre-flight checklist

Before running the plan, verify:

1. **API key configured.** `python3 -c "from contentprinter import is_llm_configured; print(is_llm_configured())"` prints `True`.
2. **Test suite green.** `pytest tests/ -q` returns 124 passed (or higher if newer tests have landed).
3. **Network reachable.** `curl -s https://api.crossref.org/works/10.3390/nu17172748 | head -c 100` returns JSON (not an error). Both Crossref and api.anthropic.com need to be reachable from the test machine.
4. **Posts/.needs_research/ does not pre-exist** (or is empty). The smoke test should not write into it on the happy path; pre-existing content would mask a regression.
5. **Recent raw scrape on disk.** `ls Posts/raw/scraped_*.json` shows at least one file. The hafthor case relies on the existing `scraped_20260402_144744.json` raw entry.

If any precondition fails, **stop**. The smoke test depends on these and skipping them silently is the kind of "it ran but didn't actually verify anything" failure mode the F-0 gate exists to prevent.

---

## 3. Per-post test cases

### 3.1 `training_hafthor_diet` — RSS source with structured-content allow-list

**Source article:** `Posts/raw/scraped_20260402_144744.json` entry titled "Fueling the Future Deadlift World Record: Hafthor Björnsson's 8,000-Calorie Diet" (BarBend, `https://barbend.com/news/hafthor-bjornsson-8000-calorie-diet/`).

**Source type:** RSS (no `structured_content` block — BarBend articles don't ship one). Allow-list extraction will go through Source 2 (inline DOI scan) and Source 3 (inline PMID scan), not Source 1.

**Expected behavior:**
- `extract_allowed_citations(article)` returns either an empty list (if BarBend's article body has no inline DOIs), OR a small list of inline-DOI matches that survive `verify_citations`.
- If empty: function returns `None`, `Posts/.needs_research/training_hafthor_diet.json` is written, **the post is NOT regenerated**. This is a VALID outcome — see §4 below for how to interpret it.
- If non-empty: LLM call produces a draft, Layer A and Layer B both pass, the draft is saved, `refresh_audit_meta` stamps it `OK`.

**Comparison criterion:**
- The current `meta.json` lists 4 references (Helms 2014, Jäger 2017, Iraki 2019, Morton 2018) — researcher back-filled these during the #21 audit because the original drafter output was hallucinated AND fixed by hand. They are NOT in BarBend's article body.
- If the grounded drafter produces 0 references (empty allow-list), that is **expected and correct**: BarBend articles typically don't carry verified inline DOIs.
- The current 4-reference state is the post-remediation baseline, not what the grounded drafter should reproduce. The grounded path's output for hafthor will likely be 0 references with the `[INSUFFICIENT_SOURCE_DATA]` marker, and a `.needs_research` signal file. **That is the right answer for an RSS source without inline DOIs.**

**Run command:**
```bash
python3 -c "
import sys, json
sys.path.insert(0, 'src')
sys.path.insert(0, '.')
from grounded_drafter import generate_grounded_draft

raw = json.loads(open('Posts/raw/scraped_20260402_144744.json').read())
article = next(a for a in raw if 'hafthor' in a['title'].lower())
result = generate_grounded_draft(article, slug='training_hafthor_diet_smoke')
print('---')
print('result is None:', result is None)
if result is not None:
    print(result[:500])
"
```

**Pass criteria:**
- Either `result is None` AND `Posts/.needs_research/training_hafthor_diet_smoke.json` exists with `extraction_breakdown.inline_doi_matches >= 0`,
- OR `result` is a non-empty draft text containing `REFERENCES:` and at least one numbered ref, AND `verify_citations(result)` returns zero blocking severities.

**Fail signals:**
- Function raises an exception.
- Function returns a draft with hallucinated refs (refs not in `extract_allowed_citations(article)`).
- `Posts/.needs_research/training_hafthor_diet_smoke.json` is written but the article has obvious DOIs in the body (verify by hand: `grep -oE "10\.[0-9]+/[^ )]+" <<< "$(jq .full_text < scraped_*.json)"`).

### 3.2 `supplements_beta_alanine` — Synthetic PubMed-shaped article

**Why synthetic:** the meta.json's `source_url` is empty (this post was back-filled by researcher from an "ISSN Position Stand + PubMed Meta-Analyses" composite source, not a single scrape). There is no raw article on disk to feed to the grounded drafter.

**The fix:** construct an article dict matching one of the 5 references in the current meta.json — e.g. Saunders 2017 (`doi:10.1136/bjsports-2016-096396`, the BJSM systematic review) — and exercise Source 1 (PubMed structured) extraction against it. This synthetic flow validates the structured-content branch end-to-end with a real DOI on a real journal.

**Synthetic article shape:**
```python
article = {
    "title": "Beta-alanine supplementation to improve exercise capacity and performance: a systematic review and meta-analysis",
    "url": "https://pubmed.ncbi.nlm.nih.gov/27797728/",
    "source": "PubMed (Br J Sports Med)",
    "source_type": "pubmed",
    "topic": "supplements",
    "structured_content": {
        "pmid": "27797728",
        "doi": "10.1136/bjsports-2016-096396",
        "authors": ["Saunders B", "Elliott-Sale K", "Artioli GG"],
        "journal": "Br J Sports Med",
        "year": "2017",
    },
    "full_text": (
        "Beta-alanine supplementation increases muscle carnosine and improves "
        "high-intensity exercise performance. This systematic review pooled "
        "40 studies (n=1461) and found small-to-moderate ergogenic effects "
        "for exercise tasks lasting 30 seconds to 10 minutes."
    ),
}
```

**Expected behavior:**
- Allow-list extraction yields 1 entry (the synthetic article itself, via Source 1).
- LLM call produces a draft with at least 1 reference, byte-equivalent to the Source 1 citation.
- Layer A passes, Layer B passes (the DOI resolves through Crossref).
- Draft saved to `Posts/supplements_beta_alanine_smoke/en/draft.txt`.

**Pass criteria:**
- `result is not None`.
- `len(extract_allowed_citations(article)) == 1`.
- `result` contains `doi:10.1136/bjsports-2016-096396` byte-for-byte.
- `verify_citations(result)` returns one row with `severity == "OK"`.
- `Posts/supplements_beta_alanine_smoke/meta.json` has `audit_status: "OK"`, `publication_allowed: true`, empty `audit_issues`.

**Fail signals:**
- Empty allow-list (Source 1 extraction is broken).
- Draft contains a citation that's NOT byte-equivalent to the Saunders 2017 line (LLM ignored the constraint OR Layer A let it through).
- `verify_citations(result)` returns any blocking severity.

### 3.3 `nutrition_fat_myth` — Multi-citation synthetic + Layer A stress test

**Why this case:** the current meta.json lists 5 references (Hall 2015, Ge 2020, Whittaker 2021, Aragon 2017, Helms 2014) — all PubMed-indexed with valid DOIs. This is the closest we get to a "rich-citation article" matching design doc §7.1. But again, no raw source on disk, so synthetic.

**Synthetic strategy:** instead of feeding all 5 citations as Source 1 (which would only test the trivial "1 article = 1 citation" case 5 times), we feed the article as ONE structured-content paper plus an `full_text` body containing the OTHER 4 DOIs as inline references. This exercises Source 1 + Source 2 + dedup + the cap-at-8 logic in one shot.

**Synthetic article shape:**
```python
article = {
    "title": "Calorie for calorie, dietary fat restriction results in more body fat loss than carbohydrate restriction in people with obesity",
    "url": "https://pubmed.ncbi.nlm.nih.gov/26278052/",
    "source": "PubMed (Cell Metab)",
    "source_type": "pubmed",
    "topic": "nutrition",
    "structured_content": {
        "pmid": "26278052",
        "doi": "10.1016/j.cmet.2015.07.021",
        "authors": ["Hall KD", "Bemis T", "Brychta R"],
        "journal": "Cell Metab",
        "year": "2015",
    },
    "full_text": (
        "This 6-day metabolic ward study compared isocaloric reduced-fat vs "
        "reduced-carb diets in obese adults. Related work: a systematic review "
        "and meta-analysis (doi:10.1136/bmj.m696) compared 14 popular diets and "
        "found minimal weight-loss differences at 12 months. The ISSN position "
        "stand on diets and body composition (doi:10.1186/s12970-017-0174-y) "
        "endorses flexible dieting. For testosterone effects, see Whittaker & Wu "
        "2021 (doi:10.1016/j.jsbmb.2021.105878). Helms et al. 2014 evidence-based "
        "recommendations for natural bodybuilding (doi:10.1186/1550-2783-11-20)."
    ),
}
```

**Expected behavior:**
- Source 1 yields 1 entry (Hall 2015).
- Source 2 (inline DOIs) finds 4 candidates → all 4 verify against Crossref → 4 entries added.
- Allow-list total: 5 entries after dedup. (Hall is in Source 1 already; the other 4 are new.)
- LLM produces a draft using some or all of the 5 allow-list entries.
- Layer A passes (every emitted ref is byte-equivalent to an allow-list entry).
- Layer B passes (Crossref re-verification clean).

**Pass criteria:**
- `len(extract_allowed_citations(article)) == 5`.
- All 5 expected DOIs present in the allow-list (verify by `set(c['doi'] for c in allowed)` matching `{10.1016/j.cmet.2015.07.021, 10.1136/bmj.m696, 10.1186/s12970-017-0174-y, 10.1016/j.jsbmb.2021.105878, 10.1186/1550-2783-11-20}`).
- `result is not None`.
- `verify_citations(result)` returns zero blocking severities.

**Fail signals:**
- Allow-list is shorter than 5 (Source 2 inline-DOI extraction missed candidates OR Crossref verification rejected legitimate DOIs).
- Allow-list contains DOIs that aren't in the expected set (regex over-matched something else in the body).
- Draft contains a ref not in the 5-element allow-list.

---

## 4. Interpreting outcomes

### 4.1 What "success" looks like (overall)

| Post | Allow-list size | LLM result | meta.json after |
|---|---|---|---|
| training_hafthor_diet | 0 (most likely) | None + signal file | unchanged |
| supplements_beta_alanine | 1 (Source 1) | non-None draft, 1 ref | `audit_status: OK` |
| nutrition_fat_myth | 5 (Source 1 + 4 Source 2) | non-None draft, 1-5 refs | `audit_status: OK` |

If all three post-test results match the table above, **the grounded drafter is end-to-end functional** and #31 remediation can proceed through it.

### 4.2 What the first DROP case would mean

If any of the three returns `None` for a reason OTHER than INSUFFICIENT_SOURCE_DATA (i.e. allow-list was non-empty and LLM ran but every retry failed Layer A or Layer B), that's a **prompt iteration signal**, not a code bug. Possible interpretations in priority order:

1. **LLM is reliably ignoring the allow-list constraint** — the prompt's CRITICAL SAFETY RULE is too soft, or the LLM is pattern-matching against the editorial spec ("minimum 2 references" etc.) from its training data despite the prompt saying otherwise. Action: tighten the prompt's hard-rules section, possibly add an example of REJECTED output to the prompt body. Re-run.
2. **LLM is byte-mangling the allow-list citations** — emitting `Forbes SC. (2025)` instead of `Forbes SC et al. (2025)`, or capitalizing differently, or wrapping in markdown. Action: extend `_all_refs_in_allowlist` to normalize whitespace + case before comparison, OR add a "do not modify any character" hard rule to the prompt.
3. **Layer B is failing on a Crossref hiccup that Layer A passed** — the allow-list citation was extracted from a working Crossref response during extraction, but the post-LLM re-verification got a 5xx or rate limit. Action: this should have been normalized to VERIFICATION_UNAVAILABLE by #36's network-failure leak fix; if it wasn't, check the audit module's error message format and extend the substring list.
4. **The article body's full_text is too long and the LLM is getting confused** — the `_excerpt` truncation rule should cap at 4000 chars but maybe a particular article slips through. Action: add length logging to the prompt builder, verify the cap is applied.

**None of these mean "the grounded drafter is fundamentally broken".** The retry-then-drop loop is doing its job — it caught a problem and refused to ship hallucinated content. That's the correct safe-direction failure. The question after a DROP is "what about the prompt or the LLM behavior needs to change", not "should we go back to the template path".

### 4.3 What an INSUFFICIENT_SOURCE_DATA on hafthor would mean

If `training_hafthor_diet` returns `None` with a signal file showing `inline_doi_matches: 0`, that confirms the design doc §7.3 prediction: practitioner-voiced sources (BarBend, T-Nation) don't carry verifiable inline citations and the grounded drafter correctly refuses to fabricate. The signal file becomes the operator's job: find a richer source for the topic, or mark it as a coach's-notes category and exclude from auto-drafting.

This is the **expected outcome** for hafthor and is not a regression. Researcher manually back-filled the current 4 references during the #21 audit; the grounded drafter has no way to reproduce that human-curated work from the BarBend article alone.

---

## 5. Cleanup after the smoke test

The smoke test creates synthetic slugs (`training_hafthor_diet_smoke`, `supplements_beta_alanine_smoke`, `nutrition_fat_myth_smoke`) so the real `Posts/<slug>/` directories are not touched. After running, clean up:

```bash
rm -rf Posts/training_hafthor_diet_smoke Posts/supplements_beta_alanine_smoke Posts/nutrition_fat_myth_smoke
rm -f Posts/.needs_research/training_hafthor_diet_smoke.json
```

Do NOT delete `Posts/.needs_research/` itself — it's gitignored and may be load-bearing for future #31 remediation operator triage.

---

## 6. What this plan does NOT cover

- **Editorial quality of LLM output.** Human eyeball, not in scope.
- **Prompt iteration after a DROP.** Filed as a separate concern in §4.2 — the smoke test surfaces the problem but doesn't fix it.
- **Performance / cost.** Each smoke test consumes ~3-5 LLM calls (3 posts × ~1.5 attempts each, mostly first-try passes). Budget ~$0.50 per smoke run at current Opus pricing. Negligible.
- **Multi-language path (`generate_chinese_from_english`).** Layer 1 is English-only. Once the grounded English drafter is validated, the Chinese drafter can consume its output without changes — that's a separate smoke run (Task #5 territory, blocked on the same API key).
- **Remediation of the 27 BLOCKED posts.** That's #31, which uses the grounded drafter as its tool. This plan validates the tool; #31 validates the workflow.

---

## 7. Execution checklist (one-shot)

When the API key lands, run this in order:

1. `export ANTHROPIC_API_KEY=...` (or write to `.env`)
2. `python3 -c "from contentprinter import is_llm_configured; print(is_llm_configured())"` → expect `True`
3. `pytest tests/ -q` → expect `124 passed`
4. Run the 3 per-post smoke commands from §3 (in order: hafthor, beta-alanine, fat-myth)
5. Inspect output:
   - hafthor: signal file exists OR draft has zero blocking issues
   - beta-alanine: 1-ref draft, audit_status OK
   - fat-myth: 1-5 ref draft, audit_status OK
6. Run cleanup from §5
7. Report results (pass/fail per post + LLM call count + any DROPs) back to team-lead

Total wall time: **~5 minutes** (3 LLM calls × ~30 seconds + 1 minute setup/cleanup).

If any post DROPs, do NOT iterate the prompt yourself — surface the DROP to team-lead with the LLM output captured for review. Prompt iteration is a design-doc-level change requiring approval, not a code-level fix.
