"""Live OpenAlex HTTP fetch. Not reachable from the container; runs on the
laptop. Injected as the fetch callable into resolve and traverse.
"""
import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

OPENALEX_WORKS = "https://api.openalex.org/works"


def http_fetch(ref: str) -> dict:
    """Fetch an OpenAlex work by work id ('Wxxxx') or DOI ('10.x/y').

    Adds the polite-pool mailto from NCBI_EMAIL when set.
    """
    path = ref if ref.startswith("W") else f"doi:{ref}"
    url = f"{OPENALEX_WORKS}/{path}"
    email = os.environ.get("NCBI_EMAIL")
    if email:
        url = f"{url}?{urllib.parse.urlencode({'mailto': email.strip()})}"
    logger.info("Fetching OpenAlex work %s", ref)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())
