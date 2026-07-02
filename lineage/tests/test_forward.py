"""Forward walk: fetch works citing the seed and the selected groundwork."""
import tempfile
import unittest
from pathlib import Path

from lineage import store
from lineage.forward import build_forward, forward_targets


def _work(wid: str, year: int, cited_by: int = 1, title: str = "") -> dict:
    return {
        "id": f"https://openalex.org/{wid}",
        "display_name": title or f"Citer {wid}",
        "publication_year": year,
        "cited_by_count": cited_by,
        "doi": f"https://doi.org/10.9/{wid.lower()}",
        "authorships": [{"author": {"display_name": "A. Citer"}}],
        "referenced_works": ["https://openalex.org/W1"],
        "abstract_inverted_index": None,
    }


RUN = {
    "schema_version": 2,
    "run_id": "seed-20260701",
    "created_at": "2026-07-01T00:00:00",
    "seed": {"doi": "10.1/seed", "openalex_id": "W1", "title": "Seed"},
    "depth": 2,
    "nodes": [
        {"openalex_id": "W1", "title": "Seed", "pub_year": 2025, "depth": 0,
         "kept": True, "authors": ["S. Author"], "doi": "10.1/seed"},
        {"openalex_id": "W2", "title": "Groundwork", "pub_year": 1990, "depth": 1,
         "kept": True, "authors": ["G. Author"], "doi": "10.1/ground"},
    ],
    "edges": [["W1", "W2"]],
    "meta": {},
}

CITING = {
    "W1": [_work("W10", 2026), _work("W11", 2025)],
    "W2": [_work("W10", 2026), _work("W12", 2024)],
}


class TestForwardTargets(unittest.TestCase):
    def test_seed_plus_selection_ids(self):
        selection = {"selections": [{"openalex_id": "W2", "rationale": "x"}]}
        self.assertEqual(forward_targets(RUN, selection), ["W1", "W2"])

    def test_seed_only_without_selection(self):
        self.assertEqual(forward_targets(RUN, None), ["W1"])

    def test_selection_id_missing_from_run_dropped(self):
        selection = {"selections": [{"openalex_id": "W99", "rationale": "x"}]}
        self.assertEqual(forward_targets(RUN, selection), ["W1"])


class TestBuildForward(unittest.TestCase):
    def test_normalizes_and_dedups_citers(self):
        fwd = build_forward(RUN, ["W1", "W2"], lambda wid: CITING[wid])
        self.assertEqual(fwd["run_id"], "seed-20260701")
        self.assertEqual(fwd["schema_version"], 1)
        citer_ids = {c["openalex_id"] for c in fwd["citers"]}
        self.assertEqual(citer_ids, {"W10", "W11", "W12"})  # W10 deduped
        for citer in fwd["citers"]:
            self.assertNotIn("referenced_works", citer)
            self.assertIn("pub_year", citer)
            self.assertIn("citation_count", citer)
        by_target = {t["openalex_id"]: t["citer_ids"] for t in fwd["targets"]}
        self.assertEqual(set(by_target["W1"]), {"W10", "W11"})
        self.assertEqual(set(by_target["W2"]), {"W10", "W12"})
        self.assertEqual(fwd["meta"]["target_count"], 2)
        self.assertEqual(fwd["meta"]["citer_count"], 3)


class TestForwardSidecarIO(unittest.TestCase):
    def test_write_and_read_roundtrip_overwrite_permitted(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            runs_dir = Path(tmp)
            fwd = build_forward(RUN, ["W1"], lambda wid: CITING[wid])
            path = store.write_forward(fwd, RUN["run_id"], runs_dir)
            self.assertEqual(path, runs_dir / "seed-20260701.forward.json")
            again = store.write_forward(fwd, RUN["run_id"], runs_dir)
            self.assertEqual(again, path)
            back = store.read_forward(RUN["run_id"], runs_dir)
            self.assertEqual(back["meta"]["citer_count"], 2)


if __name__ == "__main__":
    unittest.main()
