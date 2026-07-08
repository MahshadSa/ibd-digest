# Candidate-Distribution Threshold Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw tier cutoffs from the distribution of candidate scores the system actually produces, instead of from corpus self-similarity, so niche-relevant papers stop being archived.

**Architecture:** Persist candidate scores to a committed rolling-window text file (`data/score_history.txt`). Each run appends the day's scores, then computes must/skim thresholds as percentiles of that window. `score_and_tier` splits into two passes (score all, calibrate, then tier). A one-off bootstrap seeds the window from the local DB snapshot.

**Tech Stack:** Python 3.11+, NumPy, SQLite (stdlib `sqlite3`), unittest.

## Global Constraints

- No em dashes anywhere (code, comments, docs, commit messages).
- No emojis.
- No decorative comments; comment only non-obvious "why". Docstrings one line where possible.
- Type hints throughout. Plain, direct Python. Prefer stdlib.
- Use the `logging` module, never `print` for logging.
- Tests: stdlib `unittest`. Run digest suite with `python -m unittest discover -s tests -t .`.
- Windows: use `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)` in DB tests (sqlite file-handle timing).

---

## File Structure

- Create `src/ranking/history.py` — score-history persistence (load, append, cap). One responsibility: the rolling-window file IO.
- Modify `src/ranking/score.py` — `compute_thresholds` signature + percentiles; `score_and_tier` two-pass with history integration; extract `_load_corpus` and `score_papers` helpers (reused by the bootstrap).
- Create `scripts/bootstrap_score_history.py` — one-off seed of `data/score_history.txt` from the DB snapshot.
- Modify `tests/test_score.py` — rewrite threshold/score_and_tier tests to the new mechanism.
- Create `tests/test_history.py` — tests for the new persistence helpers.
- Modify `.github/workflows/daily-digest.yml` — add the new file to the commit step.
- Modify `CLAUDE.md`, `README.md` — document the mechanism switch.
- Create `data/score_history.txt` — the seeded window (committed artifact, produced by Task 4).

---

## Task 1: Score-history persistence helpers

**Files:**
- Create: `src/ranking/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SCORE_HISTORY_CAP: int` (= 2000)
  - `load_score_history(path: str) -> np.ndarray` (1-D float array; empty array if the file is absent or blank)
  - `append_scores(path: str, scores: list[float], cap: int = SCORE_HISTORY_CAP) -> None` (appends in order, then keeps only the last `cap` lines)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history.py`:

```python
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.ranking.history import (
    SCORE_HISTORY_CAP,
    append_scores,
    load_score_history,
)


class TestScoreHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "score_history.txt")

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_file_returns_empty(self):
        arr = load_score_history(self.path)
        self.assertEqual(arr.size, 0)

    def test_append_then_load_roundtrip_in_order(self):
        append_scores(self.path, [0.1, 0.2, 0.3])
        arr = load_score_history(self.path)
        np.testing.assert_allclose(arr, [0.1, 0.2, 0.3], atol=1e-6)

    def test_append_is_additive_and_ordered(self):
        append_scores(self.path, [0.1, 0.2])
        append_scores(self.path, [0.3])
        arr = load_score_history(self.path)
        np.testing.assert_allclose(arr, [0.1, 0.2, 0.3], atol=1e-6)

    def test_cap_keeps_last_n(self):
        append_scores(self.path, [0.1, 0.2, 0.3, 0.4, 0.5], cap=3)
        arr = load_score_history(self.path)
        np.testing.assert_allclose(arr, [0.3, 0.4, 0.5], atol=1e-6)

    def test_cap_default_is_2000(self):
        self.assertEqual(SCORE_HISTORY_CAP, 2000)

    def test_load_ignores_blank_lines(self):
        Path(self.path).write_text("0.1\n\n0.2\n", encoding="utf-8")
        arr = load_score_history(self.path)
        np.testing.assert_allclose(arr, [0.1, 0.2], atol=1e-6)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_history -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ranking.history'`.

- [ ] **Step 3: Write the implementation**

Create `src/ranking/history.py`:

```python
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SCORE_HISTORY_CAP = 2000


def load_score_history(path: str) -> np.ndarray:
    """Return the persisted rolling window of candidate scores. Empty if absent.

    The papers table is rebuilt empty each scheduled run, so tier calibration
    cannot rely on it; this committed text file is the durable candidate-score
    distribution the thresholds are drawn from.
    """
    p = Path(path)
    if not p.exists():
        return np.array([], dtype=np.float64)
    values = [
        float(line.strip())
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return np.array(values, dtype=np.float64)


def append_scores(
    path: str, scores: list[float], cap: int = SCORE_HISTORY_CAP
) -> None:
    """Append scores in order, then keep only the last `cap` (FIFO from front)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = [
        line.strip()
        for line in (
            p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        )
        if line.strip()
    ]
    combined = existing + [f"{s:.6f}" for s in scores]
    combined = combined[-cap:]
    p.write_text("\n".join(combined) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_history -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ranking/history.py tests/test_history.py
git commit -m "feat: rolling score-history persistence for tier calibration"
```

---

## Task 2: Recalibrate `compute_thresholds` on the candidate distribution

**Files:**
- Modify: `src/ranking/score.py:20-56` (the percentile constants and `compute_thresholds`)
- Test: `tests/test_score.py` (rewrite `TestComputeThresholds`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `compute_thresholds(score_history: np.ndarray) -> tuple[float, float]`; module constants `MUST_PERCENTILE = 85`, `SKIM_PERCENTILE = 40`.

- [ ] **Step 1: Rewrite the failing test**

In `tests/test_score.py`, replace the entire `class TestComputeThresholds` (lines 49-65) with:

```python
class TestComputeThresholds(unittest.TestCase):
    def test_small_history_falls_back_to_fixed(self):
        history = np.array([0.9, 0.91, 0.92], dtype=np.float64)
        must, skim = compute_thresholds(history)
        self.assertEqual(must, FALLBACK_MUST_READ)
        self.assertEqual(skim, FALLBACK_SKIM)

    def test_percentiles_of_history(self):
        history = np.linspace(0.80, 0.99, 100)
        must, skim = compute_thresholds(history)
        self.assertAlmostEqual(must, float(np.percentile(history, 85)), places=6)
        self.assertAlmostEqual(skim, float(np.percentile(history, 40)), places=6)

    def test_must_at_least_skim(self):
        history = np.linspace(0.80, 0.99, 100)
        must, skim = compute_thresholds(history)
        self.assertGreaterEqual(must, skim)
```

Also delete the now-unused `CORPUS_VECS`/`LOO_DIST` module constants (lines 26-36) ONLY IF no other test references them. Note: `TestScoreAndTier` still uses `CORPUS_VECS` (rewritten in Task 3) so keep `CORPUS_VECS`; remove `LOO_DIST` at the end of Task 3 when its last reference is gone. For now, leave both in place.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_score.TestComputeThresholds -v`
Expected: FAIL (compute_thresholds still expects a corpus matrix; `test_percentiles_of_history` gets wrong values or the fallback path differs).

- [ ] **Step 3: Rewrite the implementation**

In `src/ranking/score.py`, change the percentile constants (lines 20-21):

```python
TOP_K_SIM = 3
MIN_CALIBRATION = 5
MUST_PERCENTILE = 85
SKIM_PERCENTILE = 40
```

Replace `compute_thresholds` (lines 32-56) with:

```python
def compute_thresholds(score_history: np.ndarray) -> tuple[float, float]:
    """Percentile-anchored tier thresholds from the candidate-score distribution.

    The thresholds are the MUST_PERCENTILE / SKIM_PERCENTILE percentiles of the
    scores candidates have actually produced (the persisted rolling window), so
    the cutoffs track where papers land rather than how self-similar the corpus
    is. Falls back to the fixed constants when the window is too small.
    """
    if score_history.size < MIN_CALIBRATION:
        logger.warning(
            "Score history too small to calibrate (%d < %d); using fallbacks",
            score_history.size,
            MIN_CALIBRATION,
        )
        return FALLBACK_MUST_READ, FALLBACK_SKIM
    must = float(np.percentile(score_history, MUST_PERCENTILE))
    skim = float(np.percentile(score_history, SKIM_PERCENTILE))
    return must, skim
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_score.TestComputeThresholds tests.test_score.TestTopKMean tests.test_score.TestAssignTier -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ranking/score.py tests/test_score.py
git commit -m "feat: calibrate tier thresholds from candidate-score distribution"
```

---

## Task 3: Two-pass `score_and_tier` with history integration

**Files:**
- Modify: `src/ranking/score.py:99-168` (`score_and_tier`), and add `_load_corpus` / `score_papers` helpers.
- Test: `tests/test_score.py` (rewrite `TestScoreAndTier`).

**Interfaces:**
- Consumes: `load_score_history`, `append_scores` (Task 1); `compute_thresholds` (Task 2); existing `top_k_mean`, `assign_tier`, `get_connection`, `set_meta`.
- Produces:
  - `_load_corpus(conn) -> tuple[list[str], np.ndarray]` (corpus DOIs and L2-normalized corpus matrix)
  - `score_papers(corpus_dois: list[str], corpus_normed: np.ndarray, paper_rows) -> list[tuple[str, float, str]]` (returns `(doi, score, matching_corpus_doi)` per scorable paper)
  - `score_and_tier(db_path: str, score_history_path: str = "data/score_history.txt") -> int`

- [ ] **Step 1: Rewrite the failing test**

In `tests/test_score.py`, replace the entire `class TestScoreAndTier` (lines 77-131) with:

```python
class TestScoreAndTier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self.tmp.name) / "papers.db")
        self.history_path = str(Path(self.tmp.name) / "score_history.txt")
        migrate(self.db_path)
        migrate_embedding_columns(self.db_path)
        conn = get_connection(self.db_path)
        with conn:
            for i, vec in enumerate(CORPUS_VECS):
                conn.execute(
                    "INSERT INTO corpus (doi, title, abstract, embedding, added_date)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (f"10.1/corpus{i}", f"Corpus {i}", "", vec.tobytes(), "2026-01-01"),
                )
            for doi, vec in [
                ("10.1/paper-a", _unit([1, 0, 0])),
                ("10.1/paper-b", _unit([0, 0, 1])),
            ]:
                conn.execute(
                    "INSERT INTO papers (doi, title, authors, journal, pub_date,"
                    " source, seen_date, embedding)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (doi, doi, json.dumps(["A"]), "J", "2026-01-01", "test",
                     "2026-01-01", vec.tobytes()),
                )
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_history(self, values):
        # A window whose 85th pct is 0.90 and 40th pct is 0.50, so paper-a
        # (score 1.0) is must-read and paper-b (score 0.0) is archive.
        from src.ranking.history import append_scores
        append_scores(self.history_path, values)

    def test_scores_tiers_and_meta(self):
        # 10 values: p85 ~ 0.905, p40 ~ 0.5
        self._seed_history([0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.92, 0.95])
        n = score_and_tier(self.db_path, self.history_path)
        self.assertEqual(n, 2)
        conn = get_connection(self.db_path)
        a = conn.execute("SELECT * FROM papers WHERE doi = '10.1/paper-a'").fetchone()
        b = conn.execute("SELECT * FROM papers WHERE doi = '10.1/paper-b'").fetchone()
        self.assertAlmostEqual(a["similarity_score"], 1.0, places=5)
        self.assertEqual(a["matching_corpus_doi"], "10.1/corpus0")
        self.assertEqual(a["tier"], "must-read")
        self.assertAlmostEqual(b["similarity_score"], 0.0, places=5)
        self.assertEqual(b["tier"], "archive")
        self.assertIsNotNone(get_meta(conn, "tier_threshold_must"))
        self.assertIsNotNone(get_meta(conn, "tier_threshold_skim"))
        conn.close()

    def test_appends_this_runs_scores_to_history(self):
        from src.ranking.history import load_score_history
        self._seed_history([0.5] * 5)
        before = load_score_history(self.history_path).size
        score_and_tier(self.db_path, self.history_path)
        after = load_score_history(self.history_path).size
        self.assertEqual(after, before + 2)  # two scorable papers appended
```

Now remove the `LOO_DIST` constant (lines 36) since its last reference is gone.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_score.TestScoreAndTier -v`
Expected: FAIL (`score_and_tier` does not accept `score_history_path`).

- [ ] **Step 3: Rewrite the implementation**

In `src/ranking/score.py`, update the imports at the top to add the history helpers:

```python
from src.ranking.history import append_scores, load_score_history
```

Add these two helpers above `score_and_tier`:

```python
def _load_corpus(conn) -> tuple[list[str], np.ndarray]:
    """Return corpus DOIs and the L2-normalized corpus embedding matrix."""
    rows = conn.execute(
        "SELECT doi, embedding FROM corpus WHERE embedding IS NOT NULL"
    ).fetchall()
    dois = [r["doi"] for r in rows]
    matrix = np.vstack(
        [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
    )
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return dois, matrix / np.maximum(norms, 1e-8)


def score_papers(
    corpus_dois: list[str], corpus_normed: np.ndarray, paper_rows
) -> list[tuple[str, float, str]]:
    """Score each paper as top-k mean cosine vs corpus.

    Returns (doi, score, matching_corpus_doi) per scorable paper; papers with a
    degenerate (zero-norm) embedding are skipped.
    """
    scored: list[tuple[str, float, str]] = []
    for row in paper_rows:
        emb = np.frombuffer(row["embedding"], dtype=np.float32)
        norm = np.linalg.norm(emb)
        if norm < 1e-8:
            continue
        sims = corpus_normed @ (emb / norm)
        best_idx = int(np.argmax(sims))
        scored.append((row["doi"], top_k_mean(sims), corpus_dois[best_idx]))
    return scored
```

Replace `score_and_tier` (lines 99-168) with:

```python
def score_and_tier(
    db_path: str, score_history_path: str = "data/score_history.txt"
) -> int:
    """Score papers vs corpus, append scores to the history window, calibrate
    thresholds from that window, then tier. Returns count updated.

    Two-pass: scoring is independent of the thresholds, and the thresholds come
    from the accumulated candidate-score distribution (this run's scores
    included), so scoring must complete before tiering.
    """
    conn = get_connection(db_path)

    corpus_dois, corpus_normed = _load_corpus(conn)
    if not corpus_dois:
        logger.warning("Corpus is empty; cannot score papers")
        conn.close()
        return 0

    paper_rows = conn.execute(
        "SELECT doi, embedding FROM papers WHERE embedding IS NOT NULL"
    ).fetchall()
    if not paper_rows:
        logger.info("No papers with embeddings to score")
        conn.close()
        return 0

    scored = score_papers(corpus_dois, corpus_normed, paper_rows)

    append_scores(score_history_path, [s for _, s, _ in scored])
    window = load_score_history(score_history_path)
    must_threshold, skim_threshold = compute_thresholds(window)
    logger.info(
        "Tier thresholds this run: must-read >= %.4f, skim >= %.4f (window n=%d)",
        must_threshold,
        skim_threshold,
        window.size,
    )
    with conn:
        set_meta(conn, "tier_threshold_must", f"{must_threshold:.6f}")
        set_meta(conn, "tier_threshold_skim", f"{skim_threshold:.6f}")
        for doi, score, matching_doi in scored:
            conn.execute(
                """
                UPDATE papers
                SET similarity_score = ?, matching_corpus_doi = ?, tier = ?
                WHERE doi = ?
                """,
                (score, matching_doi, assign_tier(score, must_threshold, skim_threshold), doi),
            )

    conn.close()
    logger.info("Scored and tiered %d papers", len(scored))
    return len(scored)
```

- [ ] **Step 4: Run the full score + history suites**

Run: `python -m unittest tests.test_score tests.test_history -v`
Expected: PASS (all classes).

- [ ] **Step 5: Commit**

```bash
git add src/ranking/score.py tests/test_score.py
git commit -m "feat: two-pass score_and_tier calibrated from score history"
```

---

## Task 4: Bootstrap the score-history window from the DB snapshot

**Files:**
- Create: `scripts/bootstrap_score_history.py`
- Create (output, committed): `data/score_history.txt`

**Interfaces:**
- Consumes: `_load_corpus`, `score_papers` (Task 3); `append_scores` (Task 1); `get_connection`.
- Produces: the seeded `data/score_history.txt`.

**Precondition:** the local `data/papers.db` holds the ~1233-paper snapshot with embeddings, and its `corpus` table reflects the current 42 notes. The corpus has not changed since the initial build, so the DB corpus is current; if in doubt, run `python -m src.corpus from-notes data/papers.db` first to re-embed the committed notes into the DB.

- [ ] **Step 1: Write the bootstrap script**

Create `scripts/bootstrap_score_history.py`:

```python
"""One-off: seed data/score_history.txt from the local DB snapshot.

Re-scores every embedded paper in data/papers.db against the current corpus and
writes the scores as the initial calibration window. Not part of the daily
pipeline. Run once, locally, then commit data/score_history.txt.
"""
import logging
import sys

from src.db import get_connection
from src.ranking.history import append_scores
from src.ranking.score import _load_corpus, score_papers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run(db_path: str, history_path: str) -> int:
    conn = get_connection(db_path)
    corpus_dois, corpus_normed = _load_corpus(conn)
    if not corpus_dois:
        conn.close()
        sys.exit("corpus table is empty; run: python -m src.corpus from-notes " + db_path)
    paper_rows = conn.execute(
        "SELECT doi, embedding FROM papers WHERE embedding IS NOT NULL"
    ).fetchall()
    conn.close()
    scored = score_papers(corpus_dois, corpus_normed, paper_rows)
    append_scores(history_path, [s for _, s, _ in scored])
    logger.info("Seeded %s with %d scores", history_path, len(scored))
    return len(scored)


if __name__ == "__main__":
    _db = sys.argv[1] if len(sys.argv) > 1 else "data/papers.db"
    _hist = sys.argv[2] if len(sys.argv) > 2 else "data/score_history.txt"
    run(_db, _hist)
```

- [ ] **Step 2: Confirm the history file does not already exist**

Run: `ls data/score_history.txt 2>/dev/null && echo EXISTS || echo ABSENT`
Expected: `ABSENT`. If it EXISTS, delete it first (`rm data/score_history.txt`) so the seed is clean.

- [ ] **Step 3: Run the bootstrap**

Run: `.venv/Scripts/python.exe -m scripts.bootstrap_score_history`
Expected: log line `Seeded data/score_history.txt with 1233 scores` (count may differ slightly if some embeddings are degenerate).

- [ ] **Step 4: Verify the seeded distribution gives sane thresholds**

Run:
```bash
.venv/Scripts/python.exe -c "import numpy as np; from src.ranking.history import load_score_history; from src.ranking.score import compute_thresholds; w=load_score_history('data/score_history.txt'); m,s=compute_thresholds(w); print('n=%d must=%.4f skim=%.4f'%(w.size,m,s))"
```
Expected: `n≈1233 must≈0.95 skim≈0.90` (must in ~0.94-0.96, skim in ~0.90-0.91). If must is ~0.97+, the corpus table was stale; run `python -m src.corpus from-notes data/papers.db`, delete and re-seed.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap_score_history.py data/score_history.txt
git commit -m "feat: bootstrap script and seeded score-history window"
```

---

## Task 5: Wire into the workflow and update docs

**Files:**
- Modify: `.github/workflows/daily-digest.yml:77`
- Modify: `CLAUDE.md` (Ranking section; 2026-07-02 overhaul scoring note)
- Modify: `README.md` ("Rank" step; "Ranking calibration" section)

**Interfaces:**
- Consumes: `data/score_history.txt` produced by Task 4.
- Produces: nothing code-facing.

- [ ] **Step 1: Add the file to the workflow commit step**

In `.github/workflows/daily-digest.yml`, change the `git add` line (line 77) from:

```
          git add Inbox/Papers/ "Inbox/To Read.md" Inbox/Column/ Corpus/ data/seen_dois.txt data/metrics.txt
```

to:

```
          git add Inbox/Papers/ "Inbox/To Read.md" Inbox/Column/ Corpus/ data/seen_dois.txt data/metrics.txt data/score_history.txt
```

- [ ] **Step 2: Update CLAUDE.md**

In `CLAUDE.md`, in the `### Ranking` section, replace the tier-calibration paragraph (the one beginning "Tiers are SELF-CALIBRATING per run") with:

```
- Tiers are SELF-CALIBRATING per run: thresholds are the 85th (must-read) and
  40th (skim) percentiles of the CANDIDATE-score distribution, a rolling window
  of the scores papers actually produced, persisted in data/score_history.txt
  (last 2000 scores). This replaced the corpus leave-one-out calibration on
  2026-07-08: that version drew cutoffs from corpus self-similarity, which sat
  at the 96th/98th percentile of real candidate scores, so every run archived
  100% of papers (see data/metrics.txt 07-03 through 07-08). compute_thresholds
  in src/ranking/score.py; values recorded in the DB meta table
  (tier_threshold_must/skim) and data/metrics.txt. Fixed fallbacks
  (0.958/0.924) apply only when the window is under 5 scores. Anchor knobs:
  MUST_PERCENTILE/SKIM_PERCENTILE in src/ranking/score.py.
```

- [ ] **Step 3: Update README.md**

In `README.md`, in the numbered "Rank" step (item 3), replace "using thresholds recalibrated every run from the corpus's own leave-one-out similarity distribution (90th and 50th percentiles)" with:

```
using thresholds recalibrated every run as the 85th and 40th percentiles of the
rolling candidate-score distribution (data/score_history.txt), so the cutoffs
track where incoming papers actually land
```

In the `### Ranking calibration` section, replace its body with:

```
SPECTER2 produces high cosine similarities for in-domain biomedical text, so
fixed thresholds do not generalize. Thresholds self-calibrate every run as the
85th (must-read) and 40th (skim) percentiles of a rolling window of candidate
scores (data/score_history.txt, last 2000). Calibrating on the candidate
distribution, not on corpus self-similarity, is deliberate: the earlier
corpus-leave-one-out cutoffs sat at the 96th/98th percentile of real candidate
scores and archived everything. The values are logged per run in
data/metrics.txt; watch that file for tier drift. Fixed fallbacks apply only
below 5 scores in the window.
```

- [ ] **Step 4: Run the full digest suite**

Run: `python -m unittest discover -s tests -t .`
Expected: PASS (all tests, including the rewritten score/history suites).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/daily-digest.yml CLAUDE.md README.md
git commit -m "docs: candidate-distribution calibration in workflow and docs"
```

---

## Self-Review

**Spec coverage:**
- Score history persistence (spec 1) -> Task 1.
- Threshold computation on candidate distribution + anchors 85/40 (spec 2) -> Task 2.
- Two-pass score_and_tier + history path param (spec 3) -> Task 3.
- Bootstrap from DB snapshot (spec 4) -> Task 4.
- Workflow commit (spec 5) -> Task 5 Step 1.
- Tests (spec Testing) -> Tasks 1-3 (history, thresholds, score_and_tier, fallback via `test_small_history_falls_back_to_fixed`; `top_k_mean`/`assign_tier` untouched).
- Docs (spec Documentation) -> Task 5 Steps 2-3.
- Out-of-scope items -> not touched (scoring method, wildcard, feedback loop, label tuning).

**Type consistency:** `load_score_history`/`append_scores`/`SCORE_HISTORY_CAP` (Task 1) are imported and called with matching signatures in Tasks 3 and 4. `_load_corpus`/`score_papers` (Task 3) called with matching signatures in Task 4. `compute_thresholds(np.ndarray)` (Task 2) called with `window` (an ndarray) in Task 3. `score_and_tier(db_path, score_history_path=...)` consistent between Task 3 definition and Task 3 tests.

**Placeholder scan:** no TBD/TODO; all code shown in full; commands have expected output.

**Note carried from spec review:** locally `score_and_tier` re-scores the whole DB each run (appending a large batch); the FIFO cap absorbs it and the distribution stays valid. No code change needed.
