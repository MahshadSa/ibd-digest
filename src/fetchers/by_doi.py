import json
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from src.fetchers.journals import _parse_crossref_item
from src.fetchers.pubmed import _parse_article

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _http_crossref_work(doi: str, email: str) -> dict | None:
    """Return the Crossref work item for a DOI, or None."""
    encoded = urllib.parse.quote(doi, safe="")
    url = f"https://api.crossref.org/works/{encoded}"
    req = urllib.request.Request(
        url, headers={"User-Agent": f"IBD-Digest/1.0 (mailto:{email})"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("message") or None
    except Exception:
        logger.warning("Crossref lookup failed for %s", doi)
        return None


def _http_pubmed_article(doi: str, api_key: str | None, email: str) -> ET.Element | None:
    """Return the first PubmedArticle element for a DOI, or None."""
    search = {"db": "pubmed", "term": f"{doi}[DOI]", "retmode": "json",
              "retmax": 1, "email": email}
    if api_key:
        search["api_key"] = api_key
    try:
        with urllib.request.urlopen(
            f"{EUTILS_BASE}/esearch.fcgi?{urllib.parse.urlencode(search)}", timeout=30
        ) as resp:
            pmids = json.loads(resp.read())["esearchresult"]["idlist"]
        if not pmids:
            return None
        fetch = {"db": "pubmed", "id": pmids[0], "rettype": "xml", "retmode": "xml",
                 "email": email}
        if api_key:
            fetch["api_key"] = api_key
        with urllib.request.urlopen(
            f"{EUTILS_BASE}/efetch.fcgi?{urllib.parse.urlencode(fetch)}", timeout=30
        ) as resp:
            root = ET.fromstring(resp.read())
        return root.find("PubmedArticle")
    except Exception:
        logger.warning("PubMed lookup failed for %s", doi)
        return None


def fetch_by_doi(
    doi: str,
    email: str,
    api_key: str | None,
    crossref=_http_crossref_work,
    pubmed=_http_pubmed_article,
) -> dict | None:
    """Return a full paper dict for one DOI. Crossref first, PubMed for the
    abstract when Crossref lacks it. None if neither source resolves the DOI.
    """
    item = crossref(doi, email)
    cr = _parse_crossref_item(item, "crossref-rehydrate", "") if item else None
    if cr and cr["abstract"]:
        return cr
    el = pubmed(doi, api_key, email)
    pm = _parse_article(el) if el is not None else None
    if pm and pm["abstract"]:
        return pm
    return cr or pm
