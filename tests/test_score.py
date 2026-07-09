import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.db import get_connection, get_meta, migrate, migrate_embedding_columns
from src.ranking.score import (
    FALLBACK_MUST_READ,
    FALLBACK_SKIM,
    MIN_CALIBRATION,
    assign_tier,
    compute_thresholds,
    score_and_tier,
    top_k_mean,
)


def _unit(v: list[float]) -> np.ndarray:
    a = np.array(v, dtype=np.float32)
    return a / np.linalg.norm(a)


# 5 corpus vectors: three copies of e1, two of e2. Leave-one-out top-3 mean
# similarities are hand-derivable: e1 rows see [1, 1, 0, 0] -> 2/3, e2 rows
# see [0, 0, 0, 1] -> 1/3.
CORPUS_VECS = [
    _unit([1, 0, 0]),
    _unit([1, 0, 0]),
    _unit([1, 0, 0]),
    _unit([0, 1, 0]),
    _unit([0, 1, 0]),
]


class TestTopKMean(unittest.TestCase):
    def test_uses_top_three(self):
        sims = np.array([0.9, 0.1, 0.8, 0.7])
        self.assertAlmostEqual(top_k_mean(sims, 3), (0.9 + 0.8 + 0.7) / 3, places=6)

    def test_fewer_sims_than_k_uses_all(self):
        sims = np.array([0.6, 0.4])
        self.assertAlmostEqual(top_k_mean(sims, 3), 0.5, places=6)


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


class TestAssignTier(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(assign_tier(0.96, 0.95, 0.90), "must-read")
        self.assertEqual(assign_tier(0.95, 0.95, 0.90), "must-read")
        self.assertEqual(assign_tier(0.92, 0.95, 0.90), "skim")
        self.assertEqual(assign_tier(0.90, 0.95, 0.90), "skim")
        self.assertEqual(assign_tier(0.89, 0.95, 0.90), "archive")


class TestScoreAndTier(unittest.TestCase):
    def setUp(self):
        # ignore_cleanup_errors: Windows can briefly hold the sqlite file handle
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
        from src.ranking.history import append_scores
        append_scores(self.history_path, values)

    def test_scores_tiers_and_meta(self):
        # 10 values: p85 ~ 0.905, p40 ~ 0.5, so paper-a (score 1.0) is must-read
        # and paper-b (score 0.0) is archive.
        self._seed_history([0.0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.92, 0.95])
        n = score_and_tier(self.db_path, self.history_path)
        self.assertEqual(n, 2)
        conn = get_connection(self.db_path)
        a = conn.execute(
            "SELECT * FROM papers WHERE doi = '10.1/paper-a'"
        ).fetchone()
        b = conn.execute(
            "SELECT * FROM papers WHERE doi = '10.1/paper-b'"
        ).fetchone()
        # paper-a sims vs corpus: [1, 1, 1, 0, 0] -> top-3 mean 1.0
        self.assertAlmostEqual(a["similarity_score"], 1.0, places=5)
        self.assertEqual(a["matching_corpus_doi"], "10.1/corpus0")
        self.assertEqual(a["tier"], "must-read")
        # paper-b is orthogonal to every corpus vector -> score 0 -> archive
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


if __name__ == "__main__":
    unittest.main()
