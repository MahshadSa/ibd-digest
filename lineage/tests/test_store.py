import tempfile
import unittest
from datetime import date
from pathlib import Path

from lineage import store
from lineage.tests.fixture import SEED_DOI, make_fetch
from lineage.traverse import build_run


class TestStore(unittest.TestCase):
    def test_make_run_id(self):
        run_id = store.make_run_id("10.1000/Seed", date(2026, 6, 14))
        self.assertEqual(run_id, "10-1000-seed-20260614")

    def test_write_then_read_round_trip(self):
        run = build_run(SEED_DOI, make_fetch()[0], depth=2)
        with tempfile.TemporaryDirectory() as tmp:
            path = store.write_run(run, runs_dir=Path(tmp))
            self.assertTrue(path.exists())
            loaded = store.read_run(path)
            self.assertEqual(loaded, run)

    def test_refuse_overwrite(self):
        run = build_run(SEED_DOI, make_fetch()[0], depth=2)
        with tempfile.TemporaryDirectory() as tmp:
            store.write_run(run, runs_dir=Path(tmp))
            with self.assertRaises(FileExistsError):
                store.write_run(run, runs_dir=Path(tmp))

    def test_missing_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                store.write_run({"run_id": "x"}, runs_dir=Path(tmp))


if __name__ == "__main__":
    unittest.main()
