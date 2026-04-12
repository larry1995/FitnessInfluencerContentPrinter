"""Smoke test: every pipeline module should import cleanly."""

import importlib
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

MODULES = [
    "scraper",
    "biorxiv_scraper",
    "pubmed_scraper",
    "youtube_scraper",
    "reddit_scraper",
    "forum_scraper",
    "recursive_discovery",
    "posts_layout",
    "output_layout",
    "source_promoter",
    "audit_meta_writer",
    "llm_client",
    "chinese_drafter",
    "pdf_downloader",
    "drafter",
    "single_page_generator",
    "image_generator",
    "pdf_generator",
    "http_utils",
]


def test_all_modules_import():
    for name in MODULES:
        importlib.import_module(name)
