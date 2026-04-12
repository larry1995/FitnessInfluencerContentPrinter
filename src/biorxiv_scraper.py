"""
bioRxiv Scraper for Central Strength Gym
Fetches exercise physiology, nutrition, and sports science preprints
from the bioRxiv API (api.biorxiv.org).
"""

import json
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from http_utils import create_session, get as http_get

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize

BIORXIV_API_BASE = "https://api.biorxiv.org"

_session = create_session()


def load_config():
    with open(CONFIG_DIR / "config.json") as f:
        config = json.load(f)
    with open(CONFIG_DIR / "sources.json") as f:
        sources = json.load(f)
    return config, sources


def content_hash(text):
    """Generate hash to avoid duplicate content."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def fetch_biorxiv_preprints(interval_days=30, cursor=0, page_size=30):
    """Fetch recent bioRxiv preprints within a date interval.

    Uses the /details endpoint which returns preprints by posted date range.
    """
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=interval_days)).strftime("%Y-%m-%d")

    url = f"{BIORXIV_API_BASE}/details/biorxiv/{start_date}/{end_date}/{cursor}/{page_size}"

    try:
        resp = http_get(_session, url, timeout=30)
        data = resp.json()
        return data.get("collection", [])
    except Exception as e:
        print(f"  [ERROR] bioRxiv API request failed: {e}")
        return []


def is_relevant_preprint(preprint, keywords):
    """Check if a preprint matches our target keywords."""
    text = " ".join([
        preprint.get("title", ""),
        preprint.get("abstract", ""),
        preprint.get("category", ""),
    ]).lower()

    for keyword in keywords:
        if keyword.lower() in text:
            return True
    return False


def determine_topic(preprint, topics):
    """Determine which topic a preprint best fits into."""
    text = " ".join([
        preprint.get("title", ""),
        preprint.get("abstract", ""),
    ]).lower()

    best_topic = None
    best_count = 0

    for topic_name, topic_info in topics.items():
        count = sum(1 for kw in topic_info["keywords"] if kw.lower() in text)
        if count > best_count:
            best_count = count
            best_topic = topic_name

    return best_topic or "training"


def scrape_biorxiv():
    """Main function -- fetch relevant preprints from bioRxiv."""
    config, sources = load_config()
    settings = config["scrape_settings"]
    topics = sources["topics"]

    biorxiv_config = sources.get("biorxiv_settings", {})
    if not biorxiv_config:
        print("[WARN] No biorxiv_settings defined in sources.json. Skipping bioRxiv.")
        return []

    keywords = biorxiv_config.get("keywords", [])
    categories = biorxiv_config.get("categories", [])
    interval_days = biorxiv_config.get("interval_days", 30)
    max_results = biorxiv_config.get("max_results", 20)

    raw_dir = POSTS_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Load seen hashes
    seen_file = POSTS_DIR / ".seen_biorxiv_hashes.json"
    if seen_file.exists():
        with open(seen_file) as f:
            seen_hashes = set(json.load(f))
    else:
        seen_hashes = set()

    all_preprints = []

    print(f"\n{'='*60}")
    print(f"  BIORXIV SCRAPER -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    print(f"[CONFIG] Searching last {interval_days} days")
    print(f"  Keywords: {', '.join(keywords[:5])}...")
    print(f"  Categories: {', '.join(categories)}")

    # Fetch preprints in pages
    cursor = 0
    page_size = 100  # bioRxiv API max per page
    fetched_total = 0

    while fetched_total < max_results * 5:  # Fetch enough to filter from
        time.sleep(1)  # Rate limiting
        print(f"\n  Fetching page at cursor {cursor}...")
        preprints = fetch_biorxiv_preprints(
            interval_days=interval_days,
            cursor=cursor,
            page_size=page_size,
        )

        if not preprints:
            print("  No more preprints available.")
            break

        fetched_total += len(preprints)
        print(f"  Retrieved {len(preprints)} preprints (total fetched: {fetched_total})")

        for preprint in preprints:
            if len(all_preprints) >= max_results:
                break

            # Filter by category if specified
            category = preprint.get("category", "")
            if categories and category not in categories:
                # Also check by keyword if category doesn't match
                if not is_relevant_preprint(preprint, keywords):
                    continue
            elif not is_relevant_preprint(preprint, keywords):
                continue

            doi = preprint.get("doi", "")
            h = content_hash(f"biorxiv:{doi}")
            if h in seen_hashes:
                continue

            # Parse authors (bioRxiv returns semicolon-separated string)
            authors_raw = preprint.get("authors", "")
            authors = [a.strip() for a in authors_raw.split(";") if a.strip()]

            topic = determine_topic(preprint, topics)

            entry = {
                "title": preprint.get("title", ""),
                "url": f"https://doi.org/{doi}" if doi else "",
                "source": "bioRxiv (preprint)",
                "source_type": "biorxiv",
                "topic": topic,
                "summary": preprint.get("abstract", "")[:500],
                "full_text": preprint.get("abstract", "")[:20000],
                "structured_content": {
                    "doi": doi,
                    "authors": authors,
                    "posted_date": preprint.get("date", ""),
                    "category": category,
                    "version": preprint.get("version", ""),
                    "jatsxml": preprint.get("jatsxml", ""),
                },
                "scraped_at": datetime.now().isoformat(),
                "hash": h,
            }

            all_preprints.append(entry)
            seen_hashes.add(h)
            print(f"  [OK] {preprint.get('title', '')[:70]}...")

        if len(all_preprints) >= max_results:
            break

        cursor += page_size

    # Save results
    if all_preprints:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = raw_dir / f"biorxiv_{timestamp}.json"
        with open(outfile, "w") as f:
            json.dump(all_preprints, f, indent=2)
        print(f"\n[SAVED] {len(all_preprints)} bioRxiv preprints -> {outfile}")

        with open(seen_file, "w") as f:
            json.dump(list(seen_hashes), f)
    else:
        print("\n[INFO] No new relevant bioRxiv preprints found.")

    print(f"\n{'='*60}\n")
    return all_preprints


if __name__ == "__main__":
    preprints = scrape_biorxiv()
    print(f"Total bioRxiv preprints scraped: {len(preprints)}")
