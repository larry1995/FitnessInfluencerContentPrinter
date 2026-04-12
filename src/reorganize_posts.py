"""
Migrate the flat Posts/ layout to a per-topic structure.

Before:
    Posts/polished/postNN_<slug>.txt
    Posts/single_pages/postNN_<slug>.png
    Posts/chinese/postNN_chinese.txt

After:
    Posts/<slug>/en/draft.txt
    Posts/<slug>/en/single_page.png
    Posts/<slug>/zh/draft.txt
    Posts/<slug>/pdfs/
    Posts/<slug>/meta.json

Idempotent: safe to re-run. Already-migrated topics are skipped.
Run:
    python src/reorganize_posts.py            # migrate
    python src/reorganize_posts.py --dry-run  # show planned moves, no changes
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from posts_layout import merge_meta

PROJECT_ROOT = Path(__file__).parent.parent
POSTS_DIR = PROJECT_ROOT / "Posts"

LEGACY_EN_DIR = POSTS_DIR / "polished"
LEGACY_PNG_DIR = POSTS_DIR / "single_pages"
LEGACY_ZH_DIR = POSTS_DIR / "chinese"

POST_FILENAME_RE = re.compile(r"^post(\d+)_(.+)$")
SOURCE_URL_RE = re.compile(r"https?://[^\s)]+")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s)]+)", re.I)
PMID_RE = re.compile(r"\bPMID[:\s]*(\d+)", re.I)


def discover_posts():
    """Return {post_num: {'slug': str, 'en_txt': Path|None, 'png': Path|None, 'zh_txt': Path|None}}.

    Discovers both legacy flat layout and already-migrated per-topic layout so that
    re-runs can refresh meta.json and fill in any missing pieces.
    """
    posts = {}
    legacy_slug_by_num = {}

    if LEGACY_EN_DIR.exists():
        for f in LEGACY_EN_DIR.glob("post*.txt"):
            m = POST_FILENAME_RE.match(f.stem)
            if not m:
                continue
            num = int(m.group(1))
            slug = m.group(2)
            legacy_slug_by_num[num] = slug
            posts.setdefault(num, {"slug": slug, "en_txt": None, "png": None, "zh_txt": None})
            posts[num]["slug"] = slug
            posts[num]["en_txt"] = f

    if LEGACY_PNG_DIR.exists():
        for f in LEGACY_PNG_DIR.glob("post*.png"):
            m = POST_FILENAME_RE.match(f.stem)
            if not m:
                continue
            num = int(m.group(1))
            slug = m.group(2)
            legacy_slug_by_num.setdefault(num, slug)
            posts.setdefault(num, {"slug": slug, "en_txt": None, "png": None, "zh_txt": None})
            if not posts[num].get("slug"):
                posts[num]["slug"] = slug
            posts[num]["png"] = f

    if LEGACY_ZH_DIR.exists():
        for f in LEGACY_ZH_DIR.glob("post*_chinese.txt"):
            m = re.match(r"^post(\d+)_chinese$", f.stem)
            if not m:
                continue
            num = int(m.group(1))
            posts.setdefault(num, {"slug": None, "en_txt": None, "png": None, "zh_txt": None})
            posts[num]["zh_txt"] = f

    for topic_dir in sorted(POSTS_DIR.iterdir() if POSTS_DIR.exists() else []):
        if not topic_dir.is_dir():
            continue
        if topic_dir.name.startswith("."):
            continue
        en_draft = topic_dir / "en" / "draft.txt"
        png = topic_dir / "en" / "single_page.png"
        zh_draft = topic_dir / "zh" / "draft.txt"
        meta = topic_dir / "meta.json"
        if not (en_draft.exists() or png.exists() or meta.exists()):
            continue
        slug = topic_dir.name
        post_num = None
        if meta.exists():
            try:
                existing = json.loads(meta.read_text(encoding="utf-8"))
                if isinstance(existing.get("post_number"), int):
                    post_num = existing["post_number"]
            except (json.JSONDecodeError, OSError):
                pass
        if post_num is None:
            for num, legacy_slug in legacy_slug_by_num.items():
                if legacy_slug == slug:
                    post_num = num
                    break
        if post_num is None and en_draft.exists():
            try:
                header = en_draft.read_text(encoding="utf-8", errors="replace").splitlines()[:10]
                for line in header:
                    hm = re.search(r"POST\s*#\s*(\d+)", line, re.I)
                    if hm:
                        post_num = int(hm.group(1))
                        break
            except OSError:
                pass
        if post_num is None:
            continue
        entry = posts.setdefault(post_num, {"slug": slug, "en_txt": None, "png": None, "zh_txt": None})
        entry["slug"] = slug
        if entry.get("en_txt") is None and en_draft.exists():
            entry["en_txt"] = en_draft
        if entry.get("png") is None and png.exists():
            entry["png"] = png
        if entry.get("zh_txt") is None and zh_draft.exists():
            entry["zh_txt"] = zh_draft

    return posts


def parse_meta_from_draft(draft_path: Path) -> dict:
    """Extract topic, source name/url, references, and tags from a polished draft file."""
    if not draft_path or not draft_path.exists():
        return {}

    text = draft_path.read_text(encoding="utf-8", errors="replace")
    meta = {
        "source_name": "",
        "source_url": "",
        "topic_label": "",
        "tags": [],
        "references": [],
    }

    for line in text.splitlines()[:12]:
        line = line.strip()
        if line.startswith("POST #") and "—" in line:
            meta["topic_label"] = line.split("—", 1)[1].strip()
        elif line.lower().startswith("source:"):
            src = line.split(":", 1)[1].strip()
            url_m = SOURCE_URL_RE.search(src)
            if url_m:
                meta["source_url"] = url_m.group(0).rstrip(".,)")
                src = SOURCE_URL_RE.sub("", src).strip(" ()")
            meta["source_name"] = src

    tag_matches = re.findall(r"#[A-Za-z][A-Za-z0-9_]*", text)
    seen = set()
    for tag in tag_matches:
        low = tag.lower()
        if low not in seen:
            seen.add(low)
            meta["tags"].append(tag)
        if len(meta["tags"]) >= 30:
            break

    ref_block_match = re.search(r"REFERENCES:\s*\n(.*?)(?:\n-{5,}|\Z)", text, re.DOTALL | re.IGNORECASE)
    if ref_block_match:
        ref_lines = [
            ln.strip()
            for ln in ref_block_match.group(1).splitlines()
            if ln.strip() and not ln.strip().startswith("-")
        ]
        for rl in ref_lines:
            ref = {"citation": rl}
            doi_m = DOI_RE.search(rl)
            if doi_m:
                ref["doi"] = doi_m.group(1).rstrip(".,")
            pmid_m = PMID_RE.search(rl)
            if pmid_m:
                ref["pmid"] = pmid_m.group(1)
            meta["references"].append(ref)

    return meta


def build_meta_json(post_num: int, slug: str, parsed: dict, has_zh: bool) -> dict:
    return {
        "post_number": post_num,
        "topic_slug": slug,
        "topic_label": parsed.get("topic_label", ""),
        "source_name": parsed.get("source_name", ""),
        "source_url": parsed.get("source_url", ""),
        "tags": parsed.get("tags", []),
        "references": parsed.get("references", []),
        "has_chinese": has_zh,
        "migrated_at": datetime.now().isoformat(timespec="seconds"),
    }


def move_file(src: Path, dst: Path, dry_run: bool) -> str:
    """Move src to dst. Returns a status string. Idempotent."""
    if not src or not src.exists():
        if dst.exists():
            return f"already-migrated ({dst.name})"
        return "missing-source"

    try:
        if src.resolve() == dst.resolve():
            return f"already-migrated ({dst.name})"
    except OSError:
        pass

    if dst.exists():
        try:
            if dst.stat().st_size == src.stat().st_size:
                if not dry_run:
                    src.unlink()
                return f"dst-exists, removed-legacy ({dst.name})"
            return f"CONFLICT: dst-exists-different-size ({dst.name})"
        except OSError as e:
            return f"ERROR stat: {e}"

    if dry_run:
        return f"would-move → {dst.relative_to(POSTS_DIR)}"

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"moved → {dst.relative_to(POSTS_DIR)}"


def migrate(dry_run: bool = False) -> dict:
    posts = discover_posts()

    if not posts:
        print("[INFO] No posts discovered (neither legacy flat layout nor per-topic layout). Nothing to do.")
        return {}

    print(f"\n{'='*60}")
    print(f"  POSTS REORGANIZATION {'(DRY RUN)' if dry_run else ''}")
    print(f"  Discovered: {len(posts)} posts")
    print(f"{'='*60}\n")

    summary = {"moved": 0, "skipped": 0, "errors": 0, "topics": []}

    for num in sorted(posts.keys()):
        entry = posts[num]
        slug = entry.get("slug")
        if not slug:
            print(f"[WARN] post{num:02d}: no English draft, skipping (orphan zh file)")
            summary["skipped"] += 1
            continue

        topic_dir = POSTS_DIR / slug
        en_dir = topic_dir / "en"
        zh_dir = topic_dir / "zh"
        pdfs_dir = topic_dir / "pdfs"
        meta_path = topic_dir / "meta.json"

        if not dry_run:
            en_dir.mkdir(parents=True, exist_ok=True)
            pdfs_dir.mkdir(parents=True, exist_ok=True)
            if entry.get("zh_txt") or zh_dir.exists():
                zh_dir.mkdir(parents=True, exist_ok=True)

        print(f"[POST {num:02d}] {slug}")

        dst_en = en_dir / "draft.txt"
        status = move_file(entry.get("en_txt"), dst_en, dry_run)
        print(f"  en/draft.txt        : {status}")
        summary["moved"] += status.startswith("moved") or status.startswith("would")
        summary["errors"] += status.startswith("CONFLICT") or status.startswith("ERROR")

        dst_png = en_dir / "single_page.png"
        status = move_file(entry.get("png"), dst_png, dry_run)
        print(f"  en/single_page.png  : {status}")
        summary["moved"] += status.startswith("moved") or status.startswith("would")
        summary["errors"] += status.startswith("CONFLICT") or status.startswith("ERROR")

        has_zh = False
        if entry.get("zh_txt") or (zh_dir / "draft.txt").exists():
            dst_zh = zh_dir / "draft.txt"
            status = move_file(entry.get("zh_txt"), dst_zh, dry_run)
            print(f"  zh/draft.txt        : {status}")
            summary["moved"] += status.startswith("moved") or status.startswith("would")
            summary["errors"] += status.startswith("CONFLICT") or status.startswith("ERROR")
            has_zh = True

        draft_source = dst_en if dst_en.exists() else entry.get("en_txt")
        parsed = parse_meta_from_draft(draft_source) if draft_source else {}

        new_meta = build_meta_json(num, slug, parsed, has_zh)
        existing_meta = None
        meta_was_malformed = False
        if meta_path.exists():
            try:
                existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing_meta = None
                meta_was_malformed = True

        meta = merge_meta(existing_meta, new_meta)
        if existing_meta is not None:
            meta_status = "updated (preserved existing fields)"
        elif meta_was_malformed:
            meta_status = "rewritten (existing was malformed)"
        else:
            meta_status = "created"

        if not dry_run:
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  meta.json           : {meta_status}")
        print(f"  pdfs/               : {'ready' if pdfs_dir.exists() or dry_run else 'missing'}")
        summary["topics"].append(slug)

    print(f"\n{'='*60}")
    print(f"  Topics processed : {len(summary['topics'])}")
    print(f"  Moves            : {summary['moved']}")
    print(f"  Skipped          : {summary['skipped']}")
    print(f"  Errors/conflicts : {summary['errors']}")
    print(f"{'='*60}\n")

    for legacy in (LEGACY_EN_DIR, LEGACY_PNG_DIR, LEGACY_ZH_DIR):
        if legacy.exists():
            try:
                remaining = [p for p in legacy.iterdir() if not p.name.startswith(".")]
                if not remaining:
                    if not dry_run:
                        legacy.rmdir()
                        print(f"[CLEANUP] removed empty legacy dir: {legacy.relative_to(POSTS_DIR)}/")
                    else:
                        print(f"[CLEANUP] would remove empty legacy dir: {legacy.relative_to(POSTS_DIR)}/")
                else:
                    print(f"[KEEP] {legacy.relative_to(POSTS_DIR)}/ still has {len(remaining)} item(s) — not removed")
            except OSError as e:
                print(f"[WARN] could not clean {legacy}: {e}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Reorganize Posts/ into per-topic layout")
    parser.add_argument("--dry-run", action="store_true", help="Show planned moves without writing")
    args = parser.parse_args()
    summary = migrate(dry_run=args.dry_run)
    sys.exit(0 if summary.get("errors", 0) == 0 else 1)


if __name__ == "__main__":
    main()
