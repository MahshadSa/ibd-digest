import tempfile
import unittest
from datetime import date
from pathlib import Path

from lineage import render, store
from lineage.prune import prune
from lineage.tests.fixture import SEED_DOI, make_fetch
from lineage.traverse import build_run


def _synthetic_run() -> dict:
    """A small pruned v2 run with one undated node, which the real fixtures and
    runs lack. Seed in the 2020s; an undated (no pub_year) node must trail."""
    nodes = [
        {"openalex_id": "S0", "doi": "10.1/seed", "title": "Seed paper",
         "authors": ["Ada Lovelace", "Charles Babbage"], "pub_year": 2022,
         "citation_count": 5, "depth": 0, "in_degree": 0, "phase": 2020, "kept": True},
        {"openalex_id": "A1", "doi": "10.2/a", "title": "Old foundational work",
         "authors": ["Grace Hopper"], "pub_year": 1965, "citation_count": 99,
         "depth": 1, "in_degree": 2, "phase": 1960, "kept": True},
        {"openalex_id": "A2", "doi": None, "title": "Mid era",
         "authors": [], "pub_year": 1995, "citation_count": 0,
         "depth": 1, "in_degree": 1, "phase": 1990, "kept": True},
        {"openalex_id": "U1", "doi": "10.4/u", "title": "Undated work",
         "authors": ["No Year"], "pub_year": None, "citation_count": 1,
         "depth": 2, "in_degree": 1, "phase": None, "kept": True},
    ]
    edges = [["S0", "A1"], ["S0", "A2"], ["A2", "A1"], ["A1", "U1"]]
    return {
        "schema_version": 2, "run_id": "synthetic-20260618", "created_at": "x",
        "seed": {"doi": "10.1/seed", "openalex_id": "S0", "title": "Seed paper"},
        "depth": 2, "top_k": 15, "nodes": nodes, "edges": edges,
        "meta": {"node_count": 4, "edge_count": 4, "kept_count": 4, "pruned_count": 0},
    }


class TestGroupByPhase(unittest.TestCase):
    def setUp(self):
        self.groups = render.group_by_phase(_synthetic_run())

    def test_decades_oldest_to_newest_undated_last(self):
        self.assertEqual([g["label"] for g in self.groups],
                         ["1960s", "1990s", "2020s", "Undated"])

    def test_undated_trails(self):
        self.assertIsNone(self.groups[-1]["phase"])

    def test_sorted_within_group_by_year_then_title(self):
        # All four groups hold one node here; assert the ordering key directly.
        run = _synthetic_run()
        run["nodes"].append(
            {"openalex_id": "A3", "doi": None, "title": "Abel", "authors": ["Z"],
             "pub_year": 1995, "citation_count": 0, "depth": 1, "in_degree": 1,
             "phase": 1990, "kept": True})
        g90 = next(g for g in render.group_by_phase(run) if g["phase"] == 1990)
        self.assertEqual([n["title"] for n in g90["nodes"]], ["Abel", "Mid era"])

    def test_only_kept_nodes(self):
        run = _synthetic_run()
        run["nodes"][1]["kept"] = False
        ids = {n["openalex_id"] for g in render.group_by_phase(run) for n in g["nodes"]}
        self.assertNotIn("A1", ids)


class TestBuildLabel(unittest.TestCase):
    def test_surname_and_year(self):
        self.assertEqual(
            render.build_label({"openalex_id": "X", "authors": ["P. Rutgeerts"], "pub_year": 1990}),
            "Rutgeerts 1990")

    def test_no_authors_falls_back_to_id(self):
        self.assertEqual(
            render.build_label({"openalex_id": "W42", "authors": [], "pub_year": 2000}),
            "W42 2000")

    def test_missing_year(self):
        self.assertTrue(
            render.build_label({"openalex_id": "W1", "authors": ["A B"], "pub_year": None})
            .endswith("n.d."))


class TestMermaid(unittest.TestCase):
    def setUp(self):
        self.run = _synthetic_run()
        self.mmd = render.mermaid(self.run)

    def test_charts_every_kept_node(self):
        for n in self.run["nodes"]:
            self.assertIn(f'{n["openalex_id"]}[', self.mmd)

    def test_subgraphs_in_phase_order(self):
        order = [self.mmd.index(lbl) for lbl in ['"1960s"', '"1990s"', '"2020s"', '"Undated"']]
        self.assertEqual(order, sorted(order))

    def test_seed_styled(self):
        self.assertIn("classDef seed", self.mmd)
        self.assertIn("class S0 seed;", self.mmd)
        self.assertIn("SEED: Lovelace 2022", self.mmd)

    def test_renders_all_edges_between_kept_nodes(self):
        for citing, referenced in self.run["edges"]:
            self.assertIn(f"{citing} --> {referenced}", self.mmd)


class TestTrajectory(unittest.TestCase):
    def setUp(self):
        self.traj = render.trajectory(_synthetic_run())

    def test_headings_in_order(self):
        order = [self.traj.index(h) for h in ["### 1960s", "### 1990s", "### 2020s", "### Undated"]]
        self.assertEqual(order, sorted(order))

    def test_seed_marked(self):
        self.assertIn("**SEED: Seed paper**", self.traj)

    def test_et_al_for_multiple_authors(self):
        self.assertIn("Ada Lovelace et al.", self.traj)

    def test_single_author_no_et_al(self):
        self.assertIn("Grace Hopper, 1965", self.traj)
        self.assertNotIn("Grace Hopper et al.", self.traj)

    def test_doi_link_present_and_absent(self):
        self.assertIn("[10.2/a](https://doi.org/10.2/a)", self.traj)
        # A2 has no doi: its bullet ends at the period, no doi.org link.
        line = next(l for l in self.traj.splitlines() if "Mid era" in l)
        self.assertNotIn("doi.org", line)


class TestWriteNote(unittest.TestCase):
    def test_path_and_overwrite_guard(self):
        run = _synthetic_run()
        with tempfile.TemporaryDirectory() as tmp:
            path = render.write_note(run, vault_root=Path(tmp))
            expected = Path(tmp) / "Inbox" / "Lineages" / f"lovelace-2022-{date.today():%Y-%m-%d}.md"
            self.assertEqual(path, expected)
            self.assertTrue(path.exists())
            with self.assertRaises(FileExistsError):
                render.write_note(run, vault_root=Path(tmp))
            render.write_note(run, vault_root=Path(tmp), force=True)

    def test_note_contains_mermaid_and_trajectory(self):
        text = render.render_note(_synthetic_run())
        self.assertIn("```mermaid", text)
        self.assertIn("## Trajectory", text)
        self.assertIn("# Lineage: Seed paper", text)


class TestRendersFromFixtureRun(unittest.TestCase):
    def test_pruned_fixture_run_renders(self):
        run = build_run(SEED_DOI, make_fetch()[0], depth=2)
        prune(run)
        text = render.render_note(run)
        kept = sum(1 for n in run["nodes"] if n["kept"])
        charted = text.count('["')  # node + subgraph declarations
        self.assertGreaterEqual(charted, kept)


if __name__ == "__main__":
    unittest.main()
