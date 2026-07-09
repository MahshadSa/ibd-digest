# Regenerate July Digests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-rank and rewrite the all-archive digests 2026-07-03..08 under the fixed candidate-distribution calibration by re-fetching each paper's metadata by DOI.

**Architecture:** A new `fetch_by_doi` reuses the existing full Crossref/PubMed parsers to return a complete paper dict for one DOI. A one-off `regenerate_digests.py` reads the DOIs from each broken digest, fetches metadata, inserts each paper with `seen_date` pinned to its digest date, then runs the normal corpus/rank/writer/metrics pipeline per date.

**Tech Stack:** Python 3.11+, stdlib `urllib`/`xml.etree`, SQLite, NumPy, SPECTER2, unittest.

## Global Constraints

- No em dashes, no emojis, no decorative comments. Docstrings one line where possible.
- Type hints throughout. Plain, direct Python. stdlib first.
- `logging`, never `print` for logging.
- Tests: stdlib `unittest`, HTTP injected (never hit the network in tests), matching the lineage fetcher pattern. Run: `python -m unittest discover -s tests -t .`.
- Network (Crossref, PubMed) is unreachable from the container. Build and unit-test here; the end-to-end run happens on the laptop.
- Windows: `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)` for DB tests.

## File Structure

- Modify `src/db.py:119-139` — add optional `seen_date` param to `insert_paper`.
- Create `src/fetchers/by_doi.py` — `fetch_by_doi(doi, email, api_key, ...)` returning a full paper dict, reusing `_parse_crossref_item` and `_parse_article`.
- Create `scripts/regenerate_digests.py` — one-off orchestration (DOI extraction per date + pipeline wiring).
- Create `tests/test_by_doi.py` — fetch_by_doi orchestration/parse tests (injected HTTP).
- Create `tests/test_regenerate.py` — per-date DOI extraction test.

---

## Task 1: Optional seen_date on insert_paper

**Files:**
- Modify: `src/db.py:119-139`
- Test: `tests/test_db.py` (create if absent; otherwise append the test class)

**Interfaces:**
- Produces: `insert_paper(conn, paper: dict, seen_date: str | None = None) -> None` (defaults to today when `seen_date` is None; existing callers unaffected).

- [ ] **Step 1: Write the failing test**

Create `tests/test_db.py` (or append the class if the file exists):

```python
import tempfile
import unittest
from pathlib import Path

from src.db import get_connection, insert_paper, migrate, migrate_embedding_columns


def _paper(doi):
    return {
        "doi": doi, "title": "T", "authors": ["A B"],
        "corresponding_author": "A B", "journal": "J",
        "pub_date": "2026-07-04", "abstract": "x", "source": "test",
    }


class TestInsertPaperSeenDate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = str(Path(self.tmp.name) / "papers.db")
        migrate(self.db)
        migrate_embedding_columns(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_seen_date_is_stored(self):
        conn = get_connection(self.db)
        with conn:
            insert_paper(conn, _paper("10.1/a"), seen_date="2026-07-04")
        row = conn.execute(
            "SELECT seen_date FROM papers WHERE doi = '10.1/a'"
        ).fetchone()
        self.assertEqual(row["seen_date"], "2026-07-04")
        conn.close()

    def test_default_seen_date_is_today(self):
        from datetime import date
        conn = get_connection(self.db)
        with conn:
            insert_paper(conn, _paper("10.1/b"))
        row = conn.execute(
            "SELECT seen_date FROM papers WHERE doi = '10.1/b'"
        ).fetchone()
        self.assertEqual(row["seen_date"], date.today().isoformat())
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_db -v`
Expected: FAIL on `test_explicit_seen_date_is_stored` (insert_paper takes no `seen_date`).

- [ ] **Step 3: Modify insert_paper**

In `src/db.py`, replace the function (lines 119-139):

```python
def insert_paper(conn: sqlite3.Connection, paper: dict, seen_date: str | None = None) -> None:
    """Insert a paper dict into papers; skips silently if DOI already exists.

    seen_date defaults to today; regeneration passes the original digest date.
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO papers
            (doi, title, authors, corresponding_author, journal,
             pub_date, abstract, source, seen_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            paper["doi"],
            paper["title"],
            json.dumps(paper["authors"]),
            paper.get("corresponding_author"),
            paper["journal"],
            paper["pub_date"],
            paper.get("abstract"),
            paper["source"],
            seen_date or date.today().isoformat(),
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_db -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_db.py
git commit -m "feat: optional seen_date on insert_paper for backfill"
```

---

## Task 2: fetch_by_doi

**Files:**
- Create: `src/fetchers/by_doi.py`
- Test: `tests/test_by_doi.py`

**Interfaces:**
- Consumes: `_parse_crossref_item` (`src/fetchers/journals.py`), `_parse_article` (`src/fetchers/pubmed.py`).
- Produces:
  - `fetch_by_doi(doi: str, email: str, api_key: str | None, crossref=_http_crossref_work, pubmed=_http_pubmed_article) -> dict | None`
  - `_http_crossref_work(doi: str, email: str) -> dict | None` (returns the Crossref `message` item, or None)
  - `_http_pubmed_article(doi: str, api_key: str | None, email: str) -> xml.etree.ElementTree.Element | None` (returns the first `PubmedArticle` element, or None)

**Orchestration contract (what the tests pin):** try Crossref; if it yields an abstract, return it. Else try PubMed; if that yields an abstract, return it. Else return whichever record exists with abstract=None, or None if neither resolves.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_by_doi.py`:

```python
import unittest
import xml.etree.ElementTree as ET

from src.fetchers.by_doi import fetch_by_doi

# Minimal Crossref /works/{doi} "message" item
CR_WITH_ABSTRACT = {
    "DOI": "10.1/withabs",
    "title": ["Crossref Title"],
    "author": [{"given": "Jane", "family": "Doe"}],
    "container-title": ["Radiology"],
    "published-online": {"date-parts": [[2026, 7, 4]]},
    "abstract": "<p>Crossref abstract text.</p>",
}
CR_NO_ABSTRACT = {
    "DOI": "10.1/noabs",
    "title": ["Crossref Title 2"],
    "author": [{"given": "John", "family": "Roe"}],
    "container-title": ["JMRI"],
    "published-online": {"date-parts": [[2026, 7, 5]]},
}

# Minimal PubmedArticle element with an abstract
PM_XML = """
<PubmedArticle>
  <MedlineCitation>
    <Article>
      <ArticleTitle>PubMed Title</ArticleTitle>
      <Abstract><AbstractText>PubMed abstract text.</AbstractText></Abstract>
      <AuthorList><Author><LastName>Smith</LastName><Initials>A</Initials></Author></AuthorList>
      <Journal><Title>Gut</Title>
        <JournalIssue><PubDate><Year>2026</Year><Month>Jul</Month><Day>5</Day></PubDate></JournalIssue>
      </Journal>
    </Article>
  </MedlineCitation>
  <PubmedData><ArticleIdList>
    <ArticleId IdType="doi">10.1/noabs</ArticleId>
  </ArticleIdList></PubmedData>
</PubmedArticle>
"""


class TestFetchByDoi(unittest.TestCase):
    def test_crossref_with_abstract_returns_full_dict(self):
        p = fetch_by_doi(
            "10.1/withabs", "e@x.com", None,
            crossref=lambda d, e: CR_WITH_ABSTRACT,
            pubmed=lambda d, k, e: None,
        )
        self.assertEqual(p["doi"], "10.1/withabs")
        self.assertEqual(p["title"], "Crossref Title")
        self.assertEqual(p["journal"], "Radiology")
        self.assertEqual(p["pub_date"], "2026-07-04")
        self.assertIn("Crossref abstract", p["abstract"])
        self.assertEqual(p["source"], "crossref-rehydrate")

    def test_falls_back_to_pubmed_when_crossref_has_no_abstract(self):
        p = fetch_by_doi(
            "10.1/noabs", "e@x.com", "key",
            crossref=lambda d, e: CR_NO_ABSTRACT,
            pubmed=lambda d, k, e: ET.fromstring(PM_XML),
        )
        self.assertIn("PubMed abstract", p["abstract"])
        self.assertEqual(p["source"], "pubmed")

    def test_no_abstract_anywhere_returns_crossref_with_null_abstract(self):
        p = fetch_by_doi(
            "10.1/noabs", "e@x.com", "key",
            crossref=lambda d, e: CR_NO_ABSTRACT,
            pubmed=lambda d, k, e: None,
        )
        self.assertEqual(p["doi"], "10.1/noabs")
        self.assertIsNone(p["abstract"])
        self.assertEqual(p["source"], "crossref-rehydrate")

    def test_unresolvable_doi_returns_none(self):
        p = fetch_by_doi(
            "10.1/gone", "e@x.com", "key",
            crossref=lambda d, e: None,
            pubmed=lambda d, k, e: None,
        )
        self.assertIsNone(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_by_doi -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.fetchers.by_doi'`.

- [ ] **Step 3: Write the implementation**

Create `src/fetchers/by_doi.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_by_doi -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fetchers/by_doi.py tests/test_by_doi.py
git commit -m "feat: fetch_by_doi rehydrates a paper from Crossref/PubMed by DOI"
```

---

## Task 3: regenerate_digests.py orchestration

**Files:**
- Create: `scripts/regenerate_digests.py`
- Test: `tests/test_regenerate.py` (DOI extraction only; the pipeline run is laptop end-to-end)

**Interfaces:**
- Consumes: `fetch_by_doi` (Task 2); `insert_paper(..., seen_date=...)` (Task 1); `migrate`, `migrate_embedding_columns`, `get_connection` (`src/db.py`); `rebuild_corpus_from_notes` (`src/corpus.py`); `embed_pending`, `score_and_tier` (`src/ranking/score.py`); `writer.run`, `metrics.run`.
- Produces: `dois_from_digest(path: str) -> list[str]` (ordered, de-duplicated DOIs linked in one digest file); `run(vault_root, db_path, email, api_key) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_regenerate.py`:

```python
import tempfile
import unittest
from pathlib import Path

from scripts.regenerate_digests import dois_from_digest


SAMPLE = """# IBD Imaging Digest - 2026-07-08

- [ ] **Paper One**
  A B, C D
  Radiology | 2026-07-01
  [10.1/aaa](https://doi.org/10.1/aaa) | Score: 0.95

> [!abstract]- Archive (2)
>
> - **Paper Two**
>   E F
>   [10.1/bbb](https://doi.org/10.1/bbb)
>
> - **Paper Three**
>   G H
>   [10.1/aaa](https://doi.org/10.1/aaa)
"""


class TestDoisFromDigest(unittest.TestCase):
    def test_extracts_ordered_unique_dois(self):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "2026-07-08.md"
        path.write_text(SAMPLE, encoding="utf-8")
        self.assertEqual(dois_from_digest(str(path)), ["10.1/aaa", "10.1/bbb"])
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_regenerate -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.regenerate_digests'`.

- [ ] **Step 3: Write the script**

Create `scripts/regenerate_digests.py`:

```python
"""One-off: regenerate the all-archive July digests under the fixed calibration.

Reads the DOIs from each broken digest, re-fetches metadata by DOI, inserts each
paper with seen_date pinned to its digest date, then runs corpus/rank/writer/
metrics per date. Runs on the laptop (Crossref/PubMed unreachable in CI). Not
part of the daily pipeline.
"""
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.corpus import rebuild_corpus_from_notes
from src.db import get_connection, insert_paper, migrate, migrate_embedding_columns
from src.digest import writer
from src.fetchers.by_doi import fetch_by_doi
from src.ranking.score import embed_pending, score_and_tier
from src import metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATES = ["2026-07-03", "2026-07-04", "2026-07-05", "2026-07-06", "2026-07-07", "2026-07-08"]
MODEL_NAME = "allenai/specter2_base"
CORPUS_DIR = "Corpus"
METRICS_PATH = "data/metrics.txt"

_DOI_LINK_RE = re.compile(r"\[([^\]]+)\]\(https://doi\.org/[^)]+\)")


def dois_from_digest(path: str) -> list[str]:
    """Ordered, de-duplicated DOIs linked in one digest file."""
    seen: dict[str, None] = {}
    for m in _DOI_LINK_RE.finditer(Path(path).read_text(encoding="utf-8")):
        doi = m.group(1).strip().lower()
        if doi.startswith("10."):
            seen.setdefault(doi, None)
    return list(seen)


def run(vault_root: str, db_path: str, email: str, api_key: str | None) -> None:
    if Path(db_path).exists():
        Path(db_path).unlink()  # start from a clean DB; the snapshot is expendable
    migrate(db_path)
    migrate_embedding_columns(db_path)
    rebuild_corpus_from_notes(db_path, CORPUS_DIR, MODEL_NAME)

    conn = get_connection(db_path)
    for d in DATES:
        digest = Path(vault_root) / "Inbox" / "Papers" / f"{d}.md"
        dois = dois_from_digest(str(digest))
        logger.info("%s: %d DOIs", d, len(dois))
        for doi in dois:
            paper = fetch_by_doi(doi, email, api_key)
            if paper is None:
                logger.warning("Unresolved DOI, skipping: %s", doi)
                continue
            with conn:
                insert_paper(conn, paper, seen_date=d)
    conn.close()

    embed_pending(db_path, MODEL_NAME)
    score_and_tier(db_path)

    for d in DATES:
        target = date.fromisoformat(d)
        writer.run(db_path, vault_root, target_date=target, force=True)
        metrics.run(db_path, METRICS_PATH, target_date=target)
    logger.info("Regenerated %d digests", len(DATES))


if __name__ == "__main__":
    load_dotenv()
    _vault = sys.argv[1] if len(sys.argv) > 1 else "."
    _db = sys.argv[2] if len(sys.argv) > 2 else "data/papers.db"
    run(_vault, _db, os.environ["NCBI_EMAIL"], os.environ.get("NCBI_API_KEY"))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_regenerate -v`
Expected: PASS (1 test).

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests -t .`
Expected: PASS (all, including the new by_doi/db/regenerate tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/regenerate_digests.py tests/test_regenerate.py
git commit -m "feat: regenerate_digests script for July backfill"
```

---

## Task 4: Laptop end-to-end run (manual, not committed as code)

**This runs on the laptop; Crossref/PubMed are unreachable in the container. Not a code task.**

- [ ] **Step 1: Confirm env**

`NCBI_EMAIL` (and optionally `NCBI_API_KEY`) are set in `.env`. SPECTER2 is cached locally.

- [ ] **Step 2: Run the regeneration**

Run: `.venv/Scripts/python.exe -m scripts.regenerate_digests . data/papers.db`
Expected: per-date "N DOIs" logs, some "Unresolved DOI" warnings are acceptable, ending "Regenerated 6 digests".

- [ ] **Step 3: Verify the result**

Run:
```bash
for d in 03 04 05 06 07 08; do grep -m1 "New papers:" "Inbox/Papers/2026-07-$d.md"; done
tail -8 data/metrics.txt
```
Expected: non-zero Must-read/Skim counts on most days; metrics lines for 07-03..08 show thresholds ~0.947/0.900, not 0.975/0.967.

- [ ] **Step 4: Spot-check a known paper**

Confirm the ECCO UC guideline (10.1093/ecco-jcc/jjag066) on 2026-07-08 is no longer in Archive (now skim or must-read, or at least scored and rendered with its abstract).

- [ ] **Step 5: Commit the regenerated digests**

```bash
git add Inbox/Papers/2026-07-0[3-8].md data/metrics.txt data/score_history.txt
git commit -m "content: regenerate 2026-07-03..08 digests under fixed calibration"
```

---

## Self-Review

**Spec coverage:**
- fetch_by_doi (Crossref + PubMed fallback, title-only when no abstract) -> Task 2.
- Orchestration: fresh DB, corpus from-notes, per-date DOI extraction + seen_date pin, rank, writer/metrics per date -> Task 3.
- seen_date pinning -> Task 1 (insert_paper param) + Task 3 (passes the date).
- Score-history append side effect -> happens inside `score_and_tier` (Task 3 Step 3 calls it); no extra work.
- Testing against fixtures with injected HTTP -> Tasks 1-3; end-to-end -> Task 4.
- Scope 07-03..08 -> `DATES` constant.

**Placeholder scan:** no TBD/TODO; all code shown in full; commands have expected output.

**Type consistency:** `fetch_by_doi(doi, email, api_key, crossref=, pubmed=)` defined in Task 2, called with 3 positional args in Task 3. `insert_paper(conn, paper, seen_date=...)` defined in Task 1, called that way in Task 3. `dois_from_digest(str) -> list[str]` defined and tested in Task 3. `writer.run(db_path, vault_root, target_date=, force=)` and `metrics.run(db_path, out_path, target_date=)` match the real signatures read from the source.

**Note:** `dois_from_digest` matches every doi.org link in the file; a DOI appearing inside an abstract callout would be picked up too. In practice digest abstracts do not contain doi.org links, and a stray extra DOI would just be re-fetched and tiered, not corrupt anything. Accepted.
