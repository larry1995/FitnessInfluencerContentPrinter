# Drafter Hallucination Root-Cause Investigation

**Date:** 2026-04-12
**Investigator:** backend-writer (Task #30)
**Trigger:** researcher's #21 citation integrity audit found 62 of 164 refs (38%) hallucinated across 31 posts; 27 of 31 posts publication-blocked.
**Status:** investigation only; NO code changes made. Proposed fix below awaits team-lead approval per crisis-pivot directive.

---

## 1. Executive summary

**The ContentPrinter drafter does not produce citations. There is no LLM call in `src/drafter.py` and no code path in this repo that writes a `REFERENCES:` block.**

The 62 fabricated citations were produced **outside the drafter**, by a separate human-in-the-loop "polish" step that:
1. Tells a human operator to open Claude Code
2. Asks them to prompt the LLM to "Polish each caption... Keep the science accurate... Save polished versions back"
3. Points the LLM at `config/content_strategy.md`, which specifies a post template **requiring** a `REFERENCES:` block with "Minimum 2, target 3-5 references" and "DOI links or PMIDs for all journal references"

The LLM, instructed to produce 2-5 DOI-bearing citations to match a template, with **no grounding source material in-context**, generated them by free association from its training data. That is the exact failure mode the audit caught:

- **7 DOI_FABRICATED** — LLM invented plausible-looking DOI strings that don't exist
- **13 DOI_WRONG** — LLM attached a real DOI it "remembered" to a draft claim it doesn't actually support
- **9 DOI_MISATTRIBUTED** ("title theft") — LLM took a real paper's title + DOI and attached a fake author name
- **21 NO_VERIFIABLE_SOURCE** — LLM invented author + year + title from nothing

This pattern is **not a drafter bug**. It is the expected behavior of an LLM asked to fabricate citations against a strict template with no source grounding. The drafter itself never runs the LLM.

**The fix is structural, not local.** See § 5 proposed fix.

---

## 2. Code path audit — where references come from

### 2.1 `src/drafter.py::draft_post_template`

The entire function body is below for reference (paraphrased; actual code at `src/drafter.py:164-270`):

```python
def draft_post_template(article, brand, post_number):
    key_points = extract_key_points(article)        # text mining article full_text
    specific_data = extract_specific_data(article)  # regex-matched dosages/params/tips

    caption_parts = []
    caption_parts.append(f"{topic_emoji} {article['title'].upper()}")
    caption_parts.append(BeautifulSoup(article.get("summary", ""), ...).get_text())

    if key_points:
        caption_parts.append("KEY FINDINGS:")
        for point in key_points[:6]:
            caption_parts.append(f"{i}. {point}")

    if specific_data["dosages"] or specific_data["program_params"]:
        caption_parts.append("DOSAGE & PROTOCOL:" or "PROGRAM DETAILS:")
        for item in items[:4]:
            caption_parts.append(f"- {item}")

    # ... practical_tips, study_findings, CTA, hashtags

    caption = "\n".join(caption_parts)
    post = {"caption": caption, "key_points": ..., "carousel_slides": ..., ...}
    return post
```

**Observations:**

1. **No LLM call.** Pure Python string assembly from regex-extracted text.
2. **No `REFERENCES:` section emitted.** The word "REFERENCES" appears nowhere in `draft_post_template`, `_write_post_file`, `save_drafts`, `generate_carousel_text`, or `suggest_visual`.
3. **PMIDs and DOIs ARE available in `article["structured_content"]`** for PubMed-sourced articles (see `src/pubmed_scraper.py:256-274`), but the drafter **does not read them**. `extract_key_points` only inspects `structured_content["sections"]` and `structured_content["lists"]` — it never touches `structured_content["doi"]`, `["pmid"]`, `["authors"]`, `["journal"]`, or `["year"]`.
4. **RSS-sourced articles (`src/scraper.py`) carry no structured citation data at all.** They only preserve headings, lists, tables, and full-text — no per-paragraph DOI/PMID extraction.
5. The scraped articles contain **unverified inline citations** in `full_text` (e.g. "a 2024 meta-analysis by Helms et al. found..."). These are the author's narrative claims, not machine-readable citation metadata. The drafter's `extract_specific_data` regex for `study_findings` matches lines containing `(study|trial|meta-analysis|research|review)` + a number, but it never extracts the citation — it just dumps the narrative line as `caption_parts`.

**Conclusion for §2.1:** The drafter is a glorified text reformatter. It has zero responsibility for citation content and cannot be the source of the 62 fabricated refs.

### 2.2 `src/main.py::run_polish`

At `src/main.py:100-116`, the `polish` subcommand prints this instruction to the human operator:

```
╔══════════════════════════════════════════════════════════╗
║  POLISH WITH CLAUDE CODE                                 ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  Run this in Claude Code to refine your drafts:          ║
║                                                          ║
║  claude                                                  ║
║  > Read all .txt files in ContentPrinter/Posts/drafts/   ║
║  > Polish each caption for Instagram. Make them punchy,  ║
║  > engaging, and on-brand for Central Strength Gym.      ║
║  > Keep the science accurate. Add line breaks for        ║
║  > readability. Save polished versions back.             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

**Observations:**

1. This is a **manual polish** workflow, not an automated pipeline step. The operator is expected to run Claude Code themselves and prompt it against the drafted files.
2. The prompt does NOT constrain the LLM to use only references present in the source article. It says "Keep the science accurate" — which is aspirational, not enforceable.
3. The prompt does NOT mention `REFERENCES:` at all. The REFERENCES expectation comes from elsewhere.

### 2.3 `config/content_strategy.md`

At lines 172-201, this file defines the required post-format template:

```markdown
### Post Format Template
```
============================================================
POST #XX — [CATEGORY]
Source: [Primary source]
============================================================

CAPTION:
----------------------------------------
[EMOJI] [BOLD HEADLINE IN CAPS]
...
REFERENCES:
1. [Author et al. (Year). Title. Journal. DOI]
2. [Author et al. (Year). Title. Journal. DOI]
[Minimum 2, target 3-5 references]
----------------------------------------
```
```

And at lines 155-159, the "Scientific Rigor" quality guidelines:

> - **Minimum 2 scientific references per post** — prefer peer-reviewed meta-analyses, systematic reviews, and RCTs
> - Cite specific study findings with numbers (effect sizes, percentages, doses) wherever possible
> - Use DOI links or PMIDs for all journal references

And lines 49-149 define all 20 upcoming posts (Post 22 through Post 41) with a **pre-chosen** `Target Sources` field — e.g.:

> ### Post 27 — Powerlifting Programs
> **Target Sources**: Zourdos et al. (2016) RPE scale, Baker et al. (2006) periodization for intermediate athletes, Rhea et al. (2003) dose-response meta-analysis

**Observations:**

1. This file is the **editorial spec** given to the LLM during the `polish` workflow. An operator typing "Polish these drafts" into Claude Code, combined with the editorial context in this file (which Claude Code will read from `config/`), yields an LLM that believes its job is to produce drafts matching the template including a 2-5 item REFERENCES block with DOIs.
2. For posts 22-41, the `Target Sources` field names actual papers (e.g. "Helms et al. (2018) autoregulation in strength training"). Those names are real. **But the LLM is not given the actual papers** — only the author+year+topic hint. When asked to cite them, it fills in title, journal, and DOI from its own memory, which is where the hallucinations enter.
3. For existing posts 1-21, even the `Target Sources` field is absent from the strategy doc. The LLM is asked to cite "at least 2 peer-reviewed meta-analyses" for topics like "vegan creatine" or "sleep recovery" with **zero grounding** — pure free generation.

**This is the hallucination source.** The editorial spec demands 2-5 citations per post; the source material (scraped RSS/PubMed articles) is never passed to the LLM in a form that the LLM can cite from; the LLM does what LLMs do in that situation and confabulates.

### 2.4 `src/chinese_drafter.py` — ruled out

The Chinese drafter calls `llm_client.complete(prompt)` with `{english_draft}` substituted into `config/chinese_prompt_template.md`. The prompt explicitly says "禁止省略参考文献. 英文原文 REFERENCES 里的所有条目必须保留到中文输出" — "do not omit references; all entries from the English REFERENCES block must be preserved in the Chinese output." This means the Chinese drafter **copies** hallucinated English references verbatim into Chinese drafts, but it does not generate new ones. The Chinese drafter is a downstream consumer of the hallucinations, not a source.

### 2.5 Confirmation against a sample audited draft

Examined `Posts/nutrition_vegan_creatine/en/draft.txt` (audited as 3/4 hard-blocked refs). File structure:

- Lines 1-4: header (`POST #1 — NUTRITION`, `Source: BarBend + PubMed Research`, no URL, no `Drafted:` timestamp)
- Lines 6-41: caption in clearly human/LLM-polished narrative English
- Line 43: `REFERENCES:` label
- Lines 44-47: 4 citations, 2 with real-looking DOIs (audited DOI_MISATTRIBUTED), 1 with a real-looking PMID, 1 non-peer-reviewed
- Line 48: closing `---` divider
- Line 50: `SUGGESTED VISUAL: ...`

**This file format does not match `draft_post_template`'s output.** The template-based drafter would produce a file with `Source: X (url)` (with parens + URL), a `Drafted: <iso-timestamp>` line, and a caption starting with `KEY FINDINGS:` — none of which are present. The file was produced by **an LLM polish pass**, not by `draft_post_template`.

**Conclusion for §2:** The hallucinated citations were produced by the `run_polish` manual workflow, acting on the `config/content_strategy.md` template spec, with an LLM that received zero source grounding for the REFERENCES it was asked to produce.

---

## 3. Is the fix to constrain the LLM?

Short answer: **yes, but only as one of three layers.** See § 5 for the full fix. A single-layer fix (e.g. "update the polish prompt to only cite from source articles") would reduce hallucinations from 38% to some lower number but **cannot reach 0%** because:

1. The LLM may still mis-cite a real paper (DOI_WRONG, DOI_MISATTRIBUTED) from source material that lacks DOIs itself.
2. A well-meaning LLM asked to cite "the Jäger 2017 ISSN position stand" will reach into its training memory even if told not to.
3. Human operators will bypass any prompt constraint the first time they want to add a "better" reference.
4. The fix that lives in the prompt has no way to tell the **iOS job runner** "this citation is unverified." The CSKB F-0 gate needs a **structural** verification, not a behavioral request.

The only thing that reaches 0% is **post-generation verification against Crossref/PubMed** — exactly what researcher's `audits/_citation_audit.py` already does. Which is why #27 (`verify_citations`) is the load-bearing fix, not the drafter patch.

---

## 4. Why wasn't this caught earlier?

1. The drafter has no tests for citation correctness.
2. The `polish` workflow is manual and untested. CI never runs it.
3. The `content_strategy.md` template was treated as a design doc, not an LLM prompt — nobody audited whether an LLM fed that template would hallucinate.
4. The existing 31 polished drafts predate the sprint. They were generated in an earlier batch and committed to `Posts/polished/` (now `Posts/<slug>/en/draft.txt`) without any verification gate.
5. `single_page_generator.py` renders them directly. Nothing between "LLM produces refs" and "PNG is rendered to disk" ever checked whether the refs were real.

**This is the "F-0 doesn't exist yet" failure.** The whole reason researcher's #21 audit had to run on historical data is that there's no inline verification step anywhere in the pipeline.

---

## 5. PROPOSED FIX — three layers

**The fix must stop the bleed AND prevent recurrence AND remediate existing drafts.** I propose three layered changes. All three are needed; any one alone leaves a hole.

### Layer 1 — Remove the `polish` workflow entirely. Replace with a grounded LLM drafter path.

**Scope:** `src/drafter.py`, `src/main.py`, `config/content_strategy.md`.

**Change:** The `run_polish` function that prints an "open Claude Code and type this" instruction is deleted. The `polish` subcommand is removed from `main.py`. The `content_strategy.md` template is updated to explicitly say:

> **The REFERENCES block must contain ONLY citations that appear in the scraped source article's `structured_content` or `full_text`. Do NOT generate new references from memory. If the source article has fewer than 2 verifiable citations, the post is incomplete and must be returned to the scraper step.**

In parallel, a new LLM drafter path is added (optional, invoked via `python src/main.py draft --llm`). This path:
1. Reads the full scraped article dict
2. Extracts candidate references from `structured_content["doi"]`, `["pmid"]`, and regex-matched DOI/PMID strings in `full_text`
3. Passes ONLY those extracted references to the LLM as a hard constraint: "You may only cite from this list. Do not invent citations."
4. If the LLM output contains a citation not in the allow-list, the draft is rejected with a clear error

**Risk:** This layer alone still lets a broken LLM mis-quote the allow-list (e.g. swap author names). Layer 3 catches that.

### Layer 2 — Make `contentprinter.verify_citations` the F-0 gate. (Task #27)

**Scope:** `contentprinter/verify.py` (new), `API_SURFACE.md` (update to 0.2.0).

**Change:** Wrap researcher's `audits/_citation_audit.py::audit_draft` as a public library function. CSKB's job runner's `verifying` lifecycle step calls:

```python
from contentprinter import verify_citations, is_blocking

issues = verify_citations(draft_text)
if any(is_blocking(issue.severity) for issue in issues):
    job.status = "verification_failed"
    job.reasons = [issue.to_dict() for issue in issues if is_blocking(issue.severity)]
    return
```

Severities documented in `audits/citation_integrity_2026-04-12.md` — blocking set is `{DOI_FABRICATED, DOI_WRONG, DOI_MISATTRIBUTED, NO_VERIFIABLE_SOURCE, PMID_NOT_FOUND, AUTHOR_WRONG, TITLE_MISMATCH}`. Graceful degrade on Crossref/PubMed unreachable → `VERIFICATION_UNAVAILABLE` severity, which the KB UI can escalate to a human.

**Risk:** Crossref API rate limits. The current audit took ~90s for 164 refs (~1.8s/ref). At iOS app scale, a 5-ref post verifies in ~10s — acceptable as a background job, unacceptable as a request-response API call. Must run async.

### Layer 3 — Publication freeze on existing 27 blocked posts. (Task #29)

**Scope:** `src/audit_meta_writer.py` (new), `src/single_page_generator.py` (update).

**Change:** A new script reads `audits/citation_integrity_2026-04-12.json` and stamps every `Posts/<slug>/meta.json` with:

```json
{
  "audit_status": "OK" | "WARN" | "BLOCKED",
  "audit_date": "2026-04-12",
  "audit_issues": [...],
  "publication_allowed": true | false
}
```

`single_page_generator._discover_topic_drafts` checks `meta.json["publication_allowed"]` and either (a) refuses to render the topic, or (b) renders it with a visible red "AUDIT BLOCKED" overlay that makes it impossible to mistakenly publish. Coordinate with frontend-writer on which behavior is right — my preference is (b) so that the blocked posts are still visible for remediation review, but cannot be silently republished.

**Risk:** Low. This is defensive and idempotent.

---

## 6. What I am asking for

**Team-lead approval to proceed with Layer 2 (#27) and Layer 3 (#29) immediately.** Both are non-destructive and strictly additive.

**Team-lead guidance on Layer 1** before I touch `src/drafter.py`, `src/main.py`, or `config/content_strategy.md`. The Layer 1 change has two failure modes:

1. **Delete too much.** Removing the polish workflow without replacing it means future posts have to be drafted entirely from template output, which is lower quality. The LLM-grounded drafter path needs to land before polish is removed.
2. **Move the hallucination.** If Layer 1 is rushed and the new LLM-grounded path has a subtle allow-list bypass, we just moved the bug.

**Recommended sequencing:**
1. **Today:** Layer 2 (`contentprinter.verify_citations`) + Layer 3 (publication freeze). These stop new bleeding from existing drafts.
2. **This week:** Layer 1 (remove `polish`, update `content_strategy.md` with the grounding constraint). This prevents new drafts from entering a hallucinated state.
3. **Next sprint:** LLM-grounded drafter path (`python src/main.py draft --llm`) as a proper addition, gated by Layer 2 verification on every output before it's saved.

**DO NOT** remediate the 27 blocked posts' citations (#31) until Layer 2 is live — any remediation that goes through the `polish` workflow will just generate new hallucinations, and we'd be fixing bugs with the broken tool that caused them.

---

## 7. Files examined

- `src/drafter.py` (full file)
- `src/main.py` (polish subcommand region)
- `src/pubmed_scraper.py` (lines 90-200 — confirms structured citation data is available but unused)
- `src/scraper.py` (grep confirmed no citation/reference/DOI/PMID handling)
- `src/chinese_drafter.py` (ruled out as source — copies, does not generate)
- `config/content_strategy.md` (full file)
- `config/chinese_prompt_template.md` (confirmed REFERENCES expectation comes via `{english_draft}` substitution, not new generation)
- `Posts/nutrition_vegan_creatine/en/draft.txt` (compared against template output, confirmed non-match)
- `audits/citation_integrity_2026-04-12.md` (researcher's audit — authoritative severity definitions and counts)
- `audits/_citation_audit.py` (referenced for Layer 2 wrapper scope)

## 8. Files NOT modified

**None.** This report is investigation-only per crisis-pivot directive. Holding for team-lead approval before touching any code.
