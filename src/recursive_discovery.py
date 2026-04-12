"""
Shared utilities for recursive scraping (Reddit, forums, etc.).

Provides:
    - VisitedSet: persistent URL-hash deduper, used as a cycle guard across
      recursive scrape passes.
    - normalize_url / url_hash: canonicalization so fragment/query differences
      don't produce false-new URLs.
    - expand_outbound_links: given HTML or a text blob, return outbound links
      filtered by allow/block lists — the queue-expander for depth>0 passes.
    - fetch_html: polite HTTP fetch with robots.txt cache (fail-closed when
      respect_robots_txt is set).

All outbound HTTP goes through http_utils.create_session, as required by the
project conventions.
"""

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from http_utils import create_session, get as http_get


def normalize_url(url: str) -> str:
    """Canonicalize a URL for dedup: drop fragments, lowercase host, strip trailing slash."""
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query = p.query
    return urlunparse((scheme, netloc, path, "", query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:16]


class VisitedSet:
    """Persistent URL-hash visited set. Backed by a JSON file on disk."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._hashes: set[str] = set()
        if self.path.exists():
            try:
                self._hashes = set(json.loads(self.path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                self._hashes = set()

    def __contains__(self, url: str) -> bool:
        return url_hash(url) in self._hashes

    def add(self, url: str) -> bool:
        """Add a URL; return True if it was new."""
        h = url_hash(url)
        if h in self._hashes:
            return False
        self._hashes.add(h)
        return True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self._hashes)), encoding="utf-8")

    def __len__(self) -> int:
        return len(self._hashes)


class RobotsCache:
    """Per-host robots.txt cache. `can_fetch(ua, url)` is fail-closed on error
    iff fail_closed=True, otherwise defaults to allow.
    """

    def __init__(self, session, user_agent: str, fail_closed: bool = False):
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._session = session
        self._ua = user_agent
        self._fail_closed = fail_closed

    def _fetch(self, host_root: str) -> RobotFileParser | None:
        rp = RobotFileParser()
        robots_url = urljoin(host_root, "/robots.txt")
        try:
            resp = http_get(self._session, robots_url, timeout=10)
            rp.parse(resp.text.splitlines())
            return rp
        except Exception:
            return None

    def can_fetch(self, url: str) -> bool:
        p = urlparse(url)
        if not p.netloc:
            return False
        host_root = f"{p.scheme}://{p.netloc}"
        if host_root not in self._parsers:
            self._parsers[host_root] = self._fetch(host_root)
        rp = self._parsers[host_root]
        if rp is None:
            return not self._fail_closed
        try:
            return rp.can_fetch(self._ua, url)
        except Exception:
            return not self._fail_closed


def _host_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except ValueError:
        return ""


def host_matches_any(url: str, patterns: Iterable[str]) -> bool:
    host = _host_of(url)
    if not host:
        return False
    for pat in patterns:
        p = pat.lower().strip()
        if not p:
            continue
        if host == p or host.endswith("." + p):
            return True
    return False


URL_REGEX = re.compile(r"https?://[^\s<>\"']+")


def extract_outbound_links(
    html_or_text: str,
    base_url: str,
    allowlist: Iterable[str] = (),
    blocklist: Iterable[str] = (),
    max_links: int = 5,
) -> list[str]:
    """Pull outbound links from HTML (or plain text) for recursive expansion.

    Rules:
      - Dedup on normalized URL.
      - Drop same-origin as base_url (we already handle that source).
      - If allowlist is non-empty, require a host match.
      - Always drop blocklist matches.
    """
    allowlist = list(allowlist)
    blocklist = list(blocklist)
    base_host = _host_of(base_url)

    candidates: list[str] = []
    try:
        soup = BeautifulSoup(html_or_text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "javascript:", "#")):
                continue
            absolute = urljoin(base_url, href)
            candidates.append(absolute)
    except Exception:
        pass

    for m in URL_REGEX.findall(html_or_text):
        candidates.append(m)

    out: list[str] = []
    seen_hashes: set[str] = set()
    for raw in candidates:
        norm = normalize_url(raw)
        if not norm:
            continue
        h = url_hash(norm)
        if h in seen_hashes:
            continue
        host = _host_of(norm)
        if not host or host == base_host:
            continue
        if blocklist and host_matches_any(norm, blocklist):
            continue
        if allowlist and not host_matches_any(norm, allowlist):
            continue
        seen_hashes.add(h)
        out.append(norm)
        if len(out) >= max_links:
            break
    return out


def fetch_html(session, url: str, timeout: int = 15) -> str:
    """Fetch a URL and return response text. Raises on HTTP errors (via http_utils.get)."""
    resp = http_get(session, url, timeout=timeout)
    return resp.text


def polite_sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def make_session(user_agent: str | None = None):
    """Return a requests session with optional UA override."""
    session = create_session()
    if user_agent:
        session.headers["User-Agent"] = user_agent
    return session
