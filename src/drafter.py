"""
Instagram Post Drafter for Central Strength Gym
Takes scraped articles and drafts Instagram-ready posts.
Uses Claude Code as the AI engine (run via CLI), or generates template-based drafts.
"""

import json
import os
import random
import re
import textwrap
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from posts_layout import merge_meta, resolve_topic_slug

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize


def load_config():
    with open(CONFIG_DIR / "config.json") as f:
        config = json.load(f)
    with open(CONFIG_DIR / "sources.json") as f:
        sources = json.load(f)
    return config, sources


def load_latest_articles():
    """Load the most recent scraped articles from both RSS and YouTube."""
    raw_dir = POSTS_DIR / "raw"
    if not raw_dir.exists():
        return []

    all_articles = []

    # Load RSS articles
    rss_files = sorted(raw_dir.glob("scraped_*.json"), reverse=True)
    if rss_files:
        with open(rss_files[0]) as f:
            all_articles.extend(json.load(f))

    # Load YouTube video summaries
    yt_files = sorted(raw_dir.glob("youtube_*.json"), reverse=True)
    if yt_files:
        with open(yt_files[0]) as f:
            yt_data = json.load(f)
        # Convert YouTube format to article format for the drafter
        for vid in yt_data:
            article = {
                "title": vid["title"],
                "url": vid["url"],
                "source": f"{vid['channel']} (YouTube)",
                "topic": vid.get("topic", "training"),
                "summary": vid.get("transcript_excerpt", "")[:500],
                "full_text": vid.get("transcript_excerpt", ""),
                "scraped_at": vid.get("scraped_at", ""),
                "hash": vid.get("video_id", ""),
                "source_type": "youtube",
                "duration_min": vid.get("duration_min", 0),
                "views": vid.get("views", 0),
            }
            all_articles.append(article)

    return all_articles


def extract_key_points(article):
    """Extract key takeaways from article text."""
    text = article["full_text"]
    lines = text.split("\n")

    key_points = []
    # Priority 1: Extract from structured sections (headings with content)
    structured = article.get("structured_content", {})
    if structured and structured.get("sections"):
        for sec in structured["sections"][:8]:
            heading = sec["heading"].strip()
            content = sec["content"].strip()
            if heading and content and len(content) > 30:
                combined = f"{heading}: {content[:300]}"
                key_points.append(combined)
            if len(key_points) >= 8:
                break

    # Priority 2: Extract from structured lists
    if len(key_points) < 4 and structured and structured.get("lists"):
        for lst in structured["lists"]:
            for item in lst["items"]:
                if len(item) > 20 and item not in key_points:
                    key_points.append(item)
                if len(key_points) >= 8:
                    break

    # Priority 3: Fall back to text scanning
    if len(key_points) < 4:
        for line in lines:
            line = line.strip()
            if not line or len(line) < 20:
                continue
            if (line.startswith(("•", "-", "–", "►", "✓", "1", "2", "3", "4", "5"))
                or (30 < len(line) < 300 and any(kw in line.lower() for kw in
                    ["study", "research", "found", "shows", "increase", "decrease",
                     "improve", "percent", "tip", "key", "important", "recommend",
                     "dose", "dosage", "mg", "grams", "sets", "reps", "weeks",
                     "program", "supplement", "evidence", "meta-analysis", "trial",
                     "significantly", "optimal", "recommended", "protocol"]))):
                if line not in key_points:
                    key_points.append(line)
            if len(key_points) >= 8:
                break

    return key_points


def extract_specific_data(article):
    """Extract specific numbers, dosages, study findings, and program parameters."""
    text = article["full_text"]
    data = {
        "dosages": [],
        "study_findings": [],
        "program_params": [],
        "practical_tips": [],
    }

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Dosages and measurements
        if re.search(r'\d+\s*(mg|g|iu|mcg|ml|oz|cups?|scoops?)\b', line, re.I):
            data["dosages"].append(line[:300])

        # Study findings with statistics
        if re.search(r'(study|trial|meta-analysis|research|review)\b.*\d', line, re.I):
            data["study_findings"].append(line[:300])

        # Program parameters (sets, reps, weeks, phases)
        if re.search(r'(\d+\s*x\s*\d+|\d+\s*sets?|\d+\s*reps?|week\s*\d|phase\s*\d|RPE\s*\d)', line, re.I):
            data["program_params"].append(line[:300])

        # Practical recommendations
        if re.search(r'^[-•]\s*(take|use|eat|drink|try|avoid|aim|start|do|don\'t|consider)\b', line, re.I):
            data["practical_tips"].append(line.lstrip("-• ").strip()[:200])

    # Deduplicate and cap
    for k in data:
        seen = set()
        unique = []
        for item in data[k]:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        data[k] = unique[:6]

    return data


def draft_post_template(article, brand, post_number):
    """Generate an Instagram post draft from an article."""
    key_points = extract_key_points(article)
    specific_data = extract_specific_data(article)

    # Topic-specific emoji mapping
    emoji_map = {
        "training": "🏋️",
        "nutrition": "🥩",
        "techniques": "⚙️",
    }
    topic_emoji = emoji_map.get(article.get("topic", ""), "💪")

    # Build the caption
    caption_parts = []

    # Hook line (attention-grabbing first line)
    caption_parts.append(f"{topic_emoji} {article['title'].upper()}\n")

    # Summary / intro
    if article.get("summary"):
        # Strip HTML tags from RSS summary
        summary = BeautifulSoup(article["summary"], "html.parser").get_text(strip=True)
        summary = summary[:500]
        if len(article["summary"]) > 500:
            summary = summary.rsplit(" ", 1)[0] + "..."
        caption_parts.append(f"{summary}\n")

    # Key takeaways with detailed bodies
    if key_points:
        caption_parts.append("KEY FINDINGS:\n")
        for i, point in enumerate(key_points[:6], 1):
            # Clean and preserve more detail
            point = point.lstrip("•-–►✓0123456789.) ").strip()
            if ":" in point and len(point.split(":", 1)[0]) < 60:
                headline, body = point.split(":", 1)
                caption_parts.append(f"{i}. {headline.strip().upper()}")
                caption_parts.append(f"{body.strip()[:300]}")
            else:
                if len(point) > 300:
                    point = point[:297] + "..."
                caption_parts.append(f"{i}. {point}")
            caption_parts.append("")

    # Specific dosages / program parameters
    if specific_data["dosages"] or specific_data["program_params"]:
        items = specific_data["dosages"] or specific_data["program_params"]
        label = "DOSAGE & PROTOCOL:" if specific_data["dosages"] else "PROGRAM DETAILS:"
        caption_parts.append(f"\n{label}")
        for item in items[:4]:
            caption_parts.append(f"- {item}")
        caption_parts.append("")

    # Practical tips
    if specific_data["practical_tips"]:
        caption_parts.append("\nPRACTICAL GUIDE:")
        for tip in specific_data["practical_tips"][:6]:
            caption_parts.append(f"- {tip}")
        caption_parts.append("")

    # Summary line from study findings
    if specific_data["study_findings"]:
        caption_parts.append("\nTHE BOTTOM LINE:")
        caption_parts.append(specific_data["study_findings"][0][:300])
        caption_parts.append("")

    # CTA
    cta = random.choice(brand["cta_options"])
    caption_parts.append(f"👉 {cta}\n")

    # Hashtags
    topic_hashtags = {
        "training": ["#PowerliftingTraining", "#StrengthProgram", "#ScienceBasedTraining", "#ProgressiveOverload", "#StrengthCoaching"],
        "nutrition": ["#FitnessNutrition", "#MacroFriendly", "#ProteinGoals", "#EatForStrength", "#NutritionScience"],
        "techniques": ["#LiftingForm", "#SquatTechnique", "#DeadliftTips", "#BenchPressTips", "#MovementQuality"],
    }
    tags = brand["hashtags"].copy()
    tags.extend(topic_hashtags.get(article.get("topic", ""), ["#Fitness", "#Strength"]))
    tags.extend(["#Powerlifting", "#StrengthTraining", "#GymLife", "#FitnessMotivation"])
    # Deduplicate and limit
    seen = set()
    unique_tags = []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique_tags.append(t)
    tags = unique_tags[:30]

    caption_parts.append(" ".join(tags))

    caption = "\n".join(caption_parts)

    # Build the post object
    post = {
        "post_number": post_number,
        "topic": article.get("topic", "general"),
        "source": article.get("source", "unknown"),
        "source_url": article.get("url", ""),
        "title": article["title"],
        "caption": caption,
        "key_points": key_points[:4],
        "carousel_slides": generate_carousel_text(article, key_points),
        "suggested_visual": suggest_visual(article),
        "drafted_at": datetime.now().isoformat(),
    }

    return post


def generate_carousel_text(article, key_points):
    """Generate text for Instagram carousel slides."""
    slides = []

    # Slide 1: Title / Hook
    slides.append({
        "slide": 1,
        "type": "title",
        "headline": article["title"],
        "subtext": f"Science-backed insights from {article.get('source', 'experts')}",
    })

    # Slides 2-7: Key points (up to 6)
    for i, point in enumerate(key_points[:6], 2):
        point = point.lstrip("•-–►✓0123456789.) ").strip()
        if ":" in point and len(point.split(":", 1)[0]) < 60:
            headline, body = point.split(":", 1)
            slides.append({
                "slide": i,
                "type": "key_point",
                "headline": headline.strip(),
                "text": body.strip()[:300],
            })
        else:
            slides.append({
                "slide": i,
                "type": "key_point",
                "headline": f"Point #{i-1}",
                "text": point[:300],
            })

    # Final slide: CTA
    slides.append({
        "slide": len(slides) + 1,
        "type": "cta",
        "headline": "Ready to Train?",
        "text": "Central Strength Gym\nSanta Clara, CA\ncentralstrengthgyms.com",
    })

    return slides


def suggest_visual(article):
    """Suggest what kind of visual to use."""
    topic = article.get("topic", "")
    suggestions = {
        "training": "Photo/video of the exercise being discussed, or a training log graphic",
        "nutrition": "Clean food photo, macro breakdown graphic, or meal prep shot",
        "techniques": "Side-by-side form comparison, or slow-mo video of the lift",
    }
    return suggestions.get(topic, "Gym photo or branded quote graphic")


def _topic_slug_for(post: dict) -> str:
    """Derive the per-topic directory slug from a drafted post.

    Delegates to `posts_layout.resolve_topic_slug`, which first checks for an
    existing `meta.json` whose `source_url` matches this post — that way a
    migrated topic (e.g. `nutrition_vegan_creatine`) is round-trip-safe and
    won't spawn a parallel `nutrition_creatine_for_vegans_what_recent_research`
    directory on re-draft.
    """
    return resolve_topic_slug(post)


def _write_post_file(path, post):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{'='*60}\n")
        f.write(f"POST #{post['post_number']} — {post['topic'].upper()}\n")
        f.write(f"Source: {post['source']} ({post['source_url']})\n")
        f.write(f"Drafted: {post['drafted_at']}\n")
        f.write(f"{'='*60}\n\n")
        f.write("CAPTION:\n")
        f.write(f"{'-'*40}\n")
        f.write(post["caption"])
        f.write(f"\n{'-'*40}\n\n")
        f.write("CAROUSEL SLIDES:\n")
        for slide in post.get("carousel_slides", []):
            f.write(f"\n  [Slide {slide['slide']}] {slide.get('headline', '')}\n")
            if slide.get("text"):
                f.write(f"  {slide['text']}\n")
        f.write(f"\nSUGGESTED VISUAL: {post.get('suggested_visual', 'N/A')}\n")


def save_drafts(posts):
    """Save drafted posts.

    Writes the per-topic layout (work/<slug>/en/draft.txt + meta.json) that
    single_page_generator.py consumes, and also mirrors a JSON copy into
    work/drafts/ for downstream steps (image_generator) that still read the
    flat drafts dir.
    """
    drafts_dir = POSTS_DIR / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d")

    for post in posts:
        num = post["post_number"]
        topic = post["topic"]
        slug = _topic_slug_for(post)

        topic_dir = POSTS_DIR / slug
        en_dir = topic_dir / "en"
        pdfs_dir = topic_dir / "pdfs"
        en_dir.mkdir(parents=True, exist_ok=True)
        pdfs_dir.mkdir(parents=True, exist_ok=True)

        _write_post_file(en_dir / "draft.txt", post)

        meta_path = topic_dir / "meta.json"
        new_meta = {
            "post_number": num,
            "topic_slug": slug,
            "topic_label": topic,
            "source_name": post.get("source", ""),
            "source_url": post.get("source_url", ""),
            "title": post.get("title", ""),
            "drafted_at": post.get("drafted_at", ""),
            "has_chinese": (topic_dir / "zh" / "draft.txt").exists(),
        }
        existing_meta = None
        if meta_path.exists():
            try:
                existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing_meta = None
        meta = merge_meta(existing_meta, new_meta)
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        json_name = f"{timestamp}_post{num:02d}_{topic}.json"
        with open(drafts_dir / json_name, "w") as f:
            json.dump(post, f, indent=2)
        _write_post_file(drafts_dir / f"{timestamp}_post{num:02d}_{topic}.txt", post)

        try:
            from chinese_drafter import generate_for_topic
            status = generate_for_topic(topic_dir)
            print(f"  [ZH] {slug}: {status}")
        except Exception as e:
            print(f"  [ZH] {slug}: error — {e}")

    print(f"[SAVED] {len(posts)} drafts → work/<slug>/en/ (and work/drafts/ mirror)")
    return drafts_dir


def draft_all_grounded():
    """Grounded LLM drafting path — Layer 1 of the citation-hallucination fix.

    For each scraped article, calls `generate_grounded_draft` (which extracts
    a verified citation allow-list from the article, sends a constrained
    prompt to the LLM, and runs Layer A + Layer B verification on the
    output). On success, writes the LLM output verbatim to
    `work/<slug>/en/draft.txt` and stamps meta.json with
    `audit_status: "OK"` via `audit_meta_writer.refresh_audit_meta`.

    Three failure modes (logged, skipped, no draft saved):
      - INSUFFICIENT_SOURCE_DATA: source article had no extractable
        citations. A signal file is dropped at `work/.needs_research/<slug>.json`.
      - LLM not configured: no `ANTHROPIC_API_KEY`.
      - DROP: all retries failed allow-list / verify_citations checks.

    Unlike `draft_all`, the grounded path does NOT mirror posts into
    `work/drafts/`, does NOT auto-trigger the Chinese drafter, and does
    NOT touch `weekly_summary_*.json`. Those are pure-template-pipeline
    concerns. The grounded path is strict, citation-safe, and silent on
    everything outside the per-topic directory.
    """
    config, _sources = load_config()
    settings = config["post_settings"]

    articles = load_latest_articles()
    if not articles:
        print("[INFO] No scraped articles found. Run scraper.py first.")
        return []

    from grounded_drafter import generate_grounded_draft

    print(f"\n{'='*60}")
    print(f"  GROUNDED DRAFTER (LLM) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Articles available: {len(articles)}")
    print(f"  Posts to draft: {min(len(articles), settings['posts_per_run'])}")
    print(f"{'='*60}\n")

    saved: list[dict] = []
    for i, article in enumerate(articles[:settings["posts_per_run"]], 1):
        title = article.get("title", "<untitled>")
        print(f"[GROUNDED-DRAFT] #{i}: {title[:60]}...")

        synthetic_post = {
            "post_number": i,
            "topic": article.get("topic", "general"),
            "source": article.get("source", ""),
            "source_url": article.get("url") or article.get("source_url", ""),
            "title": title,
        }
        slug = resolve_topic_slug(synthetic_post)

        draft_text = generate_grounded_draft(article, slug=slug)
        if draft_text is None:
            continue

        topic_dir = POSTS_DIR / slug
        en_dir = topic_dir / "en"
        en_dir.mkdir(parents=True, exist_ok=True)
        (en_dir / "draft.txt").write_text(draft_text, encoding="utf-8")

        meta_path = topic_dir / "meta.json"
        new_meta = {
            "post_number": i,
            "topic_slug": slug,
            "topic_label": synthetic_post["topic"],
            "source_name": synthetic_post["source"],
            "source_url": synthetic_post["source_url"],
            "title": title,
            "drafted_at": datetime.now().isoformat(),
            "drafter": "grounded_llm",
            "has_chinese": (topic_dir / "zh" / "draft.txt").exists(),
        }
        existing_meta = None
        if meta_path.exists():
            try:
                existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing_meta = None
        meta = merge_meta(existing_meta, new_meta)
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        try:
            from audit_meta_writer import refresh_audit_meta
            refresh_audit_meta(slug)
        except Exception as e:
            print(f"  [WARN] refresh_audit_meta({slug}) failed: {e}")

        saved.append({"slug": slug, "title": title})

    print(f"\n[SAVED] {len(saved)} grounded drafts → work/<slug>/en/draft.txt")
    return saved


def draft_all():
    """Main drafting function."""
    config, sources = load_config()
    brand = sources["brand"]
    settings = config["post_settings"]

    articles = load_latest_articles()
    if not articles:
        print("[INFO] No scraped articles found. Run scraper.py first.")
        return []

    print(f"\n{'='*60}")
    print(f"  POST DRAFTER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Articles available: {len(articles)}")
    print(f"  Posts to draft: {min(len(articles), settings['posts_per_run'])}")
    print(f"{'='*60}\n")

    posts = []
    for i, article in enumerate(articles[:settings["posts_per_run"]], 1):
        print(f"[DRAFT] Post #{i}: {article['title'][:50]}...")
        post = draft_post_template(article, brand, i)
        posts.append(post)

    save_drafts(posts)

    # Save weekly summary
    summary_file = POSTS_DIR / f"weekly_summary_{datetime.now().strftime('%Y%m%d')}.json"
    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_posts": len(posts),
        "topics": {t: sum(1 for p in posts if p["topic"] == t) for t in set(p["topic"] for p in posts)},
        "sources": {s: sum(1 for p in posts if p["source"] == s) for s in set(p["source"] for p in posts)},
        "posts": [{"number": p["post_number"], "title": p["title"], "topic": p["topic"]} for p in posts],
    }
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[SUMMARY] {summary_file}")
    return posts
