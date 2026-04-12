# Source Format Design — Reddit & Forum Handling on the Single-Page Template

**Status:** Ahead-of-need design note. Written while backend-writer is scoping Task #6 (recursive Reddit / forum / YouTube expansion). No code changes yet — this is the contract frontend-writer will implement once the scrapers produce real output.

**Author:** frontend-writer
**Consumers:** backend-writer (scraper output shape), code-reviewer (sanity check), project-manager (scope gating)

---

## 1. Problem

ContentPrinter's single-page generator was built for long-form blog/RSS + peer-reviewed article drafts. The `parse_detailed_content()` contract assumes:

- Title line at the top of a `CAPTION:` block
- Intro paragraph
- Numbered points (usually 5) each with a headline + body paragraph
- `PRACTICAL GUIDE` / `THE BOTTOM LINE` sections
- `REFERENCES:` block with 4-7 peer-reviewed citations

Reddit and phpBB-style forum threads do not match this shape. The typical reality is:

- **Reddit** — a short OP (often under 200 words), zero citations, a highly-upvoted top comment that carries most of the actual information, secondary comments that qualify or contradict it, thread score, subreddit context.
- **Forum threads** — a longer OP with inline images, a multi-page reply chain where the authoritative answer is a quote-chain from a credentialed poster (often a coach), occasionally a sticky mod note.

If we force these into the existing `numbered_points` layout we lose the two things that make community content valuable: **attribution** (who said it, and what was their standing in that community) and **discourse structure** (the claim, the challenge, the synthesis).

---

## 2. Design Principles

1. **Don't break existing layouts.** The program / mythbust / rehab / supplement layouts work well for drafter-generated content. Community-source layouts are additive, dispatched through the same `post["layout"]` field.
2. **Preserve attribution as first-class data.** Author handle, subreddit or forum name, score/upvote count, and a permalink to the original comment all get saved — not optional metadata. Legal and editorial reasons: we credit the community voice.
3. **Treat community drafts as commentary, not science.** These posts should never carry the `evidence_info` apparatus (which is already invisible after Task #1, but the diagnostic still logs it). Skip `extract_evidence_info()` for community sources or stub it to `level=""`.
4. **Stay within the existing field schema where possible.** Add new layout-specific fields alongside `program_phases` / `myths` / `rehab_steps` / `supplement_facts` — don't invent a parallel `post` dict.
5. **No external fetches at render time.** The scraper is responsible for resolving everything the renderer needs (comment text, score, permalink, avatar-less author handle). The renderer must not hit Reddit or forum APIs.

---

## 3. New Layout A — `reddit_thread`

### 3.1 Trigger

`post["layout"] = "reddit_thread"` when the scraper writes a draft whose `Source:` line starts with `reddit.com/r/` or whose meta.json has `source_type: "reddit"`.

### 3.2 New fields on `post`

```python
post["reddit_meta"] = {
    "subreddit": "powerlifting",           # no r/ prefix
    "thread_title": "...",                 # original OP title
    "thread_score": 1247,
    "thread_permalink": "https://old.reddit.com/r/powerlifting/...",
    "op_author": "u/handle",               # include u/ prefix for display
    "op_body": "...",                      # markdown-stripped, ≤ 600 chars
    "fetched_at": "2026-04-11T..."
}
post["reddit_callouts"] = [                # top-voted comments, ranked
    {
        "author": "u/coachX",
        "score": 412,
        "body": "...",                      # ≤ 500 chars, markdown-stripped
        "permalink": "...",
        "is_op_reply": False,
        "flair": "Verified Coach",          # optional, subreddit flair text
    },
    ...
]
```

The scraper guarantees `len(reddit_callouts) <= 4`. Anything beyond 4 gets truncated — a single page can't render more without becoming a wall of quotes.

### 3.3 Visual treatment

Header region (above the existing title):
- Small pill-shaped badge: `r/powerlifting  ·  1.2k ▲` in muted orange
- OP attribution line: `Asked by u/handle` in TEXT_MUTED
- The existing title line is the OP thread title, uppercased as now

Body region (replaces the numbered-points grid):
- OP excerpt box — card background `BG_CARD`, left accent bar `ACCENT_RED`, label "OP" at top-left, body text wrapped
- Each callout rendered as its own card:
  - Top-left: author handle in `TEXT_WHITE` bold
  - Top-right: `▲ 412` score in muted orange
  - Optional flair chip next to the handle if present
  - Body text in `TEXT_LIGHT`
  - Bottom-right: small `[source]` label in `TEXT_DOI` hinting at the permalink (we don't render the URL, but the permalink is preserved in meta.json so humans can verify before posting)
- Dividers between callouts are a thin `DIVIDER` line, not full card separation — we want the thread-discussion feel
- No `PRACTICAL GUIDE` section; Reddit posts don't get a synthetic action list from the renderer. If the scraper wants one, it writes a summary_text which renders as the existing `THE BOTTOM LINE` box.

### 3.4 Heights

Add to `calculate_page_height()`:
- `+S(60)` for subreddit badge + OP attribution line
- `+S(14) + wrap(op_body, font_body) + S(20)` for OP excerpt box
- For each callout: `+S(30)` header row + wrapped body + `+S(14)` bottom margin

### 3.5 Rendering function

New `_render_reddit_layout(draw, y, post, left_x)` beside the existing `_render_program_layout` / `_render_mythbust_layout` / etc. Dispatched from `render_single_page()` alongside the existing `if layout == "program" ...` chain.

---

## 4. New Layout B — `forum_thread`

### 4.1 Trigger

`post["layout"] = "forum_thread"` when the scraper sets `source_type: "forum"` (T-Nation, Starting Strength, phpBB, etc.).

### 4.2 New fields

```python
post["forum_meta"] = {
    "forum_name": "T-Nation",
    "subforum": "Powerlifting",
    "thread_title": "...",
    "thread_url": "...",
    "op_author": "username",
    "op_rank": "Senior Member",       # forum-native rank text, optional
    "op_post_count": 1842,            # optional, cast to None if unavailable
    "op_body": "...",                 # ≤ 800 chars
    "fetched_at": "..."
}
post["forum_quote_chain"] = [         # ordered, ranked by editorial judgement in scraper
    {
        "author": "coach_handle",
        "rank": "Verified Coach",
        "body": "...",                 # ≤ 600 chars
        "quoting": None,               # or the index of the post being quoted
        "permalink": "..."
    },
    ...
]
```

Quote chains can nest (forum post B quotes forum post A). The scraper flattens to a linear list and sets `quoting` to the flat-list index of the parent. Max 4 entries.

### 4.3 Visual treatment

Header region:
- Forum name + subforum as a pill: `T-Nation › Powerlifting`
- OP author line with rank in muted: `username · Senior Member · 1842 posts`

Body region:
- OP excerpt card (taller than Reddit OP since forum OPs are usually longer)
- Quote chain rendered as nested cards, each quoted post getting a left-indent of `S(30)` when `quoting is not None`, plus a thin vertical connector line to the parent card to visualize the thread.
- Indent depth capped at 2 levels — anything deeper rendered flat to avoid blowing the page width.

### 4.4 Reuse vs. duplication with Reddit

80% of the forum layout is visually identical to the Reddit layout (author + score + body + permalink hint). **Recommendation:** share a single helper, `_render_community_callout(draw, y, card_data, left_x, indent=0)`, called by both `_render_reddit_layout` and `_render_forum_layout`. The only real divergence is the header pill (subreddit vs forum name) and the indent/connector logic for forum quote chains.

This keeps card styling consistent across community sources without bloating the module.

---

## 5. Impact on `parse_detailed_content()`

Current situation: `parse_detailed_content()` reads a single `.txt` file with a hardcoded `CAPTION: ... REFERENCES:` structure. That format doesn't naturally hold structured community metadata.

Three options, in order of my preference:

**Option 1 (preferred): scraper writes a sidecar JSON.**
The scraper produces `Posts/<slug>/en/draft.txt` as usual (the caption/flavor text the author wants on the page), and additionally `Posts/<slug>/en/source.json` containing the community metadata shape from §3.2 / §4.2. `parse_detailed_content()` learns to detect the sidecar, load it, and populate `reddit_meta` / `forum_meta` / etc. directly. The txt file stays human-editable; the structured data stays structured. This matches how `meta.json` already works at the topic level (thanks to backend-writer's Task #2 reorg).

**Option 2: inline structured block inside draft.txt.**
Add a new `REDDIT_CALLOUTS:` or `FORUM_CHAIN:` block with pseudo-YAML. Downside: fragile parsing, harder for editors to tweak manually without breaking the regex. I don't recommend this.

**Option 3: switch the whole pipeline to YAML/JSON drafts.**
Cleaner long-term but this is a rewrite of `parse_detailed_content()` and `drafter.py` and should be its own sprint if we ever go that way. Out of scope here.

**Ask for backend-writer:** does Option 1 work for you? If yes, the new field on `meta.json` (`source_type: "reddit" | "forum" | "rss" | "pubmed" | "youtube"`) and the sidecar `source.json` are your deliverable; I'll build the renderer against that contract.

---

## 6. Things that stay out of scope

- **Auto-ranking callouts.** Which comment is "best" is an editorial decision, not an algorithmic one. The scraper records top-voted comments; a human or the drafter curates the final 2-4 that land in the post.
- **Rendering nested reply trees.** One level of quote-chain is enough for a single-page format. If the discourse is deeper than that, the post probably doesn't belong on a graphic.
- **Fetching user avatars.** We do not render avatars — too many permissions and API-cost problems, and the tonal fit is wrong (too social-media, not enough science-card).
- **Score thresholds baked into the renderer.** Don't enforce "min score 100" in the generator; the scraper decides what's worth surfacing.

---

## 7. Open questions for backend-writer

1. **Sidecar format** — Option 1 above. Please confirm or propose an alternative.
2. **Author handle scrubbing** — do we want a `display_author` field that replaces `u/realname` with `u/a_reddit_user` for posters who asked to be anonymized, or do we always surface the handle as-is? Editorial question as much as technical.
3. **Source attribution line** — Reddit's licensing requires linking back to the original thread. The renderer shows a `[source]` hint; the permalink is in `meta.json`. Is that enough, or does legal want the full URL rendered on the PNG? (I'd rather not — URLs at typical Reddit length blow the layout.)
4. **Flair and rank strings** — these can be arbitrary text set by subreddit mods or forum admins. Should the scraper sanitize them (strip emoji, cap length) or should the renderer do it? I think scraper — the renderer shouldn't know sub-specific quirks.
5. **What happens to `extract_evidence_info()` on community sources?** My recommendation: skip it entirely (stub `evidence_info = {}`) so the diagnostic print at line 1335 just shows `evidence=-`. Alternative: keep calling it on the OP body, which will basically always return empty. Either works; prefer the stub for clarity.

---

## 8. Implementation roadmap (when this becomes real work)

1. Backend-writer publishes a sample scraper output — one Reddit, one forum — into a `tests/fixtures/` dir so I can build the renderer against real data rather than a synthetic schema.
2. Extend the `post` dict schema with the new fields (§3.2, §4.2).
3. Implement `_discover_topic_drafts()` awareness of `source_type` → `post["layout"]` mapping. Single-page generator reads the sidecar and dispatches.
4. Write `_render_community_callout()` shared helper + `_render_reddit_layout()` + `_render_forum_layout()`, alongside height calculators.
5. Generate 2-3 test PNGs from fixtures, iterate with backend-writer on what the scraper guarantees vs. what the renderer assumes.
6. Code-reviewer pass, same conventions as Task #1.

Rough sizing: 1-2 days once fixtures exist. No need to start until Task #6 produces output.

---

## 9. Decisions locked in with backend-writer (2026-04-12)

After review with backend-writer, the following open questions are resolved:

1. **Sidecar format** — Option 1 confirmed. Scraper writes `Posts/<slug>/en/source.json` alongside `draft.txt`. Schema matches §3.2 / §4.2 exactly with one addition: a top-level `"schema_version": 1` field for forward compatibility.
2. **Handle scrubbing** — surface handles as-is. Optional `display_author` override is a future-only field; not implemented until a real anonymization case arrives.
3. **Permalink rendering** — not on the PNG. Stored in `source.json` + `meta.json`. Renderer shows `u/handle · r/sub` as the attribution line. Humans paste the full permalink into the IG caption at upload time.
4. **Flair / rank sanitization** — scraper owns it. Reddit flair capped at 20 chars, forum rank at 30 chars, emoji stripped, empty-after-strip discarded. Falsy flair → renderer omits the flair chip (no special-casing).
5. **`evidence_info` on community sources** — stubbed to `{}` by the scraper. Diagnostic print will show `evidence=-`.
6. **Promotion step ownership** — `_write_topic_sidecar()` is a `drafter.py` concern, not a scraper concern. Raw `Posts/raw/reddit_*.json` is the scraper's output; the promotion to per-topic `Posts/<slug>/en/source.json` happens when drafter decides a raw record becomes a post. Tracked as Task #13, owned by backend-writer, blocked by Task #6.

---

## 10. Revision history

- **2026-04-12** — initial draft (frontend-writer, ahead of Task #6 implementation).
- **2026-04-12** — §9 added with locked-in decisions after backend-writer review.
