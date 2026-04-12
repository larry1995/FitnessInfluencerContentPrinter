"""Tests for the shared Posts/ layout helpers (tasks #11, #12)."""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


def test_merge_meta_creates_when_no_existing():
    from posts_layout import merge_meta
    new = {"post_number": 1, "topic_slug": "foo", "tags": ["#a"]}
    merged = merge_meta(None, new)
    assert merged == new
    merged["topic_slug"] = "bar"
    assert new["topic_slug"] == "foo"


def test_merge_meta_preserves_hand_edited_tags_and_references():
    from posts_layout import merge_meta
    existing = {
        "post_number": 1,
        "topic_slug": "nutrition_vegan_creatine",
        "tags": ["#Curated", "#ByHand"],
        "references": [{"citation": "hand-curated ref"}],
        "topic_label": "NUTRITION (reclassified)",
    }
    new = {
        "post_number": 1,
        "topic_slug": "nutrition_vegan_creatine",
        "tags": [],
        "references": [],
        "topic_label": "",
        "drafted_at": "2026-04-12T01:00:00",
    }
    merged = merge_meta(existing, new)
    assert merged["tags"] == ["#Curated", "#ByHand"]
    assert merged["references"] == [{"citation": "hand-curated ref"}]
    assert merged["topic_label"] == "NUTRITION (reclassified)"
    assert merged["drafted_at"] == "2026-04-12T01:00:00"


def test_merge_meta_update_keys_always_win():
    from posts_layout import merge_meta
    existing = {"post_number": 1, "topic_slug": "old_slug", "has_chinese": False}
    new = {"post_number": 1, "topic_slug": "new_slug", "has_chinese": True}
    merged = merge_meta(existing, new)
    assert merged["topic_slug"] == "new_slug"
    assert merged["has_chinese"] is True


def test_merge_meta_fills_empty_preserve_keys_from_new():
    from posts_layout import merge_meta
    existing = {"post_number": 1, "tags": []}
    new = {"post_number": 1, "tags": ["#Auto"], "source_url": "https://example.com"}
    merged = merge_meta(existing, new)
    assert merged["tags"] == ["#Auto"]
    assert merged["source_url"] == "https://example.com"


def test_merge_meta_preserves_unknown_extension_keys():
    from posts_layout import merge_meta
    existing = {"post_number": 1, "future_field": {"experimental": True}}
    new = {"post_number": 1}
    merged = merge_meta(existing, new)
    assert merged["future_field"] == {"experimental": True}


def test_resolve_topic_slug_rounds_trip_via_existing_meta(tmp_path, monkeypatch):
    from posts_layout import resolve_topic_slug
    import posts_layout
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    migrated = posts_dir / "nutrition_vegan_creatine"
    migrated.mkdir()
    (migrated / "meta.json").write_text(json.dumps({
        "post_number": 1,
        "topic_slug": "nutrition_vegan_creatine",
        "source_url": "https://barbend.com/creatine-vegan/",
    }), encoding="utf-8")
    monkeypatch.setattr(posts_layout, "POSTS_DIR", posts_dir)

    post = {
        "topic": "nutrition",
        "title": "Creatine for vegans: what recent research actually shows",
        "source_url": "https://barbend.com/creatine-vegan/",
    }
    slug = resolve_topic_slug(post)
    assert slug == "nutrition_vegan_creatine"


def test_resolve_topic_slug_falls_back_to_derivation_for_new_content(tmp_path, monkeypatch):
    from posts_layout import resolve_topic_slug
    import posts_layout
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(posts_layout, "POSTS_DIR", posts_dir)

    post = {"topic": "training", "title": "New Program Alpha", "source_url": ""}
    slug = resolve_topic_slug(post)
    assert slug.startswith("training_new_program")


def test_slug_from_source_url_returns_none_for_nonmatch(tmp_path, monkeypatch):
    from posts_layout import slug_from_source_url
    import posts_layout
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    monkeypatch.setattr(posts_layout, "POSTS_DIR", posts_dir)
    assert slug_from_source_url("https://unknown.example.com") is None


def test_slug_from_source_url_ignores_tracking_params_and_fragments(tmp_path, monkeypatch):
    """Reddit/RSS re-scrapes shouldn't orphan existing topics just because
    the URL picked up a `?utm_source=feed` or a `#comments` anchor."""
    from posts_layout import slug_from_source_url
    import posts_layout
    posts_dir = tmp_path / "Posts"
    posts_dir.mkdir()
    existing = posts_dir / "nutrition_vegan_creatine"
    existing.mkdir()
    (existing / "meta.json").write_text(json.dumps({
        "post_number": 1,
        "topic_slug": "nutrition_vegan_creatine",
        "source_url": "https://barbend.com/creatine-vegan/",
    }), encoding="utf-8")
    monkeypatch.setattr(posts_layout, "POSTS_DIR", posts_dir)

    assert slug_from_source_url(
        "https://barbend.com/creatine-vegan/?utm_source=feed"
    ) == "nutrition_vegan_creatine"
    assert slug_from_source_url(
        "https://barbend.com/creatine-vegan#comments"
    ) == "nutrition_vegan_creatine"
    assert slug_from_source_url(
        "HTTPS://BarBend.com/creatine-vegan/"
    ) == "nutrition_vegan_creatine"
