import tempfile
import unittest
from pathlib import Path

from lineage import store
from lineage.prune import _kept_subgraph_in_degree, _phase, prune
from lineage.tests.fixture import SEED_DOI, make_fetch
from lineage.traverse import build_run

# The real enriched runs carry the 190/217-node fan-out and the off-topic old
# ancestors the fixture cannot reproduce. Tests that need them skip when absent
# (they are not committed); the fixture-based tests below cover the logic.
# Selection sidecars (runs/{run_id}.selection.json) share the date suffix but
# are not crawl runs, so they are excluded.
REAL_RUNS = sorted(
    p for p in Path("runs").glob("*-2026*.json") if not p.name.endswith(".selection.json")
)


class TestPrune(unittest.TestCase):
    def setUp(self):
        self.run = build_run(SEED_DOI, make_fetch()[0], depth=2)
        prune(self.run)

    def test_keeps_every_node(self):
        self.assertTrue(all(n["kept"] for n in self.run["nodes"]))

    def test_counts(self):
        n = len(self.run["nodes"])
        self.assertEqual(self.run["meta"]["kept_count"], n)
        self.assertEqual(self.run["meta"]["pruned_count"], 0)

    def test_schema_bumped_to_2(self):
        self.assertEqual(self.run["schema_version"], 2)

    def test_in_degree_filled_from_edges(self):
        # W4000000006 is referenced by two parents (see test_traverse edges).
        by_id = {n["openalex_id"]: n for n in self.run["nodes"]}
        self.assertEqual(by_id["W4000000006"]["in_degree"], 2)
        self.assertEqual(by_id["W4000000007"]["in_degree"], 2)
        self.assertEqual(by_id["W2000000001"]["in_degree"], 0)

    def test_phase_assigned_from_pub_year(self):
        # Seed pub_year is 2022 in the fixture.
        by_id = {n["openalex_id"]: n for n in self.run["nodes"]}
        self.assertEqual(by_id["W2000000001"]["phase"], 2020)

    def test_idempotent(self):
        first = {n["openalex_id"]: dict(n) for n in self.run["nodes"]}
        prune(self.run)
        for n in self.run["nodes"]:
            self.assertEqual(n["in_degree"], first[n["openalex_id"]]["in_degree"])
            self.assertEqual(n["phase"], first[n["openalex_id"]]["phase"])
        self.assertEqual(self.run["schema_version"], 2)
        self.assertEqual(self.run["meta"]["pruned_count"], 0)


class TestPhase(unittest.TestCase):
    def test_decade_floor(self):
        self.assertEqual(_phase(1976), 1970)
        self.assertEqual(_phase(2003), 2000)
        self.assertEqual(_phase(1950), 1950)

    def test_undated_is_none(self):
        self.assertIsNone(_phase(None))
        self.assertIsNone(_phase(0))


class TestKeptSubgraphInDegree(unittest.TestCase):
    def test_excludes_edges_touching_pruned_nodes(self):
        # Forward-proofs the seam: once a future cut sets kept=False, edges to or
        # from a pruned node must not count toward any kept node's in_degree.
        nodes = [
            {"openalex_id": "A", "kept": True},
            {"openalex_id": "B", "kept": True},
            {"openalex_id": "C", "kept": False},
        ]
        edges = [["A", "B"], ["C", "B"], ["A", "C"]]
        counts = _kept_subgraph_in_degree(nodes, edges)
        self.assertEqual(counts["B"], 1)  # only A->B counts; C->B dropped
        self.assertEqual(counts["C"], 0)  # pruned node gets nothing
        self.assertEqual(counts["A"], 0)


class TestUpdateRun(unittest.TestCase):
    def setUp(self):
        self.run = build_run(SEED_DOI, make_fetch()[0], depth=2)

    def test_overwrite_permitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store.update_run(self.run, runs_dir=Path(tmp))
            prune(self.run)
            path = store.update_run(self.run, runs_dir=Path(tmp))
            loaded = store.read_run(path)
            self.assertEqual(loaded["schema_version"], 2)
            self.assertEqual(loaded, self.run)

    def test_no_temp_files_left_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            store.update_run(self.run, runs_dir=Path(tmp))
            leftovers = list(Path(tmp).glob("*.tmp"))
            self.assertEqual(leftovers, [])

    def test_missing_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                store.update_run({"run_id": "x"}, runs_dir=Path(tmp))


@unittest.skipUnless(REAL_RUNS, "no real run files in runs/ (not committed)")
class TestPruneRealRuns(unittest.TestCase):
    # Foundational old keepers that a similarity or citation cut would endanger.
    # Under v1 (no cut) they survive trivially; assert it so a future cut that
    # drops them is caught.
    KEEPERS = ["lesions of the ileum", "crohn's disease activity index"]

    def test_real_runs_keep_all_and_upgrade(self):
        for path in REAL_RUNS:
            run = store.read_run(path)
            n = len(run["nodes"])
            prune(run)
            self.assertTrue(all(node["kept"] for node in run["nodes"]), path)
            self.assertEqual(run["meta"]["kept_count"], n, path)
            self.assertEqual(run["meta"]["pruned_count"], 0, path)
            self.assertEqual(run["schema_version"], 2, path)

    def test_foundational_keepers_survive(self):
        kept_titles = []
        for path in REAL_RUNS:
            run = store.read_run(path)
            prune(run)
            kept_titles += [
                n["title"].lower() for n in run["nodes"] if n["kept"] and n["title"]
            ]
        for frag in self.KEEPERS:
            self.assertTrue(
                any(frag in t for t in kept_titles),
                f"foundational keeper not found among kept nodes: {frag}",
            )

    def test_shared_ancestors_have_in_degree_above_one(self):
        # The reframe-#1 cut would chart in_degree>=2 nodes; confirm the field
        # actually distinguishes some shared ancestors on the real graphs.
        found = False
        for path in REAL_RUNS:
            run = store.read_run(path)
            prune(run)
            if any(n["in_degree"] >= 2 for n in run["nodes"]):
                found = True
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
