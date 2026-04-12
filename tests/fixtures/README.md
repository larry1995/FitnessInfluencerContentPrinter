# Test fixtures

All files in this tree are used by `pytest tests/` and the `smoke.yml` CI job.
Everything here is either synthetic or manually anonymized — no real third-party
content is redistributed.

## Layout

```
tests/fixtures/
├── reddit/
│   └── powerlifting_top.json       synthetic r/powerlifting /top.json response
├── html/
│   ├── 54d1683560fbcd09.html       outbound fixture for https://www.strongerbyscience.com/autoregulation/
│   └── c6cdca7d149fdade.html       outbound fixture for https://pubmed.ncbi.nlm.nih.gov/12345678/
├── rss/                             (reserved — RSS feed samples go here)
└── youtube/                         (reserved — yt-dlp JSON + VTT samples go here)
```

## Path derivation

Outbound HTML fixtures are keyed by the first 16 hex chars of
`sha1(normalize_url(url))`, as implemented in
`src/recursive_discovery.py:url_hash`.

To add a new HTML fixture:

```bash
python3 -c "import sys; sys.path.insert(0,'src'); from recursive_discovery import url_hash; print(url_hash('YOUR_URL'))"
```

Then save the file as `tests/fixtures/html/<hash>.html`.

## Usage from CI

Scrapers accept `--fixture-dir tests/fixtures`, which short-circuits all HTTP.
The Reddit scraper loads `reddit/<sub>_<listing>.json` instead of calling
`old.reddit.com`, and all outbound GETs look up `html/<hash>.html`.
