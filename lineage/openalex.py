"""Live OpenAlex HTTP fetch. Not reachable from the container; runs on the
laptop. Injected as the fetch callable into resolve and traverse.

Failure contract: a 404 becomes WorkNotFound (permanent). Transient failures
(connection drop, timeout, 5xx, 429) are retried with backoff and become
FetchFailed if they do not clear. Other HTTP errors (401, 403, other 4xx)
propagate and abort the run. A politeness delay spaces out requests so we stop
triggering connection drops.
"""
import http.client
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from lineage.resolve import FetchFailed, WorkNotFound

logger = logging.getLogger(__name__)

OPENALEX_WORKS = "https://api.openalex.org/works"

REQUEST_TIMEOUT = 30
POLITE_DELAY = 0.2  # seconds between requests; OpenAlex polite pool allows ~10/s
MAX_RETRIES = 3
BACKOFF_BASE = 1.0  # exponential: 1, 2, 4 s
BACKOFF_CAP = 8.0

_TRANSIENT_NET = (
    urllib.error.URLError,
    ConnectionError,
    TimeoutError,
    http.client.HTTPException,
)


def _backoff(attempt: int) -> float:
    return min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)


def http_fetch(ref: str) -> dict:
    """Fetch an OpenAlex work by work id ('Wxxxx') or DOI ('10.x/y').

    Adds the polite-pool mailto from NCBI_EMAIL when set.
    """
    path = ref if ref.startswith("W") else f"doi:{ref}"
    url = f"{OPENALEX_WORKS}/{path}"
    email = os.environ.get("NCBI_EMAIL")
    if email:
        url = f"{url}?{urllib.parse.urlencode({'mailto': email.strip()})}"

    time.sleep(POLITE_DELAY)
    logger.info("Fetching OpenAlex work %s", ref)

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise WorkNotFound(ref) from e
            if e.code != 429 and not (500 <= e.code < 600):
                raise  # 401, 403, other 4xx: config problem, abort loudly
            wait = _retry_after(e) or _backoff(attempt)
            reason = f"HTTP {e.code}"
        except _TRANSIENT_NET as e:
            wait = _backoff(attempt)
            reason = str(e) or e.__class__.__name__

        if attempt < MAX_RETRIES:
            logger.warning(
                "Transient %s for %s (attempt %d/%d), retrying in %.1fs",
                reason, ref, attempt + 1, MAX_RETRIES + 1, wait,
            )
            time.sleep(wait)
        else:
            logger.warning("Giving up on %s after %d attempts: %s", ref, MAX_RETRIES + 1, reason)

    raise FetchFailed(ref)


def _retry_after(e: urllib.error.HTTPError) -> float | None:
    value = e.headers.get("Retry-After") if e.headers else None
    if value and value.isdigit():
        return float(value)
    return None
