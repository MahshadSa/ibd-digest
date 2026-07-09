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
