"""Tests for the raw→per-topic sidecar promotion step (Task #13)."""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


def _reddit_record(**overrides):
    base = {
        "title": "RPE vs percentage training — what does the research say?",
        "url": "https://old.reddit.com/r/powerlifting/comments/fake001/rpe_vs_percentage/",
        "source": "r/powerlifting",
        "topic": "reddit",
        "source_type": "reddit",
        "subreddit": "powerlifting",
        "thread_title": "RPE vs percentage training — what does the research say?",
        "thread_score": 420,
        "thread_permalink": "https://old.reddit.com/r/powerlifting/comments/fake001/rpe_vs_percentage/",
        "op_author": "u/example_user",
        "op_body": "Curious what people think about RPE vs percentage training.",
        "scraped_at": "2026-04-12T01:00:00",
        "reddit_callouts": [
            {
                "author": "u/coachX",
                "score": 412,
                "body": "Both work when volume-equated.",
                "permalink": "https://old.reddit.com/r/.../fake01/",
                "is_op_reply": False,
                "flair": "Verified Coach",
            },
            {
                "author": "u/lifter99",
                "score": 187,
                "body": "Beginners should start with percentages.",
                "permalink": "https://old.reddit.com/r/.../fake02/",
                "is_op_reply": False,
                "flair": None,
            },
        ],
        "evidence_info": {},
    }
    base.update(overrides)
    return base


def test_sanitize_label_strips_emoji_and_caps_length():
    from source_promoter import _sanitize_label
    assert _sanitize_label("Verified Coach 🏋️", 20) == "Verified Coach"
    assert _sanitize_label("🔥🎉", 20) is None
    assert _sanitize_label("   ", 20) is None
    assert _sanitize_label(None, 20) is None
    assert _sanitize_label("A" * 50, 20) == "A" * 20
    assert _sanitize_label("!!!", 20) is None
    assert _sanitize_label("Pro", 20) == "Pro"


def test_promote_reddit_record_creates_full_layout(tmp_path, monkeypatch):
    import source_promoter
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(source_promoter, "POSTS_DIR", posts_dir)
    import posts_layout
    monkeypatch.setattr(posts_layout, "POSTS_DIR", posts_dir)

    record = _reddit_record()
    slug, status = source_promoter.promote_record(record)

    assert status == "created"
    assert slug
    topic_dir = posts_dir / slug
    assert (topic_dir / "en" / "draft.txt").exists()
    assert (topic_dir / "en" / "source.json").exists()
    assert (topic_dir / "meta.json").exists()
    assert (topic_dir / "pdfs").is_dir()

    sidecar = json.loads((topic_dir / "en" / "source.json").read_text())
    assert sidecar["source_type"] == "reddit"
    assert sidecar["subreddit"] == "powerlifting"
    assert sidecar["thread_score"] == 420
    assert sidecar["op_author"] == "u/example_user"
    assert len(sidecar["reddit_callouts"]) == 2
    assert sidecar["reddit_callouts"][0]["flair"] == "Verified Coach"
    assert sidecar["reddit_callouts"][1]["flair"] is None
    assert sidecar["evidence_info"] == {}

    meta = json.loads((topic_dir / "meta.json").read_text())
    assert meta["source_type"] == "reddit"
    assert meta["source_url"] == record["thread_permalink"]
    assert meta["title"] == record["thread_title"]

    draft = (topic_dir / "en" / "draft.txt").read_text()
    assert "REDDIT THREAD" in draft
    assert "r/powerlifting" in draft
    assert "u/coachX" in draft
    assert "Verified Coach" in draft
    assert "auto-seeded" in draft


def test_promote_reddit_record_second_run_preserves_edited_draft(tmp_path, monkeypatch):
    import source_promoter
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(source_promoter, "POSTS_DIR", posts_dir)
    import posts_layout
    monkeypatch.setattr(posts_layout, "POSTS_DIR", posts_dir)

    record = _reddit_record()
    slug, _ = source_promoter.promote_record(record)

    draft_path = posts_dir / slug / "en" / "draft.txt"
    draft_path.write_text("HUMAN EDITED CAPTION — DO NOT OVERWRITE\n", encoding="utf-8")

    slug2, status2 = source_promoter.promote_record(record)
    assert slug2 == slug
    assert status2 == "updated"
    assert draft_path.read_text() == "HUMAN EDITED CAPTION — DO NOT OVERWRITE\n"

    sidecar = json.loads((posts_dir / slug / "en" / "source.json").read_text())
    assert sidecar["source_type"] == "reddit"


def test_promote_reddit_record_caps_callouts_at_four(tmp_path, monkeypatch):
    import source_promoter
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(source_promoter, "POSTS_DIR", posts_dir)
    import posts_layout
    monkeypatch.setattr(posts_layout, "POSTS_DIR", posts_dir)

    callouts = [
        {"author": f"u/user{i}", "score": 100 - i, "body": f"body {i}",
         "permalink": f"https://example.com/{i}", "is_op_reply": False, "flair": None}
        for i in range(10)
    ]
    record = _reddit_record(reddit_callouts=callouts)
    slug, _ = source_promoter.promote_record(record)
    sidecar = json.loads((posts_dir / slug / "en" / "source.json").read_text())
    assert len(sidecar["reddit_callouts"]) == 4


def test_promote_reddit_sanitizes_emoji_flair(tmp_path, monkeypatch):
    import source_promoter
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(source_promoter, "POSTS_DIR", posts_dir)
    import posts_layout
    monkeypatch.setattr(posts_layout, "POSTS_DIR", posts_dir)

    record = _reddit_record(reddit_callouts=[{
        "author": "u/fancy",
        "score": 50,
        "body": "some body",
        "permalink": "",
        "is_op_reply": False,
        "flair": "🔥🎉🏆 Coach 🔥",
    }])
    slug, _ = source_promoter.promote_record(record)
    sidecar = json.loads((posts_dir / slug / "en" / "source.json").read_text())
    assert sidecar["reddit_callouts"][0]["flair"] == "Coach"


def test_promote_skips_records_missing_title(tmp_path, monkeypatch):
    import source_promoter
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(source_promoter, "POSTS_DIR", posts_dir)

    record = _reddit_record(thread_title="", title="")
    slug, status = source_promoter.promote_record(record)
    assert slug == ""
    assert "no title" in status


def test_promote_skips_non_community_records(tmp_path, monkeypatch):
    import source_promoter
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(source_promoter, "POSTS_DIR", posts_dir)

    record = {"source_type": "rss", "title": "Some RSS article"}
    slug, status = source_promoter.promote_record(record)
    assert slug == ""
    assert "source_type" in status


def test_extract_top_callouts_sanitizes_and_caps(tmp_path):
    from reddit_scraper import _extract_top_callouts
    payload = [
        {"data": {"children": [{"data": {"author": "op_user"}}]}},
        {"data": {"children": [
            {"kind": "t1", "data": {
                "author": "coach_bob",
                "score": 500,
                "body": "First callout body.",
                "permalink": "/r/sub/c1",
                "author_flair_text": "Coach 🏋️",
            }},
            {"kind": "t1", "data": {
                "author": "op_user",
                "score": 200,
                "body": "OP replying to themselves.",
                "permalink": "/r/sub/c2",
                "author_flair_text": None,
            }},
            {"kind": "more", "data": {}},  # should be skipped
            {"kind": "t1", "data": {
                "author": "user3",
                "score": 50,
                "body": "Third callout.",
                "permalink": "/r/sub/c3",
                "author_flair_text": "🔥",  # emoji-only, should sanitize to None
            }},
        ]}},
    ]
    callouts = _extract_top_callouts(payload)
    assert len(callouts) == 3
    assert callouts[0]["author"] == "u/coach_bob"
    assert callouts[0]["flair"] == "Coach"
    assert callouts[0]["is_op_reply"] is False
    assert callouts[1]["author"] == "u/op_user"
    assert callouts[1]["is_op_reply"] is True
    assert callouts[2]["flair"] is None
