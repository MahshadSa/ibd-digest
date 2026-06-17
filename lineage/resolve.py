"""Stage 1: resolve a seed DOI to an OpenAlex work and normalize it to a node.

The normalizer (to_node) is shared with traverse.py. resolve and traverse take
an injectable fetch callable so they can run against a fixture in tests; the live
fetch lives in openalex.py.
"""
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# A work with fewer than this many references is flagged ref_complete=False.
# OpenAlex reference coverage is uneven; these nodes are candidates for the
# deferred agentic backfill.
SPARSE_THRESHOLD = 5

Fetch = Callable[[str], dict]


class WorkNotFound(Exception):
    """A fetch ref (DOI or work id) does not exist upstream (HTTP 404).

    Permanent: a re-run will not recover it. traverse skips and counts these
    in unresolved_ids; other errors propagate and abort.
    """


class FetchFailed(Exception):
    """A fetch ref could not be retrieved after bounded retries (transient).

    Connection drop, timeout, 5xx, or rate limit that did not clear. Unlike
    WorkNotFound this is not permanent: a re-run might recover it. traverse
    skips and counts these in failed_ids.
    """


def _short_id(openalex_id: str) -> str:
    """Strip the OpenAlex URL prefix: 'https://openalex.org/W123' -> 'W123'."""
    return openalex_id.rsplit("/", 1)[-1]


def _norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.lower().replace("https://doi.org/", "").strip()


def decode_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Reconstruct abstract text from OpenAlex's abstract_inverted_index.

    The index maps each word to the positions it occupies, so a word appears
    once per position. Expand every position into its own pair before sorting
    so repeated words emit at all their positions, not once. Missing or empty
    index returns None (OpenAlex omits abstracts for some works).
    """
    if not inverted_index:
        return None
    positions = [
        (pos, word) for word, idxs in inverted_index.items() for pos in idxs
    ]
    positions.sort()
    return " ".join(word for _, word in positions)


def to_node(work: dict, depth: int) -> dict:
    """Normalize an OpenAlex work into a lineage node.

    referenced_works is kept on the in-memory node so traverse can build edges;
    store strips it before write (edges carry the same information). in_degree
    and phase are reserved for stages 3 and 4 and stay 0/None this session.
    """
    refs = [_short_id(r) for r in work.get("referenced_works", [])]
    authors = [
        a["author"]["display_name"]
        for a in work.get("authorships", [])
        if a.get("author") and a["author"].get("display_name")
    ]
    return {
        "openalex_id": _short_id(work["id"]),
        "doi": _norm_doi(work.get("doi")),
        "title": work.get("display_name") or work.get("title") or "",
        "abstract": decode_abstract(work.get("abstract_inverted_index")),
        "pub_year": work.get("publication_year"),
        "authors": authors,
        "citation_count": work.get("cited_by_count", 0),
        "ref_complete": len(refs) >= SPARSE_THRESHOLD,
        "depth": depth,
        "in_degree": 0,
        "phase": None,
        "referenced_works": refs,
    }


def resolve(doi: str, fetch: Fetch) -> dict:
    """Fetch the seed work by DOI and return its normalized node at depth 0."""
    ref = doi.lower().strip()
    logger.info("Resolving seed DOI %s", ref)
    work = fetch(ref)
    return to_node(work, depth=0)
