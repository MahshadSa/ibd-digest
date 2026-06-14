"""Live OpenAlex HTTP fetch. Not reachable from the container; runs on the
laptop. Injected as the fetch callable into resolve and traverse.
"""
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from lineage.resolve import WorkNotFound

logger = logging.getLogger(__name__)

OPENALEX_WORKS = "https://api.openalex.org/works"


def http_fetch(ref: str) -> dict:
    """Fetch an OpenAlex work by work id ('Wxxxx') or DOI ('10.x/y').

    Adds the polite-pool mailto from NCBI_EMAIL when set. A 404 is re-raised as
    WorkNotFound so traverse can skip it; every other HTTP and network error
    propagates so it aborts the run loudly.
    """
    path = ref if ref.startswith("W") else f"doi:{ref}"
    url = f"{OPENALEX_WORKS}/{path}"
    email = os.environ.get("NCBI_EMAIL")
    if email:
        url = f"{url}?{urllib.parse.urlencode({'mailto': email.strip()})}"
    logger.info("Fetching OpenAlex work %s", ref)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise WorkNotFound(ref) from e
        raise
