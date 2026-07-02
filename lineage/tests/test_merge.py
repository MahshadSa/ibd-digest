"""Multi-seed merge: shared ancestors across independent crawls gain real in_degree."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from lineage import store
from lineage.merge import merge_runs
from lineage.select import build_payload


def _node(oid: str, year: int, depth: int, title: str = "") -> dict:
    return {
        "openalex_id": oid,
        "doi": f"10.1/{oid.lower()}",
        "title": title or f"Paper {oid}",
        "abstract": None,
        "pub_year": year,
        "authors": ["A. Author"],
        "citation_count": 1,
        "ref_complete": True,
        "depth": depth,
        "in_degree": 0,
        "phase": None,
    }


RUN_A = {
    "schema_version": 1,
    "run_id": "seed-a-20260701",
    "created_at": "2026-07-01T00:00:00",
    "seed": {"doi": "10.1/wa", "openalex_id": "WA", "title": "Seed A"},
    "depth": 2,
    "top_k": 15,
    "nodes": [_node("WA", 2020, 0), _node("W1", 2000, 1), _node("W2", 1990, 2)],
    "edges": [["WA", "W1"], ["W1", "W2"]],
    "meta": {"unresolved_count": 1, "failed_count": 0},
}

RUN_B = {
    "schema_version": 1,
    "run_id": "seed-b-20260701",
    "created_at": "2026-07-01T00:00:00",
    "seed": {"doi": "10.1/wb", "openalex_id": "WB", "title": "Seed B"},
    "depth": 2,
    "top_k": 15,
    "nodes": [_node("WB", 2021, 0), _node("W2", 1990, 1), _node("W3", 1980, 2)],
    "edges": [["WB", "W2"], ["W2", "W3"]],
    "meta": {"unresolved_count": 2, "failed_count": 0},
}


class TestMergeRuns(unittest.TestCase):
    def setUp(self):
        self.merged = merge_runs([RUN_A, RUN_B], "IBD imaging")

    def test_run_id_and_schema(self):
        self.assertEqual(
            self.merged["run_id"], f"ibd-imaging-merged-{date.today():%Y%m%d}"
        )
        self.assertEqual(self.merged["schema_version"], 2)

    def test_nodes_union_with_seed_count(self):
        by_id = {n["openalex_id"]: n for n in self.merged["nodes"]}
        self.assertEqual(set(by_id), {"WA", "WB", "W1", "W2", "W3"})
        self.assertEqual(by_id["W2"]["seed_count"], 2)
        self.assertEqual(by_id["W1"]["seed_count"], 1)
        # min depth kept for the shared ancestor (2 in A, 1 in B)
        self.assertEqual(by_id["W2"]["depth"], 1)
        self.assertTrue(all(n["kept"] for n in self.merged["nodes"]))

    def test_in_degree_recomputed_across_runs(self):
        by_id = {n["openalex_id"]: n for n in self.merged["nodes"]}
        self.assertEqual(by_id["W2"]["in_degree"], 2)  # cited by W1 and WB
        self.assertEqual(by_id["W1"]["in_degree"], 1)
        self.assertEqual(by_id["WA"]["in_degree"], 0)

    def test_phases_assigned(self):
        by_id = {n["openalex_id"]: n for n in self.merged["nodes"]}
        self.assertEqual(by_id["W2"]["phase"], 1990)
        self.assertEqual(by_id["W3"]["phase"], 1980)

    def test_meta_records_provenance(self):
        meta = self.merged["meta"]
        self.assertEqual(meta["merged_from"], ["seed-a-20260701", "seed-b-20260701"])
        self.assertEqual([s["openalex_id"] for s in meta["seeds"]], ["WA", "WB"])
        self.assertEqual(meta["node_count"], 5)
        self.assertEqual(meta["edge_count"], 4)
        self.assertEqual(meta["unresolved_count"], 3)

    def test_writable_via_store(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = store.write_run(self.merged, Path(tmp))
            self.assertTrue(path.exists())

    def test_payload_shows_seed_count(self):
        payload = build_payload(self.merged)
        self.assertIn("in 2/2 seed trees", payload)


if __name__ == "__main__":
    unittest.main()
