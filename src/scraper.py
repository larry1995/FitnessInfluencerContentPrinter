"""
Content Scraper for Central Strength Gym
Scrapes powerlifting, training, and nutrition content from RSS feeds and blogs.
Modeled after MoneyPrinterV2 architecture.
"""

import json
import os
import re
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from http_utils import create_session, get as http_get

# Try feedparser, fall back to raw XML parsing
try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "Posts"


def load_config():
    with open(CONFIG_DIR / "config.json") as f:
        config = json.load(f)
    with open(CONFIG_DIR / "sources.json") as f:
        sources = json.load(f)
    return config, sources


_session = create_session()


def fetch_rss_feed(feed_url, timeout=15):
    """Fetch and parse an RSS feed."""
    try:
        resp = http_get(_session, feed_url, timeout=timeout)
        if HAS_FEEDPARSER:
            return feedparser.parse(resp.text)
        else:
            return parse_rss_xml(resp.text)
    except Exception as e:
        print(f"  [ERROR] Failed to fetch {feed_url}: {e}")
        return None


def parse_rss_xml(xml_text):
    """Fallback RSS parser using BeautifulSoup when feedparser is unavailable."""
    soup = BeautifulSoup(xml_text, "html.parser")
    entries = []
    for item in soup.find_all("item"):
        entry = {
            "title": item.find("title").get_text(strip=True) if item.find("title") else "",
            "link": item.find("link").get_text(strip=True) if item.find("link") else "",
            "summary": "",
            "published": "",
        }
        desc = item.find("description")
        if desc:
            entry["summary"] = BeautifulSoup(desc.get_text(), "html.parser").get_text(strip=True)
        pub = item.find("pubdate") or item.find("published") or item.find("dc:date")
        if pub:
            entry["published"] = pub.get_text(strip=True)
        entries.append(entry)

    class FeedResult:
        pass

    class Entry:
        def __init__(self, data):
            for k, v in data.items():
                setattr(self, k, v)

    result = FeedResult()
    result.entries = [Entry(e) for e in entries]
    return result


def extract_structured_content(soup_element):
    """Extract structured content preserving headings, lists, and tables."""
    structured = {
        "sections": [],
        "lists": [],
        "tables": [],
    }

    # Extract heading-content pairs
    for heading in soup_element.find_all(re.compile(r'^h[2-4]$')):
        section = {"heading": heading.get_text(strip=True), "content": ""}
        # Collect sibling text until next heading
        content_parts = []
        for sibling in heading.find_next_siblings():
            if sibling.name and re.match(r'^h[1-4]$', sibling.name):
                break
            text = sibling.get_text(separator=" ", strip=True)
            if text:
                content_parts.append(text)
        section["content"] = "\n".join(content_parts)
        if section["content"]:
            structured["sections"].append(section)

    # Extract ordered/unordered lists with context
    for ul in soup_element.find_all(["ul", "ol"]):
        items = [li.get_text(strip=True) for li in ul.find_all("li", recursive=False) if li.get_text(strip=True)]
        if items:
            # Get preceding heading or paragraph as context
            prev = ul.find_previous(["h2", "h3", "h4", "p", "strong"])
            context = prev.get_text(strip=True) if prev else ""
            structured["lists"].append({"context": context[:200], "items": items})

    # Extract tables (dosage charts, program tables, etc.)
    for table in soup_element.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            structured["tables"].append(rows)

    return structured


def fetch_article_content(url, timeout=15):
    """Fetch full article text and structured content from a blog URL."""
    try:
        resp = http_get(_session, url, timeout=timeout)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                         "form", "iframe", "noscript"]):
            tag.decompose()

        # Try common article containers
        article = (
            soup.find("article")
            or soup.find("div", class_=re.compile(r"(post|article|content|entry)[-_]?(body|content|text)?", re.I))
            or soup.find("main")
        )

        container = article if article else soup

        # Extract structured content (headings, lists, tables)
        structured = extract_structured_content(container)

        # Get full text
        text = container.get_text(separator="\n", strip=True)

        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        full_text = "\n".join(lines)

        return full_text, structured

    except Exception as e:
        print(f"  [ERROR] Failed to fetch article {url}: {e}")
        return "", {}


def is_relevant(title, summary, topics):
    """Check if an article is relevant to our target topics."""
    text = (title + " " + summary).lower()
    for topic_name, topic_info in topics.items():
        for keyword in topic_info["keywords"]:
            if keyword.lower() in text:
                return True, topic_name
    return False, None


def content_hash(text):
    """Generate hash to avoid duplicate content."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def scrape_all_feeds():
    """Main scraping function — fetches articles from all RSS feeds."""
    config, sources = load_config()
    settings = config["scrape_settings"]
    topics = sources["topics"]

    raw_dir = POSTS_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Load existing hashes to avoid duplicates
    seen_file = POSTS_DIR / ".seen_hashes.json"
    if seen_file.exists():
        with open(seen_file) as f:
            seen_hashes = set(json.load(f))
    else:
        seen_hashes = set()

    all_articles = []
    cutoff = datetime.now() - timedelta(days=settings["max_age_days"])

    print(f"\n{'='*60}")
    print(f"  CONTENT SCRAPER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    for feed_info in sources["rss_feeds"]:
        name = feed_info["name"]
        url = feed_info["url"]
        print(f"[FEED] {name}")
        print(f"  URL: {url}")

        feed = fetch_rss_feed(url, timeout=settings["request_timeout"])
        if not feed:
            continue

        entries = feed.entries[:settings["max_articles_per_feed"]]
        print(f"  Found {len(entries)} entries")

        for entry in entries:
            title = getattr(entry, "title", "")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "")

            if not title or not link:
                continue

            # Check relevance
            relevant, topic = is_relevant(title, summary, topics)
            if not relevant:
                print(f"  [SKIP] Not relevant: {title[:60]}...")
                continue

            # Check duplicate
            h = content_hash(title + link)
            if h in seen_hashes:
                print(f"  [SKIP] Already seen: {title[:60]}...")
                continue

            print(f"  [FETCH] {title[:60]}... (topic: {topic})")

            # Fetch full article with structured content
            time.sleep(settings["request_delay_seconds"])
            full_text, structured = fetch_article_content(link, timeout=settings["request_timeout"])

            if len(full_text) < settings["min_content_length"]:
                print(f"  [SKIP] Content too short ({len(full_text)} chars)")
                continue

            article = {
                "title": title,
                "url": link,
                "source": name,
                "topic": topic,
                "summary": summary[:500],
                "full_text": full_text[:20000],
                "structured_content": structured,
                "scraped_at": datetime.now().isoformat(),
                "hash": h,
            }

            all_articles.append(article)
            seen_hashes.add(h)

        print()

    # Save raw articles
    if all_articles:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = raw_dir / f"scraped_{timestamp}.json"
        with open(outfile, "w") as f:
            json.dump(all_articles, f, indent=2)
        print(f"\n[SAVED] {len(all_articles)} articles → {outfile}")

        # Update seen hashes
        with open(seen_file, "w") as f:
            json.dump(list(seen_hashes), f)
    else:
        print("\n[INFO] No new relevant articles found.")

    print(f"\n{'='*60}\n")
    return all_articles


if __name__ == "__main__":
    articles = scrape_all_feeds()
    print(f"Total articles scraped: {len(articles)}")
