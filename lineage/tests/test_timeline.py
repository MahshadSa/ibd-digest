import logging
import tempfile
import unittest
from datetime import date
from pathlib import Path

from lineage import timeline


def _run() -> dict:
    nodes = [
        {"openalex_id": "S0", "doi": "10.1/seed", "title": "Seed paper",
         "authors": ["Ada Lovelace", "Charles Babbage"], "pub_year": 2022,
         "citation_count": 5, "depth": 0, "in_degree": 0, "phase": 2020, "kept": True},
        {"openalex_id": "A1", "doi": "10.2/a", "title": "Old foundational work",
         "authors": ["Grace Hopper"], "pub_year": 1965, "citation_count": 99,
         "depth": 2, "in_degree": 3, "phase": 1960, "kept": True},
        {"openalex_id": "A2", "doi": None, "title": "Mid era", "authors": [],
         "pub_year": 1995, "citation_count": 0, "depth": 1, "in_degree": 1,
         "phase": 1990, "kept": True},
        {"openalex_id": "N1", "doi": "10.9/n", "title": "Not selected", "authors": ["X"],
         "pub_year": 1980, "citation_count": 0, "depth": 2, "in_degree": 2,
         "phase": 1980, "kept": True},
    ]
    return {
        "schema_version": 2, "run_id": "synthetic-20260618", "created_at": "x",
        "seed": {"doi": "10.1/seed", "openalex_id": "S0", "title": "Seed paper"},
        "depth": 2, "top_k": 15, "nodes": nodes, "edges": [],
        "meta": {"node_count": 4, "kept_count": 4, "pruned_count": 0},
    }


def _selection() -> dict:
    return {
        "narrative": "From bench to imaging.",
        "coverage_gaps": ["no 1970s methods paper"],
        "selections": [
            {"openalex_id": "S0", "rationale": "the seed review."},
            {"openalex_id": "A1", "rationale": "the foundational method."},
            {"openalex_id": "A2", "rationale": "the bridging study."},
        ],
    }


class TestSelectedNodes(unittest.TestCase):
    def test_drops_unknown_id_with_warning(self):
        sel = _selection()
        sel["selections"].append({"openalex_id": "GONE", "rationale": "stale"})
        with self.assertLogs(timeline.logger, level=logging.WARNING) as cm:
            nodes, _ = timeline.selected_nodes(_run(), sel)
        self.assertEqual({n["openalex_id"] for n in nodes}, {"S0", "A1", "A2"})
        self.assertIn("GONE", "".join(cm.output))


class TestRenderNote(unittest.TestCase):
    def setUp(self):
        self.text = timeline.render_note(_run(), _selection())

    def test_no_mermaid(self):
        self.assertNotIn("```mermaid", self.text)

    def test_only_selected_rendered(self):
        self.assertIn("Old foundational work", self.text)
        self.assertNotIn("Not selected", self.text)

    def test_grouping_reuses_phase_order(self):
        order = [self.text.index(h) for h in ["### 1960s", "### 1990s", "### 2020s"]]
        self.assertEqual(order, sorted(order))

    def test_facts_from_run_role_from_sidecar(self):
        self.assertIn("[10.2/a](https://doi.org/10.2/a)", self.text)
        self.assertIn("the foundational method.", self.text)

    def test_seed_marked(self):
        self.assertIn("**SEED: Seed paper**", self.text)

    def test_narrative_and_gaps_rendered(self):
        self.assertIn("From bench to imaging.", self.text)
        self.assertIn("## Coverage gaps", self.text)
        self.assertIn("- no 1970s methods paper", self.text)

    def test_exit_lever_footer_counts_shared_ancestors(self):
        # A1 (in_degree 3) and N1 (in_degree 2) are >= 2 across the kept crawl set.
        self.assertIn("2 kept nodes have in-degree >= 2", self.text)

    def test_empty_after_drop_raises(self):
        sel = {"selections": [{"openalex_id": "GONE", "rationale": "x"}]}
        with self.assertRaises(ValueError):
            with self.assertLogs(timeline.logger, level=logging.WARNING):
                timeline.render_note(_run(), sel)


class TestWriteNote(unittest.TestCase):
    def test_path_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = timeline.write_note(_run(), _selection(), vault_root=Path(tmp))
            expected = (Path(tmp) / "Inbox" / "Lineages"
                        / f"lovelace-2022-{date.today():%Y-%m-%d}-selected.md")
            self.assertEqual(path, expected)
            self.assertTrue(path.exists())
            with self.assertRaises(FileExistsError):
                timeline.write_note(_run(), _selection(), vault_root=Path(tmp))
            timeline.write_note(_run(), _selection(), vault_root=Path(tmp), force=True)


if __name__ == "__main__":
    unittest.main()
