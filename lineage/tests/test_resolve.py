import unittest

from lineage.resolve import resolve, to_node
from lineage.tests.fixture import SEED_DOI, make_fetch


class TestResolve(unittest.TestCase):
    def test_resolve_normalizes_seed(self):
        fetch, _ = make_fetch()
        node = resolve(SEED_DOI, fetch)

        self.assertEqual(node["openalex_id"], "W2000000001")
        self.assertEqual(node["doi"], "10.1000/seed")
        self.assertEqual(node["pub_year"], 2022)
        self.assertEqual(node["citation_count"], 140)
        self.assertEqual(node["authors"], ["Alice Adams", "Bob Brown"])
        self.assertEqual(node["depth"], 0)

    def test_reserved_fields_present(self):
        fetch, _ = make_fetch()
        node = resolve(SEED_DOI, fetch)
        self.assertEqual(node["in_degree"], 0)
        self.assertIsNone(node["phase"])

    def test_ref_complete_threshold(self):
        complete = to_node({"id": "W1", "referenced_works": ["a", "b", "c", "d", "e"]}, 1)
        sparse = to_node({"id": "W2", "referenced_works": ["a", "b"]}, 1)
        self.assertTrue(complete["ref_complete"])
        self.assertFalse(sparse["ref_complete"])

    def test_missing_doi_normalizes_to_none(self):
        node = to_node({"id": "W3", "referenced_works": [], "doi": None}, 1)
        self.assertIsNone(node["doi"])


if __name__ == "__main__":
    unittest.main()
