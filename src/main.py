#!/usr/bin/env python3
"""
ContentPrinter — Instagram Content Pipeline for Central Strength Gym
Modeled after MoneyPrinterV2 architecture.

Usage:
    python src/main.py              # Run full pipeline (scrape → youtube → pubmed → biorxiv → draft → images → pdf)
    python src/main.py scrape       # Scrape RSS feeds only
    python src/main.py youtube      # Scrape YouTube channels only
    python src/main.py pubmed       # Scrape PubMed for exercise science studies
    python src/main.py biorxiv      # Scrape bioRxiv for preprints
    python src/main.py reddit       # Recursive Reddit scraper (r/powerlifting etc., depth 2)
    python src/main.py forums       # Recursive forum scraper (disabled by default in config)
    python src/main.py draft        # Draft posts from scraped content (template path)
    python src/main.py draft --llm  # Draft posts via grounded LLM (citation-safe)
    python src/main.py zh           # Regenerate Chinese drafts in Bruce Lu voice (requires ANTHROPIC_API_KEY)
    python src/main.py sourcepdfs   # Download open-access source PDFs for training-method posts
    python src/main.py images       # Generate carousel images from drafts
    python src/main.py pdf          # Generate PDFs from carousel images
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scraper import scrape_all_feeds
from youtube_scraper import scrape_youtube
from pubmed_scraper import scrape_pubmed
from biorxiv_scraper import scrape_biorxiv
from reddit_scraper import scrape_reddit
from forum_scraper import scrape_forums
from chinese_drafter import regenerate_all as regenerate_chinese
from pdf_downloader import download_all as download_source_pdfs
from drafter import draft_all, draft_all_grounded
from image_generator import generate_all_images
from pdf_generator import generate_all_pdfs
from single_page_generator import generate_all_single_pages


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   ██████╗ ██████╗ ███╗   ██╗████████╗███████╗███╗   ██╗ ║
║  ██╔════╝██╔═══██╗████╗  ██║╚══██╔══╝██╔════╝████╗  ██║ ║
║  ██║     ██║   ██║██╔██╗ ██║   ██║   █████╗  ██╔██╗ ██║ ║
║  ██║     ██║   ██║██║╚██╗██║   ██║   ██╔══╝  ██║╚██╗██║ ║
║  ╚██████╗╚██████╔╝██║ ╚████║   ██║   ███████╗██║ ╚████║ ║
║   ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝  ╚═╝   ╚══════╝╚═╝  ╚═══╝ ║
║          PRINTER — Central Strength Gym                  ║
║                                                          ║
║  Scrape → Draft → Design → Post                         ║
╚══════════════════════════════════════════════════════════╝
    """)


def run_scrape():
    print("\n[STEP 1/7] Scraping content from fitness blogs & feeds...\n")
    articles = scrape_all_feeds()
    return articles


def run_youtube():
    print("\n[STEP 2/7] Scraping YouTube channels for science-based videos...\n")
    videos = scrape_youtube()
    return videos


def run_pubmed():
    print("\n[STEP 3/7] Scraping PubMed for exercise science studies...\n")
    articles = scrape_pubmed()
    return articles


def run_biorxiv():
    print("\n[STEP 4/7] Scraping bioRxiv for preprints...\n")
    preprints = scrape_biorxiv()
    return preprints


def run_draft(use_llm: bool = False):
    print("\n[STEP 5/7] Drafting Instagram posts...\n")
    if use_llm:
        return draft_all_grounded()
    return draft_all()


def run_images():
    print("\n[STEP 6/7] Generating carousel images...\n")
    generate_all_images()


def run_pdf():
    print("\n[STEP 7/7] Generating PDFs from carousel images...\n")
    generate_all_pdfs()


def run_finalize(dry_run: bool = False):
    """Promote work/<slug>/* artifacts to Posts/<category>/<clean_slug>.*.

    Finalization is idempotent and safe to re-run. Walks every slug in work/
    with a rendered single_page.png and moves it (plus the zh draft and any
    downloaded reference PDFs) into the 6-category final output layout under
    Posts/. The zh draft is converted from plain text to markdown on the way.
    """
    from output_layout import finalize_all, summarize
    print("\n[STEP 8/8] Finalizing outputs → Posts/<category>/ ...\n")
    results = finalize_all(dry_run=dry_run)
    print(summarize(results))


def _safe_run(step_name, func):
    """Run a pipeline step, catching exceptions so partial failures don't abort the pipeline."""
    try:
        return func()
    except Exception as e:
        print(f"\n[ERROR] {step_name} failed: {e}")
        print(f"        Continuing with remaining pipeline steps.\n")
        return None


def run_full_pipeline():
    print_banner()

    articles = _safe_run("RSS scrape", run_scrape)
    if not articles:
        print("[WARN] No articles scraped. Check your internet connection or feed URLs.")
        print("       You can still draft from previously scraped content.\n")

    videos = _safe_run("YouTube scrape", run_youtube)
    if not videos:
        print("[WARN] No YouTube videos scraped. Check channel URLs or yt-dlp.\n")

    pubmed_articles = _safe_run("PubMed scrape", run_pubmed)
    if not pubmed_articles:
        print("[WARN] No PubMed articles scraped. Check search terms or connectivity.\n")

    biorxiv_preprints = _safe_run("bioRxiv scrape", run_biorxiv)
    if not biorxiv_preprints:
        print("[WARN] No bioRxiv preprints scraped. Check settings or connectivity.\n")

    posts = _safe_run("Draft", run_draft)
    if not posts:
        print("[WARN] No posts drafted. Run scrape step first.")
        return

    _safe_run("Image generation", run_images)

    _safe_run("PDF generation", run_pdf)
    _safe_run("Finalize", run_finalize)

    posts_dir = PROJECT_ROOT / "Posts"
    print(f"""
{'='*60}
  PIPELINE COMPLETE
{'='*60}

  Your content is ready in: {posts_dir}/

  Posts/
  ├── training_methods/     <- technique, progression, mistakes
  │   ├── <slug>.png         (Instagram single-page, 1080x1350+)
  │   ├── <slug>.zh.md       (Chinese markdown version)
  │   └── pdfs/              (downloaded reference papers)
  ├── sample_programming/   <- beginner program, Texas Method, etc.
  ├── nutrition/            <- diet, macros, meal structure
  ├── supplements/          <- creatine, caffeine, beta-alanine, etc.
  ├── cardio/               <- concurrent training, Zone 2
  └── warmup/               <- dynamic warmups, prehab

  Intermediates (drafts, raw scrapes, meta.json) live in work/ and are
  gitignored — Posts/ contains only the finalized outputs.

  NEXT STEPS:
  1. Review single_page PNGs under Posts/<category>/*.png
  2. Read Chinese markdowns under Posts/<category>/*.zh.md
  3. Cite the reference PDFs under Posts/<category>/pdfs/
  4. Post to Instagram!

{'='*60}
    """)


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "scrape":
            print_banner()
            run_scrape()
        elif command == "youtube":
            print_banner()
            run_youtube()
        elif command == "pubmed":
            print_banner()
            run_pubmed()
        elif command == "biorxiv":
            print_banner()
            run_biorxiv()
        elif command == "draft":
            print_banner()
            use_llm = "--llm" in sys.argv[2:]
            run_draft(use_llm=use_llm)
        elif command == "images":
            print_banner()
            run_images()
        elif command == "pdf":
            print_banner()
            run_pdf()
        elif command == "zh":
            print_banner()
            regenerate_chinese()
        elif command == "sourcepdfs":
            print_banner()
            download_source_pdfs()
        elif command == "reddit":
            print_banner()
            scrape_reddit()
        elif command == "forums":
            print_banner()
            scrape_forums()
        elif command == "singlepage":
            print_banner()
            generate_all_single_pages()
            run_finalize()
        elif command == "finalize":
            print_banner()
            run_finalize(dry_run="--dry-run" in sys.argv[2:])
        elif command in ("help", "-h", "--help"):
            print(__doc__)
        else:
            print(f"Unknown command: {command}")
            print(__doc__)
    else:
        run_full_pipeline()


if __name__ == "__main__":
    main()
