# ContentPrinter

A research-grounded content pipeline that turns peer-reviewed strength-and-conditioning literature into Instagram-ready single-page graphics for [Central Strength Gyms](https://centralstrengthgyms.com).

Each topic ships as three artifacts:

1. A 1080×1350 / 1080×1920 PNG with caption and references baked in
2. A Mainland-Simplified-Chinese companion post in the voice of [Bruce Lu (@bruce_lu_1993)](https://www.youtube.com/@bruce_lu_1993)
3. Downloaded reference PDFs for every cited journal paper

Posts pass an F-0 citation-integrity gate before publishing, so DOIs, authors, and journals all resolve against PubMed and Crossref before a topic is considered shippable.

## Quick start

Requires Python ≥ 3.10.

```bash
pip install -r requirements.txt

# template drafter — no LLM key needed
python src/main.py draft
python src/main.py singlepage

# grounded pipeline (requires ANTHROPIC_API_KEY in .env)
python src/main.py draft --llm
python src/main.py singlepage
python src/main.py zh
python src/main.py sourcepdfs
```

Run `python -m pytest tests/ -q` before committing. Baseline: all tests green.

## Repo layout

```
contentprinter/   stable public API (import from here)
src/              internal pipeline modules — scrapers, drafters, renderers, verify gate
config/           taxonomy, sources, prompts, brand style guide
Posts/            shipped output, organized by category (cardio, nutrition, supplements, etc.)
audits/           citation-integrity reference implementation + design notes
tests/            pytest suite + fixtures
work/             scratch — drafts, raw scrapes, intermediates (gitignored)
docs/             format specs and draft plans
```

## Library usage

Downstream consumers import from `contentprinter.*` only — see [API_SURFACE.md](API_SURFACE.md) for the stability contract.

```python
from contentprinter import (
    generate_grounded_draft,
    render_page,
    run_verify_gate,
    download_references,
)
```

## Documentation

- [ROADMAP.md](ROADMAP.md) — project vision, current state, agent handoff notes
- [API_SURFACE.md](API_SURFACE.md) — public package API and stability promise
- [docs/MANUAL_DRAFT_FORMAT.md](docs/MANUAL_DRAFT_FORMAT.md) — manual draft authoring spec
- [audits/grounded_drafter_design.md](audits/grounded_drafter_design.md) — citation-integrity design

## License

Proprietary — Central Strength Gyms.
