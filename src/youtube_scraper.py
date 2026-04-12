"""
YouTube Scraper for Central Strength Gym
Fetches recent videos from science-based fitness channels,
downloads transcripts, and extracts key content for Instagram posts.
"""

import json
import os
import re
import subprocess
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
POSTS_DIR = PROJECT_ROOT / "work"  # internal scratch; final output in Posts/ via output_layout.finalize


def load_youtube_config():
    with open(CONFIG_DIR / "youtube_sources.json") as f:
        return json.load(f)

def load_config():
    with open(CONFIG_DIR / "config.json") as f:
        return json.load(f)


def get_recent_videos(channel_url, max_videos=3):
    """Fetch recent video metadata from a YouTube channel using yt-dlp."""
    try:
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--flat-playlist",
            "--playlist-end", str(max_videos),
            channel_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            stderr = result.stderr.strip()
            print(f"  [WARN] yt-dlp exited with code {result.returncode} for {channel_url}")
            if stderr:
                print(f"  [WARN] stderr: {stderr[:300]}")

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                videos.append({
                    "id": data.get("id", ""),
                    "title": data.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
                    "description": data.get("description", "")[:1000],
                    "duration": data.get("duration") or 0,
                    "upload_date": data.get("upload_date", ""),
                    "view_count": data.get("view_count") or 0,
                    "channel": data.get("channel") or data.get("uploader") or data.get("channel_id") or "",
                })
            except json.JSONDecodeError:
                continue
        return videos
    except Exception as e:
        print(f"  [ERROR] Failed to fetch videos: {e}")
        return []


def download_transcript(video_id, output_dir):
    """Download auto-generated or manual subtitles for a video."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    vtt_path = output_dir / f"{video_id}.en.vtt"

    # Skip if already downloaded
    if vtt_path.exists():
        return vtt_path

    try:
        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--sub-lang", "en",
            "--skip-download",
            "--sub-format", "vtt",
            "-o", str(output_dir / "%(id)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0 and result.stderr.strip():
            print(f"    [WARN] yt-dlp auto-sub failed: {result.stderr.strip()[:200]}")

        if vtt_path.exists():
            return vtt_path

        # Try without auto-sub (manual subs)
        cmd[1] = "--write-sub"
        result2 = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result2.returncode != 0 and result2.stderr.strip():
            print(f"    [WARN] yt-dlp manual-sub failed: {result2.stderr.strip()[:200]}")

        if vtt_path.exists():
            return vtt_path

        print(f"    [WARN] No transcript available for {video_id}")
        return None
    except Exception as e:
        print(f"  [ERROR] Failed to download transcript for {video_id}: {e}")
        return None


def parse_vtt_to_text(vtt_path):
    """Parse VTT subtitle file to clean plain text."""
    with open(vtt_path, "r") as f:
        content = f.read()

    # Remove VTT header
    content = re.sub(r"WEBVTT.*?\n\n", "", content, flags=re.DOTALL)

    # Remove timestamps
    content = re.sub(r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*?\n", "", content)

    # Remove HTML-like tags from VTT
    content = re.sub(r"<[^>]+>", "", content)

    # Remove position/alignment markers
    content = re.sub(r"align:\w+ position:\d+%", "", content)

    # Remove duplicate lines (VTT repeats lines across cues)
    lines = content.split("\n")
    seen = set()
    unique_lines = []
    for line in lines:
        line = line.strip()
        if line and line not in seen and not re.match(r"^\d+$", line):
            seen.add(line)
            unique_lines.append(line)

    return " ".join(unique_lines)


def extract_key_segments(transcript, max_length=3000):
    """Extract the most content-rich segments from a transcript."""
    if len(transcript) <= max_length:
        return transcript

    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', transcript)

    # Score sentences by information density
    science_keywords = [
        "study", "research", "found", "evidence", "data", "percent",
        "increase", "decrease", "muscle", "strength", "protein",
        "training", "volume", "intensity", "sets", "reps",
        "hypertrophy", "technique", "form", "mistake", "tip",
        "important", "key", "recommend", "should", "better",
        "optimal", "effective", "benefit", "risk", "avoid",
        "squat", "bench", "deadlift", "press", "pull",
        "nutrition", "calories", "recovery", "sleep", "programming",
    ]

    scored = []
    for i, sent in enumerate(sentences):
        score = sum(1 for kw in science_keywords if kw in sent.lower())
        # Bonus for medium-length sentences (not too short, not rambling)
        if 40 < len(sent) < 200:
            score += 1
        scored.append((score, i, sent))

    # Sort by score, take the best
    scored.sort(key=lambda x: x[0], reverse=True)

    selected = []
    total_len = 0
    for score, idx, sent in scored:
        if total_len + len(sent) > max_length:
            break
        selected.append((idx, sent))
        total_len += len(sent)

    # Re-sort by original order to preserve narrative flow
    selected.sort(key=lambda x: x[0])
    return " ".join(sent for _, sent in selected)


def summarize_for_instagram(video, transcript_text, topics):
    """Create a structured summary suitable for Instagram post drafting."""

    # Determine topic
    title_lower = video["title"].lower()
    desc_lower = (video.get("description", "") + " " + transcript_text[:500]).lower()
    combined = title_lower + " " + desc_lower

    detected_topic = "training"  # default
    for topic_name, topic_info in topics.items():
        for keyword in topic_info["keywords"]:
            if keyword.lower() in combined:
                detected_topic = topic_name
                break

    # Extract key content
    key_content = extract_key_segments(transcript_text)

    summary = {
        "video_id": video["id"],
        "title": video["title"],
        "url": video["url"],
        "channel": video["channel"],
        "duration_min": round(video.get("duration", 0) / 60, 1),
        "views": video.get("view_count", 0),
        "topic": detected_topic,
        "transcript_excerpt": key_content,
        "source_type": "youtube",
        "scraped_at": datetime.now().isoformat(),
    }

    return summary


def scrape_youtube():
    """Main function — scrape recent videos from science-based fitness channels."""
    yt_config = load_youtube_config()
    config = load_config()

    # Load sources.json for topic keywords
    with open(CONFIG_DIR / "sources.json") as f:
        sources = json.load(f)
    topics = sources["topics"]

    raw_dir = POSTS_DIR / "raw"
    transcripts_dir = POSTS_DIR / "transcripts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # Load seen hashes
    seen_file = POSTS_DIR / ".seen_yt_hashes.json"
    if seen_file.exists():
        with open(seen_file) as f:
            seen_hashes = set(json.load(f))
    else:
        seen_hashes = set()

    all_videos = []

    print(f"\n{'='*60}")
    print(f"  YOUTUBE SCRAPER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    for channel in yt_config["channels"]:
        name = channel["name"]
        url = channel["url"]
        max_vids = channel.get("max_videos", 3)

        print(f"[CHANNEL] {name}")
        print(f"  URL: {url}")

        videos = get_recent_videos(url, max_videos=max_vids)
        print(f"  Found {len(videos)} videos")

        for video in videos:
            vid_id = video["id"]

            if vid_id in seen_hashes:
                print(f"  [SKIP] Already seen: {video['title'][:50]}...")
                continue

            # Filter by duration (skip very short or very long)
            duration_min = video.get("duration", 0) / 60
            if duration_min < 2 or duration_min > 90:
                print(f"  [SKIP] Duration out of range ({duration_min:.0f} min): {video['title'][:50]}...")
                continue

            # Set channel name from config if yt-dlp didn't provide it
            if not video.get("channel"):
                video["channel"] = name

            print(f"  [FETCH] {video['title'][:55]}... ({duration_min:.0f} min)")

            # Download transcript
            vtt_path = download_transcript(vid_id, transcripts_dir)

            if vtt_path and vtt_path.exists():
                transcript_text = parse_vtt_to_text(vtt_path)
                print(f"    Transcript: {len(transcript_text)} chars")
            else:
                # Fall back to description only
                transcript_text = video.get("description", "")
                print(f"    No transcript available, using description")

            if len(transcript_text) < 100:
                print(f"    [SKIP] Content too short")
                continue

            summary = summarize_for_instagram(video, transcript_text, topics)
            all_videos.append(summary)
            seen_hashes.add(vid_id)

            time.sleep(2)  # Rate limiting

        print()

    # Save results
    if all_videos:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        outfile = raw_dir / f"youtube_{timestamp}.json"
        with open(outfile, "w") as f:
            json.dump(all_videos, f, indent=2)
        print(f"[SAVED] {len(all_videos)} video summaries → {outfile}")

        with open(seen_file, "w") as f:
            json.dump(list(seen_hashes), f)
    else:
        print("[INFO] No new videos found.")

    print(f"\n{'='*60}\n")
    return all_videos


if __name__ == "__main__":
    videos = scrape_youtube()
    print(f"Total videos scraped: {len(videos)}")
