import json
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Base query without date filter; fetch_pubmed appends "last N days"[PDat].
PUBMED_QUERY_BASE = """(
  (
    (
      "Inflammatory Bowel Diseases"[Mesh]
      OR "Crohn Disease"[Mesh]
      OR "Colitis, Ulcerative"[Mesh]
      OR inflammatory bowel disease[tiab]
      OR Crohn[tiab]
      OR "ulcerative colitis"[tiab]
      OR IBD[tiab]
    )
    AND
    (
      "Magnetic Resonance Imaging"[Mesh]
      OR "Diffusion Magnetic Resonance Imaging"[Mesh]
      OR "Tomography, X-Ray Computed"[Mesh]
      OR "Ultrasonography"[Mesh]
      OR MRI[tiab]
      OR MRE[tiab]
      OR "magnetic resonance enterography"[tiab]
      OR "MR enterography"[tiab]
      OR "CT enterography"[tiab]
      OR CTE[tiab]
      OR "intestinal ultrasound"[tiab]
      OR IUS[tiab]
      OR radiomics[tiab]
      OR "deep learning"[tiab]
      OR "artificial intelligence"[tiab]
      OR "treatment response"[tiab]
      OR monitoring[tiab]
      OR "disease activity"[tiab]
      OR "mucosal healing"[tiab]
      OR "transmural healing"[tiab]
    )
  )
  OR
  (
    (
      "Inflammatory Bowel Diseases"[Mesh]
      OR "Crohn Disease"[Mesh]
      OR "Colitis, Ulcerative"[Mesh]
    )
    AND
    (
      "Review"[Publication Type]
      OR "Practice Guideline"[Publication Type]
      OR "Guideline"[Publication Type]
      OR consensus[tiab]
      OR "position paper"[tiab]
    )
  )
)
AND English[Language]
NOT "Case Reports"[Publication Type]"""

_MONTH_MAP = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def _esearch(query: str, api_key: str, email: str) -> list[str]:
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": 500,
        "api_key": api_key,
        "email": email,
    }).encode()
    url = f"{EUTILS_BASE}/esearch.fcgi"
    with urllib.request.urlopen(url, data=params, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["esearchresult"]["idlist"]


def _efetch(pmids: list[str], api_key: str, email: str) -> ET.Element:
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "xml",
        "retmode": "xml",
        "api_key": api_key,
        "email": email,
    })
    url = f"{EUTILS_BASE}/efetch.fcgi?{params}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        return ET.fromstring(resp.read())


def _parse_pubdate(el: ET.Element | None) -> str:
    if el is None:
        return date.today().isoformat()
    year = el.findtext("Year") or str(date.today().year)
    month = el.findtext("Month") or "01"
    day = el.findtext("Day") or "01"
    month = _MONTH_MAP.get(month, month.zfill(2))
    return f"{year}-{month}-{day.zfill(2)}"


def _parse_article(article: ET.Element) -> dict | None:
    """Parse a PubmedArticle element into a paper dict; returns None if DOI is missing."""
    medline = article.find("MedlineCitation")
    art = medline.find("Article") if medline is not None else None
    if art is None:
        return None

    id_list = article.find("PubmedData/ArticleIdList")
    doi = None
    if id_list is not None:
        for aid in id_list.findall("ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text
                break
    if not doi:
        return None

    title_el = art.find("ArticleTitle")
    title = "".join(title_el.itertext()).strip() if title_el is not None else ""

    authors: list[str] = []
    for author in art.findall("AuthorList/Author"):
        last = author.findtext("LastName", "")
        initials = author.findtext("Initials", "")
        if last:
            authors.append(f"{last} {initials}".strip())

    journal = (
        art.findtext("Journal/Title")
        or art.findtext("Journal/ISOAbbreviation")
        or ""
    )

    pub_date = _parse_pubdate(art.find("Journal/JournalIssue/PubDate"))

    abstract: str | None = None
    abstract_el = art.find("Abstract")
    if abstract_el is not None:
        parts = []
        for text_el in abstract_el.findall("AbstractText"):
            label = text_el.get("Label")
            text = "".join(text_el.itertext()).strip()
            parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(parts) or None

    return {
        "doi": doi.lower().strip(),
        "title": title,
        "authors": authors,
        "corresponding_author": authors[-1] if authors else None,
        "journal": journal,
        "pub_date": pub_date,
        "abstract": abstract,
        "source": "pubmed",
    }


def fetch_pubmed(api_key: str, email: str, days_back: int = 1) -> list[dict]:
    """Fetch papers from PubMed matching the v1 IBD imaging query for the last N days."""
    query = f'{PUBMED_QUERY_BASE}\nAND "last {days_back} days"[PDat]'
    logger.info("Searching PubMed (days_back=%d)", days_back)

    pmids = _esearch(query, api_key, email)
    if not pmids:
        logger.info("PubMed returned no results")
        return []

    logger.info("Fetching %d records from PubMed", len(pmids))
    root = _efetch(pmids, api_key, email)

    papers = []
    for article_el in root.findall("PubmedArticle"):
        paper = _parse_article(article_el)
        if paper:
            papers.append(paper)

    logger.info("Parsed %d papers from PubMed", len(papers))
    return papers
