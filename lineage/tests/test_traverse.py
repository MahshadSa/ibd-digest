import unittest

from lineage.resolve import FetchFailed, resolve
from lineage.tests.fixture import SEED_DOI, load_fixture, make_fetch
from lineage.traverse import build_run, traverse


class TestTraverse(unittest.TestCase):
    def setUp(self):
        self.fetch, self.calls = make_fetch()
        self.seed = resolve(SEED_DOI, self.fetch)
        self.graph = traverse(self.seed, self.fetch, depth=2)
        self.nodes = {n["openalex_id"]: n for n in self.graph["nodes"]}

    def test_node_count(self):
        # seed + 5 depth-1 + 3 unique depth-2 (W6, W7, W8)
        self.assertEqual(len(self.nodes), 9)

    def test_depth_assignment(self):
        self.assertEqual(self.nodes["W2000000001"]["depth"], 0)
        self.assertEqual(self.nodes["W3000000001"]["depth"], 1)
        self.assertEqual(self.nodes["W4000000006"]["depth"], 2)

    def test_dedup_keeps_min_depth_and_single_node(self):
        # W4000000006 is referenced by both W3000000001 and W3000000004
        self.assertEqual(self.nodes["W4000000006"]["depth"], 2)
        ids = [n["openalex_id"] for n in self.graph["nodes"]]
        self.assertEqual(ids.count("W4000000006"), 1)
        self.assertEqual(ids.count("W4000000007"), 1)

    def test_each_work_fetched_once(self):
        self.assertTrue(all(c == 1 for c in self.calls.values()), self.calls)

    def test_edges(self):
        expected = {
            ("W2000000001", "W3000000001"),
            ("W2000000001", "W3000000002"),
            ("W2000000001", "W3000000003"),
            ("W2000000001", "W3000000004"),
            ("W2000000001", "W3000000005"),
            ("W3000000001", "W4000000006"),
            ("W3000000001", "W4000000007"),
            ("W3000000003", "W4000000007"),
            ("W3000000003", "W4000000008"),
            ("W3000000004", "W4000000006"),
        }
        actual = [tuple(e) for e in self.graph["edges"]]
        self.assertEqual(len(actual), 10)
        self.assertEqual(set(actual), expected)

    def test_depth2_not_expanded(self):
        # W5000000200 is referenced only by a depth-2 node; it must not be fetched
        self.assertNotIn("W5000000200", self.calls)

    def test_sparse_flag(self):
        self.assertTrue(self.nodes["W2000000001"]["ref_complete"])
        self.assertTrue(self.nodes["W4000000006"]["ref_complete"])
        self.assertFalse(self.nodes["W3000000002"]["ref_complete"])
        self.assertFalse(self.nodes["W4000000008"]["ref_complete"])

    def test_referenced_works_stripped_in_run(self):
        run = build_run(SEED_DOI, make_fetch()[0], depth=2)
        self.assertTrue(all("referenced_works" not in n for n in run["nodes"]))

    def test_run_dict_shape(self):
        run = build_run(SEED_DOI, make_fetch()[0], depth=2)
        self.assertEqual(run["schema_version"], 1)
        self.assertTrue(run["run_id"].startswith("10-1000-seed-"))
        self.assertEqual(run["seed"]["openalex_id"], "W2000000001")
        self.assertEqual(run["meta"]["node_count"], 9)
        self.assertEqual(run["meta"]["edge_count"], 10)
        self.assertEqual(len(run["meta"]["sparse_ids"]), 7)


class TestUnresolvedReference(unittest.TestCase):
    BAD_ID = "W9999999404"

    def setUp(self):
        # Point a depth-1 node at a reference absent from the fixture; the fetch
        # raises WorkNotFound for it, modeling a real 404 during the walk.
        data = load_fixture()
        data["W3000000002"]["referenced_works"] = [f"https://openalex.org/{self.BAD_ID}"]
        self.fetch, self.calls = make_fetch(data)
        self.run = build_run(SEED_DOI, self.fetch, depth=2)
        self.ids = {n["openalex_id"] for n in self.run["nodes"]}

    def test_walk_completes_with_all_good_nodes(self):
        # Same 9 good nodes as the clean walk; the bad id is not among them.
        self.assertEqual(len(self.run["nodes"]), 9)
        self.assertNotIn(self.BAD_ID, self.ids)

    def test_no_edge_references_bad_id(self):
        self.assertFalse(any(self.BAD_ID in edge for edge in self.run["edges"]))

    def test_meta_records_unresolved(self):
        self.assertEqual(self.run["meta"]["unresolved_ids"], [self.BAD_ID])
        self.assertEqual(self.run["meta"]["unresolved_count"], 1)

    def test_bad_id_fetched_once(self):
        self.assertEqual(self.calls[self.BAD_ID], 1)


class TestTopKCap(unittest.TestCase):
    def setUp(self):
        # Seed with five references; each child has none. top_k=2 must follow
        # only the first two and never fetch the rest.
        self.data = {
            "10.1000/cap": {
                "id": "https://openalex.org/W1",
                "doi": "https://doi.org/10.1000/cap",
                "referenced_works": [f"https://openalex.org/W{i}" for i in range(2, 7)],
            },
        }
        for i in range(2, 7):
            self.data[f"W{i}"] = {"id": f"https://openalex.org/W{i}", "referenced_works": []}
        self.fetch, self.calls = make_fetch(self.data)

    def test_only_first_k_followed(self):
        run = build_run("10.1000/cap", self.fetch, depth=1, top_k=2)
        ids = {n["openalex_id"] for n in run["nodes"]}
        self.assertEqual(ids, {"W1", "W2", "W3"})
        self.assertNotIn("W4", self.calls)
        self.assertNotIn("W6", self.calls)
        self.assertEqual(run["top_k"], 2)


class TestTransientFailure(unittest.TestCase):
    BAD_ID = "W8888888888"

    def setUp(self):
        data = load_fixture()
        data["W3000000002"]["referenced_works"] = [f"https://openalex.org/{self.BAD_ID}"]
        base, self.calls = make_fetch(data)

        def fetch(ref):
            if ref == self.BAD_ID:
                self.calls[ref] += 1
                raise FetchFailed(ref)
            return base(ref)

        self.run = build_run(SEED_DOI, fetch, depth=2)
        self.ids = {n["openalex_id"] for n in self.run["nodes"]}

    def test_walk_completes_with_all_good_nodes(self):
        self.assertEqual(len(self.run["nodes"]), 9)
        self.assertNotIn(self.BAD_ID, self.ids)

    def test_no_edge_references_bad_id(self):
        self.assertFalse(any(self.BAD_ID in edge for edge in self.run["edges"]))

    def test_meta_records_failed_not_unresolved(self):
        self.assertEqual(self.run["meta"]["failed_ids"], [self.BAD_ID])
        self.assertEqual(self.run["meta"]["failed_count"], 1)
        self.assertEqual(self.run["meta"]["unresolved_count"], 0)


if __name__ == "__main__":
    unittest.main()
