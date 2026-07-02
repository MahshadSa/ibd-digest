import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.db import get_connection, migrate, migrate_embedding_columns, set_meta
from src.metrics import run as metrics_run


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self.tmp.name) / "papers.db")
        self.out_path = Path(self.tmp.name) / "metrics.txt"
        migrate(self.db_path)
        migrate_embedding_columns(self.db_path)
        conn = get_connection(self.db_path)
        with conn:
            for i, tier in enumerate(["must-read", "must-read", "skim", "archive"]):
                conn.execute(
                    "INSERT INTO papers (doi, title, authors, journal, pub_date,"
                    " source, seen_date, tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"10.1/p{i}", f"P{i}", json.dumps(["A"]), "J", "2026-07-01",
                     "test", "2026-07-02", tier),
                )
            set_meta(conn, "tier_threshold_must", "0.958000")
            set_meta(conn, "tier_threshold_skim", "0.924000")
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_appends_one_line_per_run(self):
        metrics_run(self.db_path, str(self.out_path), date(2026, 7, 2))
        lines = self.out_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            lines[0],
            "2026-07-02 new=4 must=2 skim=1 archive=1"
            " thr_must=0.958000 thr_skim=0.924000",
        )

    def test_rerun_same_date_replaces_line(self):
        metrics_run(self.db_path, str(self.out_path), date(2026, 7, 2))
        metrics_run(self.db_path, str(self.out_path), date(2026, 7, 2))
        lines = self.out_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)

    def test_second_date_appends(self):
        metrics_run(self.db_path, str(self.out_path), date(2026, 7, 2))
        metrics_run(self.db_path, str(self.out_path), date(2026, 7, 3))
        lines = self.out_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("2026-07-03 new=0"))


if __name__ == "__main__":
    unittest.main()
