"""
Shared HTTP utilities for ContentPrinter scrapers.
Provides a requests Session with automatic retry and backoff.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "Mozilla/5.0 (compatible; ContentPrinter/1.0; +https://centralstrengthgyms.com)"


def create_session(
    retries=3,
    backoff_factor=1,
    status_forcelist=(429, 500, 502, 503, 504),
    timeout=15,
):
    """Create a requests Session with retry logic.

    Args:
        retries: Number of retries on failure.
        backoff_factor: Multiplier for exponential backoff (1 -> 0s, 1s, 2s, 4s).
        status_forcelist: HTTP status codes that trigger a retry.
        timeout: Default timeout in seconds (applied per-request if not overridden).

    Returns:
        A configured requests.Session.
    """
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Store default timeout so callers can use session.get(url) without repeating it
    session.default_timeout = timeout

    return session


def get(session, url, **kwargs):
    """Wrapper around session.get that applies default timeout if not specified."""
    kwargs.setdefault("timeout", getattr(session, "default_timeout", 15))
    resp = session.get(url, **kwargs)
    resp.raise_for_status()
    return resp
