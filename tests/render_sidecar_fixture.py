"""Dev harness for Task #25.

Builds an in-memory post dict from `tests/fixtures/sidecar/sample_reddit_source.json`,
drives the renderer, and writes a test PNG to /tmp so the layout can be
eyeballed without waiting on live reddit scraping.

Usage:
    python tests/render_sidecar_fixture.py
"""

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from PIL import Image, ImageDraw  # noqa: E402

from single_page_generator import (  # noqa: E402
    _populate_from_sidecar,
    calculate_page_height,
    parse_detailed_content,
    render_single_page,
)


def build_post_from_fixture(fixture_path: Path) -> dict:
    with open(fixture_path) as f:
        sidecar = json.load(f)

    post = {
        "filename": "draft.txt",
        "title": "",
        "source": "",
        "topic": "",
        "layout": "default",
        "intro_text": "",
        "numbered_points": [],
        "sections": [],
        "extra_sections": [],
        "practical_guide": [],
        "practical_guide_header": "",
        "summary_text": "",
        "references": [],
        "evidence_info": {},
        "key_stat": "",
        "program_phases": [],
        "myths": [],
        "rehab_steps": [],
        "supplement_facts": {},
        "reddit_meta": {},
        "reddit_callouts": [],
        "forum_meta": {},
        "forum_quote_chain": [],
    }
    _populate_from_sidecar(post, sidecar)
    return post


def build_synthetic_forum_post() -> dict:
    post = {
        "filename": "draft.txt",
        "title": "", "source": "", "topic": "", "layout": "default",
        "intro_text": "", "numbered_points": [], "sections": [],
        "extra_sections": [], "practical_guide": [], "practical_guide_header": "",
        "summary_text": "", "references": [], "evidence_info": {}, "key_stat": "",
        "program_phases": [], "myths": [], "rehab_steps": [],
        "supplement_facts": {}, "reddit_meta": {}, "reddit_callouts": [],
        "forum_meta": {}, "forum_quote_chain": [],
    }
    sidecar = {
        "source_type": "forum",
        "forum_name": "T-Nation",
        "subforum": "Powerlifting",
        "thread_title": "Hip Drive vs Knee Drive on the Squat — What Actually Transfers",
        "thread_url": "https://forums.t-nation.com/t/hip-drive-vs-knee-drive/fake",
        "op_author": "texas_lifter",
        "op_rank": "Senior Member",
        "op_post_count": 1842,
        "op_body": ("Been coaching for 15 years and I still see the hip-drive vs knee-drive "
                    "debate come up every few months. Here's what I've actually observed in "
                    "clients moving over 500 lbs: the answer depends on limb proportions, not ideology."),
        "fetched_at": "2026-04-12T00:20:00",
        "evidence_info": {},
        "forum_quote_chain": [
            {
                "author": "coach_jeff",
                "rank": "Verified Coach",
                "body": ("Agreed — I've stopped prescribing cue-based fixes and switched to "
                         "position-based ones. If the knees cave, address hip abduction weakness. "
                         "If the chest collapses, address thoracic position. The 'drive' cue is "
                         "downstream of whether the position is achievable."),
                "quoting": None,
                "permalink": "https://forums.t-nation.com/t/fake/2",
            },
            {
                "author": "biomech_nerd",
                "rank": "Member",
                "body": ("Counterpoint: the McGill lab data on squat mechanics shows knee-forward "
                         "translation is a function of ankle dorsiflexion, not coaching cue. If the "
                         "lifter has stiff ankles, no amount of 'hip drive' cueing changes the bar path."),
                "quoting": 0,
                "permalink": "https://forums.t-nation.com/t/fake/3",
            },
            {
                "author": "texas_lifter",
                "rank": "Senior Member",
                "body": ("Both points fair. I'd add that for tall lifters with long femurs, the "
                         "'more hip drive' cue is a compensation for a positional problem we can't "
                         "coach around — they'll always have more forward lean, and that's fine."),
                "quoting": 1,
                "permalink": "https://forums.t-nation.com/t/fake/4",
            },
        ],
    }
    _populate_from_sidecar(post, sidecar)
    return post


def render_and_save(post: dict, out_path: Path) -> None:
    tmp_img = Image.new("RGB", (3240, 100))
    tmp_draw = ImageDraw.Draw(tmp_img)
    page_height = calculate_page_height(post, tmp_draw)
    page_img = render_single_page(post, page_height)
    page_img.save(out_path, "PNG", optimize=True)
    tmp_img.close()
    page_img.close()
    print(f"[OK] layout={post['layout']}  height={page_height}px  -> {out_path}")


def main():
    fixture = REPO_ROOT / "tests" / "fixtures" / "sidecar" / "sample_reddit_source.json"
    if not fixture.exists():
        print(f"[ERR] fixture not found: {fixture}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(tempfile.gettempdir()) / "contentprinter_dev"
    out_dir.mkdir(parents=True, exist_ok=True)

    reddit_post = build_post_from_fixture(fixture)
    render_and_save(reddit_post, out_dir / "sample_reddit.png")

    forum_post = build_synthetic_forum_post()
    render_and_save(forum_post, out_dir / "sample_forum.png")

    print(f"\nOpen these in an image viewer:\n  {out_dir}/sample_reddit.png\n  {out_dir}/sample_forum.png")


if __name__ == "__main__":
    main()
