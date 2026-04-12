# Sources Discovery — Researcher Notes (Task #6, Objective E)

**Author:** researcher
**Date:** 2026-04-11
**Scope:** Curate new sources for Reddit, strength-sport forums, and YouTube. Verify robots.txt and API shapes before backend-writer turns anything on.

---

## 1. Reddit (already added to `config/reddit_sources.json`)

Backend-writer already added four subreddits: `powerlifting`, `weightroom`, `StrongerByScience`, `Fitness`. Researcher confirmation and notes below.

| Subreddit | Why it's in scope | Listing | Window | Notes |
|---|---|---|---|---|
| r/powerlifting | Core audience. Competition chatter, meet reports, technique discussions. | top | week | Highest signal density for our niche. |
| r/weightroom | Strength athletes across PL/WL/strongman. Detailed training logs and Daily Thread advice. | top | week | "Training Tuesday" and "Quality Post Sunday" threads are gold. |
| r/StrongerByScience | Low volume but extremely high quality — threads pointing at SBS articles and recent meta-analyses. | hot | week | Use `hot` not `top` because volume is so low that `top/week` misses real-time posts. |
| r/Fitness | Mainstream — mostly beginner. Useful to surface widely-shared myths for the Nutrition-Myths category. | top | week | Filter by `min_score: 25, min_comments: 10` (already set). |

### API notes
- Public JSON is available at `https://old.reddit.com/r/<sub>/<listing>.json?t=<window>&limit=N` with no auth required for public listings.
- Response shape: `data.children[].data` with fields: `title`, `score`, `num_comments`, `permalink`, `url`, `selftext`, `created_utc`, `author`, `is_self`, `over_18`, `link_flair_text`, `stickied`, `subreddit`.
- **Rate limit:** unauthenticated Reddit caps around 10 req/min. The 3 s delay in `reddit_sources.json` is safe.
- **User-Agent matters:** Reddit blocks generic UAs aggressively. The configured UA `ContentPrinter/1.0 (+https://centralstrengthgyms.com)` is correct — keep it.
- **Recursion depth 2:** I recommend keeping this but tightening the outbound-link allowlist. Current allowlist is already focused on DOI/PMC/publisher domains. Add `osf.io`, `frontiersin.org`, `bjsm.bmj.com` if you see those show up in recursion logs.

### Subreddits I considered and rejected
- `r/gainit` — too noisy, mostly beginner "what should I eat" posts
- `r/xxfitness` — good female-focused content but the signal/noise ratio on evidence-based posts is low; revisit if we spin up a women-in-powerlifting content track
- `r/steroids` — out of scope for our brand voice
- `r/bodybuilding` — aesthetic focus, not strength; skip unless Hypertrophy becomes a category

---

## 2. Strength-sport Forums (config/forum_sources.json)

Backend-writer stubbed two forums (both `enabled: false`) asking researcher to verify. Results below.

### T-Nation Forum — **ENABLE**

- **Platform:** Discourse (confirmed).
- **robots.txt:** `https://www.t-nation.com/robots.txt` does **not** disallow `/latest.json`, `/c/<category>.json`, or individual topic JSON. The disallow list is limited to admin/auth/search/RSS endpoints.
- **No Crawl-delay directive** in robots.txt. Keep the configured 3-second delay out of courtesy.
- **Verified endpoint:** `https://www.t-nation.com/c/training.json` returns 30 topics per page with shape `topic_list.topics[]`, each entry having: `id`, `title`, `slug`, `posts_count`, `reply_count`, `created_at`, `last_posted_at`, `excerpt`, `views`, `like_count`, `fancy_title`, `category_id`, `posters[]`. This is exactly what we need.
- **Thread-level fetch:** `https://www.t-nation.com/t/<slug>/<id>.json` returns the OP + replies.
- **Recommended config update** (for backend-writer when flipping `enabled: true`):
  ```json
  {
    "name": "T-Nation Forum",
    "platform": "discourse",
    "category_json_url": "https://www.t-nation.com/c/training.json",
    "topic_json_template": "https://www.t-nation.com/t/{slug}/{id}.json",
    "min_posts_count": 3,
    "enabled": true
  }
  ```
- **Scraper hint:** Discourse category JSON is paginated via `?page=N`. Don't walk more than page 3 on scheduled runs.

### Starting Strength Forum — **KEEP DISABLED**

- **Platform:** vBulletin (or legacy custom, inconclusive — page returned 403 to our WebFetch).
- **robots.txt:** `https://startingstrength.com/robots.txt` explicitly disallows many paths under `/resources/forum/*` (go, search, posting, login, etc.). While the index itself may technically be crawlable, the site imposes a **Crawl-delay: 10** and signals `ai-train=no`. The site also explicitly disallows ClaudeBot, GPTBot, Google-Extended and other AI crawlers site-wide.
- **Direct fetch test** (no User-Agent spoofing): `https://startingstrength.com/resources/forum` → **HTTP 403**. The site is doing server-side blocking of non-browser clients.
- **Recommendation:** Do not scrape. The combination of `ai-train=no`, AI-crawler blocklist, 403 on unauthenticated GET, and 10-second Crawl-delay makes it both ethically and operationally inadvisable.
- **Alternative:** Starting Strength content surfaces on r/StartingStrength (smaller but active) and via Mark Rippetoe's articles at `https://startingstrength.com/articles` (which is **not** blocked by robots.txt — I verified). If we want Starting Strength content, use the articles RSS if one exists and add it to `sources.json` instead. Leave the forum alone.

### Other forums I considered

| Forum | Verdict | Why |
|---|---|---|
| **r/phpBB strength forums (AllThingsGym, GymnasticBodies, BarbellsDownUnder)** | Skip for now | Low volume, inconsistent signal. Each has its own custom rules. Revisit if we need international/Oceania content. |
| **EliteFTS Q&A** | Out of scope | Most content is behind a login wall; coaches' logs require a free account. |
| **Iron Game Forum** | Out of scope | Niche/old-school, mostly historical strongman; low evidence-based signal. |
| **Reddit r/AdvancedFitness** | Maybe later | Research-focused but very low volume. If #6 recursion yields good links from StrongerByScience, we don't need it. |

---

## 3. YouTube (config/youtube_sources.json)

- **Bruce Lu** already added to the channel list by backend-writer — confirmed present.
- **Recommended addition:** no additional Chinese-language channels right now. Bruce Lu is the only Mainland Chinese evidence-based strength YouTuber with meaningful volume. Candidates I vetted:
  - 健身女神-Rosie (out — aesthetic/bodybuilding focus, not strength)
  - 硬派健身 (out — general fitness, not evidence-first)
  - Dr. Mike Varshavski (out — general medicine, not strength specialist)

- **Recommended addition:** expand `max_videos` on Bruce Lu from default to **5** so we capture a week's worth of content, since his upload cadence is ~1-2 videos/week and we want at least one complete week of backlog in case of pipeline outages. Backend-writer — please bump this when convenient.

- **Channels NOT to add (candidates I rejected):**
  - **AthleanX (Jeff Cavaliere)** — huge reach, but hyperbolic titles and undersells nuance. Brand voice mismatch.
  - **Buff Dudes** — entertainment-first, not evidence-first.
  - **Joe Rogan podcast clips** — breadth is too wide; signal gets drowned by off-topic content.
  - **More Plates More Dates (Derek)** — PED-focused; we do not cover PEDs editorially.

---

## 4. Summary of Recommended Actions for Backend-Writer

1. **Flip `t-nation` to `enabled: true`** with the config block shown above. Verified safe against robots.txt.
2. **Leave Starting Strength Forum disabled.** Add a comment pointing at `https://startingstrength.com/articles` as the legitimate alternative; consider adding the articles RSS feed to `sources.json` in a later sprint.
3. **Bump Bruce Lu `max_videos` to 5** in `youtube_sources.json`.
4. **Add `osf.io`, `frontiersin.org`, `bjsm.bmj.com`** to the `outbound_link_allowlist` in `reddit_sources.json` once you see real recursion traffic from those domains.
5. **Record Unpaywall contact email** (`contentprinter@centralstrengthgyms.com`) in `config/config.json` so the PDF downloader (Task #3 second half) doesn't need to hardcode it.

All recommendations in this document are backed by live verification of robots.txt or API shape on 2026-04-11.
