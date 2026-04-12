# Grounded LLM Drafter — Design Document

**Date:** 2026-04-12
**Author:** backend-writer (Task #35, Layer 1 of the citation-hallucination crisis fix)
**Status:** DESIGN ONLY. No code changes to `src/drafter.py`, `src/main.py`, or `config/content_strategy.md`. Awaits team-lead review before any Python is touched.
**Companion docs:** `audits/drafter_root_cause_2026-04-12.md` (#30 investigation), `audits/citation_integrity_2026-04-12.md` (#21 audit), `API_SURFACE.md` §10 (citation verification gate).

---

## 1. Goal

Replace the current hallucinating `run_polish` workflow (deprecated, not deleted) with a **grounded LLM drafter** that produces draft.txt files whose `REFERENCES:` blocks contain **only** citations extractable from the scraped source article. Zero hallucinated citations at the drafter output boundary, validated by `contentprinter.verify_citations` before the draft is saved.

**Success criterion:** running the new grounded drafter against any of the 31 existing scraped articles, then immediately running `verify_citations` on the output, produces a row list with **zero** entries in `BLOCKING_SEVERITIES`. The drafter is allowed to fail loudly (refuse to produce a draft, return an error code) when the source article has insufficient citations to meet the minimum threshold — that is the correct behavior, not a regression.

**Non-goals:**
- Replacing the template-based `draft_post_template` for callers that want pure-Python text mining (e.g. CSKB's `generate_draft(article)` library entry point). The grounded LLM path is **additive**, invoked via a new `--llm` flag on `main.py draft` and a new library function `generate_grounded_draft(article)`.
- Fixing the historical 27 BLOCKED posts. That's #31's remediation territory.
- Changing the LLM model or vendor. Continues to use `llm_client.complete` against `claude-opus-4-6`.

## 2. The hallucination root cause, in one sentence

The current `run_polish` workflow gives the LLM a draft caption + the editorial spec at `config/content_strategy.md` (which mandates "minimum 2, target 3-5 references with DOI/PMID") **without ever passing the LLM the source article's actual citation metadata**. The LLM, told to produce 2-5 DOI-bearing citations from no source material, confabulates from training memory. (Full analysis: #30 investigation report.)

**The fix is to ground the LLM**: extract real citations from the scraped article into an explicit allow-list, pass the allow-list to the LLM as a hard constraint ("you may only cite from this list, do not invent citations"), and reject any LLM output that contains a non-allow-listed citation. Then verify the output through `contentprinter.verify_citations` as a defense-in-depth check.

## 3. Allow-list extraction

The grounded drafter's first step is to build an `AllowedCitations` list from the scraped article. The list contains zero or more `Citation` records, each fully verified at scrape time. **The LLM is allowed to cite ONLY from this list. Any citation in the LLM output that is not byte-equivalent to an allow-list entry is rejected.**

### 3.1 Citation record shape

```python
class Citation(TypedDict):
    citation_text: str    # canonical formatted citation, ready to drop into REFERENCES block
    doi: str | None       # 10.xxxx/yyyy form, no URL prefix
    pmid: str | None      # numeric string, e.g. "39519498"
    first_author: str
    year: int
    journal: str | None
    title: str
    source: str           # provenance: "pubmed_scraper" | "rss_structured" | "rss_inline_doi" | "rss_inline_pmid"
```

### 3.2 Extraction sources, in priority order

The scraped article dict (`article: dict`) has three places where verified citation metadata can live. The grounded drafter walks them in priority order and dedupes by DOI/PMID:

**Source 1 — `article["structured_content"]` (PubMed-sourced articles):**

`src/pubmed_scraper.py:256-274` populates this with verified-against-NCBI fields:
```python
"structured_content": {
    "pmid": "39519498",
    "authors": ["Candow DG", "Forbes SC", ...],
    "journal": "Journal of the International Society of Sports Nutrition",
    "year": "2024",
    "doi": "10.1186/s12970-024-00750-4",
    "mesh_terms": [...],
}
```

These are 100% trustworthy — they come from NCBI E-utilities at scrape time. The grounded drafter reads `pmid`, `authors[0]`, `journal`, `year`, `doi`, plus the article's own `title` field, and constructs one `Citation` record. **This is the cleanest source and the highest-priority.**

**Source 2 — Regex-matched DOIs in `article["full_text"]` (RSS articles with inline DOI references):**

RSS-scraped articles (`src/scraper.py`) don't carry structured citation metadata, but the article body sometimes contains inline DOIs that the author embedded — e.g. "...as Helms et al. (2018) showed (doi:10.1519/JSC.0000000000002491)..." The grounded drafter scans `article["full_text"]` with the regex:

```python
_INLINE_DOI = re.compile(
    r"(?:doi[:\s]*|doi\.org/|dx\.doi\.org/)(10\.\d{4,9}/[^\s)\]]+?)(?:[\s).,;\]]|$)",
    re.IGNORECASE,
)
```

For each match, the drafter calls `contentprinter.verify_citations` (Layer 2, #27) on a synthetic single-ref draft to verify the DOI resolves and is real. **If verification returns `OK`, the resolved Crossref record (author, year, journal, title) becomes a `Citation` record.** If verification returns any blocking severity, the inline DOI is dropped from the allow-list — we don't trust author-typed DOIs without independent verification.

This is slower than Source 1 (one Crossref roundtrip per match) but gives the grounded drafter access to citations the article author embedded inline rather than separately structured.

**Source 3 — Regex-matched PMIDs in `article["full_text"]`:**

Same pattern as Source 2 but for `PMID:NNNNNNNN` strings. Verified through PubMed esummary instead of Crossref. Same accept-only-OK rule.

```python
_INLINE_PMID = re.compile(r"PMID[:\s]+(\d{5,9})", re.IGNORECASE)
```

**Sources NOT used:**
- `article["summary"]` — RSS feed summaries are author-edited blurbs and don't reliably contain citations.
- `config/content_strategy.md` "Target Sources" hints — these are author-name+year guesses (e.g. "Helms et al. 2018"), not full citations. Letting the LLM resolve them itself reintroduces the hallucination path. If the editorial calendar wants a specific paper cited, the scraper should include it in the source URL.
- The drafter's existing `extract_specific_data` `study_findings` regex matches — these are narrative claims about studies, not parseable citations.

### 3.3 Deduplication

Multiple sources can surface the same paper (e.g. PubMed structured + an inline DOI in the body that points at the same paper). The drafter dedupes by `(doi, pmid)` tuple, preferring Source 1 (PubMed structured) over Source 2 (inline DOI) over Source 3 (inline PMID), since Source 1 carries more fields (`mesh_terms`, full author list).

### 3.4 Edge cases

- **Empty allow-list**: the drafter returns `None` and emits a clear log line: `[INSUFFICIENT_SOURCE_DATA] {slug}: scraped article has no extractable citations`. This is a **valid outcome** — see §6 for the behavior contract.
- **One-citation allow-list**: the drafter proceeds with a 1-citation post. The editorial spec's "minimum 2 references" rule is **dropped** for the grounded path because that rule is exactly what creates hallucination pressure. A 1-citation post is honest; a 2-citation post with one fabrication is not.
- **Allow-list larger than 8 citations**: the drafter caps at 8 (the maximum the post template can render cleanly per `single_page_generator.py` width constraints) and prefers Source-1 entries first.
- **Citation with missing fields**: a `Citation` record requires `first_author`, `year`, `title` at minimum. Records lacking any of these are dropped from the allow-list (we can't form a valid REFERENCES line without them).

## 4. The LLM prompt template

A new file `config/grounded_drafter_prompt.md` will hold the prompt template, mirroring how `config/chinese_prompt_template.md` is structured for the Chinese drafter. The prompt is loaded at runtime, the placeholders are substituted, and the result is sent to `llm_client.complete()`.

### 4.1 Prompt template (full text)

```
<<<PROMPT_START>>>
You are an Instagram content writer for Central Strength Gym, a powerlifting-focused gym in Santa Clara, CA. Your job is to write a single Instagram post draft based on a scraped source article. The post will be reviewed by a human before publication.

# CRITICAL SAFETY RULE — citations

**You may cite ONLY from the verified citation list below.** Do not generate any citation that is not byte-equivalent to one of the entries in this list. Do not paraphrase a citation, do not "remember" a related paper, do not invent a DOI, do not adjust an author name, do not add a citation from your training data even if you are confident it is real.

If the verified citation list is empty or contains fewer references than you would normally use, **the post is allowed to have fewer citations**. A post with 1 honest citation is better than a post with 5 fabricated ones. A post with 0 citations and a `REFERENCES: [INSUFFICIENT_SOURCE_DATA]` marker is better than a post with any fabrication.

**Verified citation list (the ONLY citations you may use):**

{allowed_citations_block}

# Source article

The article that gave rise to this post:

Title: {article_title}
Source: {article_source}
URL: {article_url}

Body (truncated to 4000 chars at the nearest paragraph boundary if longer):
{article_body_excerpt}

# Post format

Produce a single Instagram caption following this format exactly:

```
[EMOJI] [BOLD HEADLINE IN CAPS]

[Opening hook, 1-2 sentences]

[NUMBERED POINTS WITH BOLD HEADERS — at least 3, at most 6]
Each point: claim + evidence + practical application

PRACTICAL TAKEAWAYS:
- [bullet 1]
- [bullet 2]
- [bullet 3]

THE BOTTOM LINE:
[1-2 sentence summary]

👉 [CTA from the brand list]

[Hashtag block]

REFERENCES:
{references_block_instruction}
```

**REFERENCES block format (mandatory):** numbered entries, one per line, in the form `N. <citation text>` where `<citation text>` is copied byte-for-byte from the verified list. Do NOT use `[1]`, `(1)`, `1)`, or any other numbering style. Do NOT prepend or append any wrapping characters. The downstream `parse_refs_block` function in `audits/_citation_audit.py` parses with the exact pattern `r"\s*(\d+)\.\s*(.+?)\s*$"` — anything else fails to parse and triggers a Layer A reject. Concrete example:

```
REFERENCES:
1. Forbes SC et al. (2025). Effects of Creatine Supplementation on Upper- and Lower-Body Strength and Power: A Systematic Review and Meta-Analysis. Nutrients, 17(17), 2748. doi:10.3390/nu17172748
2. Candow DG et al. (2024). Effects of Creatine Supplementation and Resistance Training on Muscle Strength Gains in Adults <50 Years: Systematic Review and Meta-Analysis. J Int Soc Sports Nutr, 21(1). PMID:39519498
```

# Hard rules

1. **No invented citations.** See the CRITICAL SAFETY RULE above.
2. **No "Helms et al. (2018)" inline references in the body** unless that exact citation is in the verified list. If you want to reference research, use a generic phrasing ("research shows", "a 2024 meta-analysis found") and let the REFERENCES block carry the specifics.
3. **No "studies have shown" without a verified citation backing it.** If the verified list is empty, the post can still make recommendations but must phrase them as practitioner experience, not research-backed claims.
4. **Brand voice**: authoritative but approachable. Like a knowledgeable training partner, not a professor or salesperson. Use "you/your" language.
5. **Output the caption verbatim**, starting with the headline line. Do not include a preamble or commentary.
6. **REFERENCES block format** must match the example above byte-for-byte (numbered entries `1. citation`, `2. citation`, ...). Any other formatting fails the Layer A check and triggers a retry.

# Now write the post

<<<PROMPT_END>>>
```

### 4.2 The `{allowed_citations_block}` substitution

The grounded drafter formats the allow-list as a numbered block before substitution. Each entry shows the canonical citation text the LLM is required to use byte-for-byte:

```
1. Forbes SC et al. (2025). Effects of Creatine Supplementation on Upper- and Lower-Body Strength and Power: A Systematic Review and Meta-Analysis. Nutrients, 17(17), 2748. doi:10.3390/nu17172748
2. Candow DG et al. (2024). Effects of Creatine Supplementation and Resistance Training on Muscle Strength Gains in Adults <50 Years: Systematic Review and Meta-Analysis. J Int Soc Sports Nutr, 21(1). PMID:39519498
3. Antonio J et al. (2021). Common questions and misconceptions about creatine supplementation. J Int Soc Sports Nutr, 18(1):45. doi:10.1186/s12970-021-00412-w
```

If the allow-list is empty, the substituted block is the literal string:

```
[NO VERIFIED CITATIONS AVAILABLE FROM THIS SOURCE]
```

### 4.3 The `{references_block_instruction}` substitution

The drafter computes this based on the allow-list size:

- **Allow-list ≥ 1 entry**: `"Use the citations from the verified list above, in the order they support claims in the body. Number them 1, 2, 3, ... and copy each citation verbatim from the list above. Do not modify any character."`
- **Allow-list empty**: `"[INSUFFICIENT_SOURCE_DATA]"` literal — the LLM is instructed to write that exact marker as the REFERENCES block content.

### 4.4 The `{article_body_excerpt}` substitution

The drafter passes a **truncated** copy of `article["full_text"]` to the LLM, capped at **4000 characters**. Rationale: Opus 4.6 handles much longer contexts, but longer body excerpts don't make the LLM more grounded — they just give more surface for the LLM to get confused about which claims came from the source vs. its training memory. 4000 chars is enough to support a 6-point Instagram post and keeps the prompt compact.

Truncation rule: cut at the **nearest paragraph boundary** (last `\n\n` before char 4000) when possible. If no paragraph boundary exists in the first 4000 chars (rare — long unbroken text), hard-cut at char 4000. Append the literal marker `\n\n[...truncated, see source URL for full article]` so the LLM knows the body was abbreviated and can't infer missing context from absence of text.

```python
def _excerpt(full_text: str, *, max_chars: int = 4000) -> str:
    if len(full_text) <= max_chars:
        return full_text
    cut = full_text[:max_chars]
    last_para = cut.rfind("\n\n")
    if last_para > max_chars // 2:  # only honor boundary if it's not absurdly early
        cut = cut[:last_para]
    return cut.rstrip() + "\n\n[...truncated, see source URL for full article]"
```

### 4.5 Temperature, retry policy, model

- Model: `claude-opus-4-6` (same as `chinese_drafter`)
- Temperature: **0.5** — lower than the Chinese drafter's 0.7. Citations are precision work; we want less creative drift.
- Max tokens: 4096 (plenty for an Instagram caption)
- `llm_client.complete` already handles backoff/retry on transient HTTP failures (2 attempts, exponential delay). Reuse as-is.

## 5. Verification-retry-drop loop

After the LLM returns, the drafter runs a verification loop to catch any output that violates the allow-list constraint despite the prompt:

```python
def generate_grounded_draft(article, *, max_retries=1):
    """
    Returns a draft.txt text body that has passed allow-list + verify_citations
    checks, or None if all attempts failed.
    """
    allowed = extract_allowed_citations(article)  # § 3
    prompt = build_grounded_prompt(article, allowed)  # § 4

    if not llm_client.is_configured():
        return None  # graceful degradation, same as chinese_drafter

    for attempt in range(max_retries + 1):
        temp = 0.5 if attempt == 0 else 0.3  # cool down on retry
        text = llm_client.complete(prompt, temperature=temp)
        if text is None:
            continue  # network failure, retry

        # Layer A: cheap allow-list byte-check on the LLM output's REFERENCES block
        if not _all_refs_in_allowlist(text, allowed):
            log(f"[REJECT] {slug}: LLM output contained refs not in allow-list, "
                f"retrying at temp={0.3}")
            continue

        # Layer B: full verify_citations pass (defense-in-depth — catches
        # cases where the LLM byte-equivalent citation somehow still has a
        # network-disguised network-failure or any blocking severity).
        rows = verify_citations(text, slug=article.get("slug", ""))
        blocking = [r for r in rows if is_blocking(r["severity"])]
        if blocking:
            log(f"[REJECT] {slug}: verify_citations found {len(blocking)} blocking "
                f"issues post-LLM, retrying")
            continue

        return text  # SUCCESS — clean draft

    log(f"[DROP] {slug}: all {max_retries + 1} attempts failed, no draft produced")
    return None
```

### 5.1 The `_all_refs_in_allowlist` byte-check (Layer A)

This is a **fast pre-filter** to catch the obvious failure mode (LLM ignored the constraint and emitted a fabricated citation). Cheaper than `verify_citations` because it's pure local string matching:

```python
def _all_refs_in_allowlist(draft_text: str, allowed: list[Citation]) -> bool:
    refs = parse_refs_block(draft_text)  # reuse from _citation_audit
    if not refs:
        return True  # no refs at all — handled by allow-list-empty path
    allowed_texts = {c["citation_text"].strip() for c in allowed}
    for _idx, raw in refs:
        if raw.strip() not in allowed_texts:
            return False
    return True
```

This catches "LLM hallucinated a new citation" in milliseconds. The `verify_citations` check (Layer B) is the slower defense-in-depth that catches "LLM byte-equivalent-copied an allow-list citation but the underlying paper turned out to be unreachable at verify time" — rare but possible during a network outage between extraction and verification.

### 5.2 Why retry-then-drop, not retry-many-times

Two reasons. First, an LLM that fails the constraint on the first try with `temp=0.5` and fails again with `temp=0.3` is showing signal — either the prompt is ambiguous in a way the model can't recover from, or the source article genuinely doesn't support a draft of this shape. More retries waste tokens. Second, **drop is a valid outcome**. The grounded drafter is allowed to fail loudly. Better to have 8 successful drafts and 23 explicit `[DROP]` log lines than 31 drafts where some have hallucinated citations.

### 5.3 Why verify_citations as Layer B and not just Layer A

Layer A is fast but only catches "the LLM emitted a citation string not in the allow-list". It does NOT catch:

- An allow-list citation that became unreachable between extraction and post-LLM verification (network race).
- An allow-list citation that the LLM byte-equivalent copied but the underlying paper has been retracted, withdrawn, or had its DOI corrupted at the source since the audit was last run.
- Future audit module revisions that detect new failure modes the current allow-list extractor doesn't.

Layer B is the defense-in-depth net. With `is_blocking()` defaulting to `unknown_blocks=True`, any new severity the audit module starts emitting will trigger a retry/drop without a code change here.

## 6. Behavior contract

The grounded drafter has three possible outcomes:

1. **Success** — returns a draft.txt text body with a verified REFERENCES block. Saved to `Posts/<slug>/en/draft.txt` by the caller. `meta.json` gets stamped with `audit_status: "OK"` (or `"WARN"` for soft-flag-only) at write time using `audit_meta_writer`'s helper.
2. **INSUFFICIENT_SOURCE_DATA** — the source article's allow-list was empty (zero verifiable citations). The drafter returns `None` and logs `[INSUFFICIENT_SOURCE_DATA] {slug}`. **The post is not saved.** The scraper is responsible for either finding a richer source or marking the topic as "needs human research".
3. **DROP** — the LLM produced output that failed allow-list or verification on every retry. Returns `None`, logs `[DROP] {slug}: all attempts failed`. **The post is not saved.** A future iteration may retry with a different model or different prompt, but for now, drop is final.

**No fallback to the template-based `draft_post_template`.** That function is the safe-but-low-quality path used by `contentprinter.generate_draft(article)` for callers who explicitly want template output. The grounded drafter is invoked only via the new `--llm` flag (CLI) or `generate_grounded_draft(article)` (library). They are separate code paths and the grounded path never silently falls back to the template path — if it fails, it fails loudly.

## 7. Worked examples

### 7.1 Rich-citation article (PubMed source with 5 extractable refs)

**Input:** A scraped PubMed article from `src/pubmed_scraper.py` with `structured_content.doi = "10.3390/nu17172748"`, `structured_content.pmid = "39842073"`, and an abstract that mentions 4 other DOIs inline.

**Allow-list extraction:**
- Source 1 (PubMed structured): 1 entry (the article itself, Forbes SC 2025)
- Source 2 (inline DOI regex on abstract): 4 candidate DOIs → all verified through `verify_citations` → 4 OK records
- Total: 5-entry allow-list after dedup

**Prompt substitution:** `{allowed_citations_block}` is the 5-line numbered list. `{references_block_instruction}` says "Use the citations from the verified list above..."

**LLM output (expected):** A caption with 4-5 numbered points, each citing one of the 5 allow-listed papers. The REFERENCES block at the bottom is the 5 citations copied verbatim from the list.

**Layer A check:** `_all_refs_in_allowlist` parses the REFERENCES block, sees 5 entries, all match allow-list set → pass.

**Layer B check:** `verify_citations` re-runs the 5 against Crossref/PubMed → all `OK` → pass.

**Outcome:** SUCCESS. Draft saved.

### 7.2 Borderline 1-citation article (RSS source with one inline DOI)

**Input:** A BarBend article from `src/scraper.py` with no `structured_content` and `full_text` containing one inline DOI: "...recent meta-analysis (doi:10.3390/nu17172748) found...".

**Allow-list extraction:**
- Source 1 (PubMed structured): empty (RSS source)
- Source 2 (inline DOI): 1 candidate → verified → 1 OK record
- Source 3 (inline PMID): empty
- Total: 1-entry allow-list

**Prompt substitution:** `{allowed_citations_block}` is a single numbered line. `{references_block_instruction}` is the "use the verified list" version.

**LLM output (expected):** A caption with 3-4 numbered points where ONE point cites the verified paper and the others are practitioner-voiced ("research suggests", "a recent review found"). The REFERENCES block at the bottom is the single citation copied verbatim.

**Layer A check:** Pass (1 ref, matches allow-list).

**Layer B check:** Pass (`OK` from Crossref).

**Outcome:** SUCCESS. Draft saved with a 1-citation REFERENCES block. **The editorial spec's "minimum 2 references" rule is intentionally NOT enforced** — that rule was the source of the hallucination pressure.

### 7.3 Zero-citation article (RSS source with no verifiable citations)

**Input:** A T-Nation blog post from `src/scraper.py` with no `structured_content`, `full_text` containing narrative claims like "everyone knows squats are king" but no DOIs/PMIDs anywhere.

**Allow-list extraction:**
- Source 1 (PubMed structured): empty
- Source 2 (inline DOI): empty
- Source 3 (inline PMID): empty
- Total: 0-entry allow-list

**Outcome decision: Option A — refuse to draft, with a structured signal file.** (Approved by team-lead 2026-04-12.)

The drafter logs `[INSUFFICIENT_SOURCE_DATA] {slug}: T-Nation article has no extractable citations`, returns `None`, **AND emits a signal file** at `Posts/.needs_research/<slug>.json` containing:

```json
{
  "slug": "training_some_topic",
  "source_url": "https://www.t-nation.com/...",
  "source_type": "rss",
  "article_title": "Everyone Knows Squats Are King",
  "extracted_refs_attempted": 0,
  "extraction_breakdown": {
    "structured_content_doi": false,
    "inline_doi_matches": 0,
    "inline_pmid_matches": 0
  },
  "timestamp": "2026-04-12T14:35:10Z"
}
```

The `Posts/.needs_research/` directory is **gitignored** (added to `.gitignore` as part of the implementation phase). It's purely operational state, not source-controlled. Operators (or a future CSKB admin view) can read it to see "we've refused 12 posts from T-Nation this month because they don't carry citations; maybe we should reconsider that source's editorial role or find a PMC mirror for this topic."

**Why the signal file matters:** without it, Option A has a silent failure mode — the scraper keeps feeding practitioner-voiced sources to the drafter and the drafter keeps refusing, and nobody notices the content pipeline is quietly starving. The signal file is the visibility hook that makes operational triage possible.

**Why not Option B (uncited draft + marker):** Option B introduces a new draft state, a new render path (the watermark generator needs to handle the marker), and the editorial value of an uncited Instagram post for Central Strength Gyms is low anyway. The brand is science-based; a post with no citations is off-brand by definition. Better to refuse and surface the gap explicitly than to publish something that quietly contradicts the brand voice.

**Future caveat (filed under §9 risks):** if a future editorial decision wants to allow practitioner-voiced posts as first-class citizens (e.g. a "coach's notes" content category that's explicitly experiential rather than research-backed), the grounded drafter would need a new `--allow-uncited` flag and the byte-check needs a practitioner-voiced escape hatch. For now, that's deliberately out of scope.

## 8. Integration points

### 8.1 New file

`src/grounded_drafter.py` — the new module containing `extract_allowed_citations`, `build_grounded_prompt`, `_all_refs_in_allowlist`, `generate_grounded_draft`. ~200 lines including docstrings. No changes to existing files in this phase.

### 8.2 New config

`config/grounded_drafter_prompt.md` — the prompt template from §4.1. Loaded by `grounded_drafter.py` at runtime.

### 8.3 New CLI flag

`python src/main.py draft --llm` — invokes `generate_grounded_draft` instead of `draft_post_template` for each article. Existing `python src/main.py draft` (no flag) is unchanged and continues to use the template path. **No deprecation of the existing draft path** in this phase.

### 8.4 New library entry

`contentprinter.generate_grounded_draft(article) -> str | None` — added to `contentprinter/__init__.py` exports. Wraps `src.grounded_drafter.generate_grounded_draft` through the same `_compat` shim path as existing entries. Bumped to `__version__ = "0.3.0"` (additive public surface). Documented in API_SURFACE.md §2 and §11 (new "Grounded LLM drafting" section).

### 8.5 Deprecation of `run_polish`

`src/main.py::run_polish` gets a runtime `DeprecationWarning` and a docstring banner pointing at the grounded drafter. **Not removed.** The CLI subcommand `python src/main.py polish` continues to work but prints a yellow warning explaining the hallucination finding and recommending `--llm` instead. Per team-lead's instruction in the #35 task description, deletion comes in a follow-up sprint after the grounded path has been validated.

### 8.6 `config/content_strategy.md` update

The "Minimum 2 scientific references per post" rule (lines 155-159) is rewritten to:

> **Citation grounding constraint** (added 2026-04-12 after the citation hallucination crisis):
>
> The REFERENCES block must contain ONLY citations that the scraped source article carries in `structured_content.doi` / `structured_content.pmid`, OR inline DOI/PMID strings in the article body that have been verified against Crossref/PubMed at extraction time. **Do NOT generate citations from training memory.** A post with 1 honest citation is better than a post with 5 fabricated ones. A post with 0 citations is allowed if the source article is practitioner-voiced rather than research-citing — mark the REFERENCES block as `[INSUFFICIENT_SOURCE_DATA]`.
>
> The previous "minimum 2 references" rule has been retracted because it created the hallucination pressure that led to the 2026-04-12 audit finding (38% of citations across 31 posts were hallucinated, misattributed, or unverifiable). See `audits/drafter_root_cause_2026-04-12.md` for the full analysis.

Touching `content_strategy.md` is **scoped to this section only** — none of the editorial calendar (Posts 22-41) or the engagement-optimization notes are modified, since researcher's `upcoming_pdf_urls.json` assumed the calendar as-is.

### 8.7 `parse_refs_block` visibility

Layer A's `_all_refs_in_allowlist` calls `parse_refs_block` from `audits/_citation_audit.py`. That function is currently a private helper of the audit module — the leading underscore in the audit file's other helpers (`_get`, `_head`, `_tokens`, `_jtokens`, `_strip_diacritics`) suggests intent, but `parse_refs_block` itself is unprefixed and is in fact already imported by `contentprinter/verify.py:217` for the per-citation delegation pattern.

**Decision: re-import from `_citation_audit` directly in the grounded drafter, same as `verify.py` does.** Rationale: (a) keeps the dependency surface visible — both `verify.py` and the new `grounded_drafter.py` would touch the same private-by-convention helper, which is grep-able as a single pattern; (b) avoids creating a new public name in `contentprinter.verify` until we have multiple consumers asking for it; (c) `parse_refs_block` is genuinely stable — researcher hasn't touched it since #21 and the regex is documented in the audit `.md`.

If a third consumer ever needs `parse_refs_block`, that's the trigger to promote it to a public function in `contentprinter.verify` (e.g. as `parse_references`). For now, two internal consumers is fine.

### 8.8 What this design does NOT change

- `src/drafter.py::draft_post_template` — the existing template-based drafter stays. Still safe to call from `contentprinter.generate_draft(article)`, still produces valid (template-quality) output, still has zero LLM dependency. The CSKB iOS app can use it directly without the grounded path.
- `src/single_page_generator.py` — no rendering changes. The grounded drafter produces the same draft.txt format the existing renderer expects.
- `audits/_citation_audit.py` and `contentprinter/verify.py` — no changes. The grounded drafter calls `verify_citations` as a consumer.
- `chinese_drafter.py` — no changes. The Chinese drafter continues to consume English drafts and translate them; if the English draft was produced by the grounded path, the Chinese draft inherits its citation safety.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM byte-equivalent citation copy still has trailing whitespace / quote variation that fails the byte-check | Layer A normalizes both sides with `.strip()` before comparison. Cross-check against an actual prompt/response pair before final rollout. |
| Allow-list extraction misses an inline DOI because of unusual punctuation | The regex is intentionally lenient. If a real DOI is missed, the post is just shorter, not wrong. Log the regex matches at debug level so we can spot patterns to add. |
| Crossref / PubMed rate limits during extraction | `verify_citations` uses the audit module's existing 0.15s sleep between calls. 5-citation extraction = ~1 second. CSKB job runner already treats this as background work per API_SURFACE.md §2. |
| Source article cites a 2025 paper not yet in Crossref | `verify_citations` returns `DOI_UNRESOLVABLE` (soft flag, not blocking). The grounded drafter accepts it but logs a `WARN` row in meta.json for human review. |
| LLM produces a draft that passes Layer A but Layer B finds a `JOURNAL_MISMATCH` soft flag | Soft flags are not blocking by `is_blocking()` default. The draft is accepted and the soft flag flows through to meta.json's `audit_issues` for the watermark renderer to optionally surface. |
| `is_llm_configured()` returns False (no API key) | The drafter returns `None` immediately, same graceful degradation as `generate_chinese_from_english`. The `--llm` CLI flag is a no-op without a key, with a clear log line. |
| The prompt template drifts from the intended behavior over time | The prompt lives in `config/grounded_drafter_prompt.md` (git-tracked). Any change goes through code review like the chinese prompt template. |
| **Total `generate_grounded_draft` runtime budget** — extraction (5-15 sec for 1-8 candidate citations × ~1.5 sec each) + LLM call (5-15 sec for the Anthropic round trip) + Layer B re-verification (5-15 sec, same per-citation cost as extraction) = **30-60 seconds total per post**. | Document explicitly in `API_SURFACE.md` §11 (when the doc lands during implementation) that `generate_grounded_draft` is a job-runner background operation, **not a request-handler operation**. CSKB api-engineer's job runner is async by design (per `CentralStrengthKB/docs/ARCHITECTURE.md` §3 — `POST /v1/generate` returns `202` with a `job_id`, iOS polls for completion), so this fits the existing lifecycle. The risk is only that an inline call from an HTTP handler would block the event loop for up to a minute. |
| **Future editorial demand for uncited posts** — a "coach's notes" content category that's explicitly experiential rather than research-backed would currently be refused by the grounded drafter under §7.3 Option A. | If/when this becomes a real editorial requirement, add an `--allow-uncited` flag to `generate_grounded_draft` and a practitioner-voiced escape hatch to the byte-check. For now, deliberately out of scope — the brand is science-based and uncited posts are off-brand by definition. The `Posts/.needs_research/<slug>.json` signal file from §7.3 makes it visible when this gap actually starts hurting the content pipeline. |

## 10. Approval status

All five approval items below were greenlit by team-lead on 2026-04-12 with the polish-pass tweaks now folded into the doc above. **Implementation phase is unblocked.** The approvals are itemized for traceability:

1. **Three-layer architecture** (extract allow-list → grounded LLM call → verify-retry-drop loop) — APPROVED. The two-layer verification (fast byte-check Layer A + defense-in-depth `verify_citations` Layer B) is the right shape; retry-once-then-drop is correct; drop-is-valid-outcome doctrine in §5.2 is the load-bearing piece that prevents regression to "retry forever".
2. **Prompt template in §4.1** — APPROVED with two folded-in tweaks: (a) §4.4 added documenting the `{article_body_excerpt}` truncation rule (4000 chars at paragraph boundary, `[...truncated...]` marker, `_excerpt` helper pseudocode); (b) §4.1 prompt body now contains the "REFERENCES block format (mandatory)" subsection with a concrete example showing the exact `N. <citation>` format, matching `parse_refs_block`'s `r"\s*(\d+)\.\s*(.+?)\s*$"` regex. Hard rule #6 added to enforce the format.
3. **§7.3 zero-citation handling** — APPROVED Option A with the `.needs_research/<slug>.json` signal file enhancement. §7.3 rewritten to remove the open question and document the signal file shape, the gitignore note, and the Option B rejection rationale.
4. **`config/content_strategy.md` retraction in §8.6** — APPROVED in principle. **Diff held until the implementation PR** so team-lead can review side-by-side. The implementation phase will produce the actual diff against the current text and submit it as part of the Layer 1 PR.
5. **Library export `generate_grounded_draft` + version bump to 0.3.0** — APPROVED. Documented in §8.4. The implementation phase will add the corresponding §2 entry and a new §11 "Grounded LLM drafting" section in `API_SURFACE.md` clarifying when to call grounded vs template paths.

**Polish-pass additions also folded in:**

- **§4.4** new — `{article_body_excerpt}` truncation rule and helper pseudocode
- **§4.5** renumbered — "Temperature, retry policy, model" was §4.4 before, now §4.5 after the new excerpt subsection slotted in
- **§4.1 prompt body** — REFERENCES block format example + Hard rule #6
- **§7.3** rewritten — Option A approved with `.needs_research/` signal file structure, gitignore note, Option B rejection rationale
- **§8.7** new — `parse_refs_block` visibility decision (re-import from `_citation_audit`, same pattern as `verify.py`; promote to public name only when a third consumer asks)
- **§8.8** renumbered — was §8.7 before
- **§9 risks table** — two new rows: total runtime budget (30-60 sec, job-runner-only) and the future-uncited-posts caveat with the `--allow-uncited` escape hatch

## 11. Implementation phase — what lands next

The code phase produces these files (per §8 integration points):

- `src/grounded_drafter.py` — new (~200 lines)
- `config/grounded_drafter_prompt.md` — new (the §4.1 template text)
- `src/main.py` — `--llm` flag added, `run_polish` deprecation banner
- `config/content_strategy.md` — §8.6 retraction diff (held for review-in-PR)
- `contentprinter/__init__.py` — `generate_grounded_draft` export, `__version__` bump to 0.3.0
- `contentprinter/grounded_drafter.py` — thin shim around `src/grounded_drafter`
- `API_SURFACE.md` — §2 entry for `generate_grounded_draft`, new §11 "Grounded LLM drafting" section, version-bump changelog
- `tests/test_grounded_drafter.py` — new tests (allow-list extraction, byte-check, retry loop, dry-run, three worked-example fixtures)
- `.gitignore` — add `Posts/.needs_research/`

**Sequencing precondition:** team-lead has explicitly required that **#39 (refresh_audit_meta) lands before Layer 1 implementation begins**. As of this design-doc revision, #39 is shipped and live (103/103 tests pass), so the precondition is satisfied. Implementation can start whenever team-lead gives the explicit "go" signal.

Estimated implementation time: 2-4 hours of coding + testing per team-lead's prior estimate. The doc above is the contract; the code shouldn't deviate from it without surfacing the deviation in a code-review note.
