"""Topic dossier: narrative + main studies + consensus chart + frontier + gaps."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from lineage.dossier import render_dossier, write_note
from lineage.forward import build_forward
from lineage.merge import merge_runs


def _node(oid: str, year: int, depth: int, title: str = "") -> dict:
    return {
        "openalex_id": oid,
        "doi": f"10.1/{oid.lower()}",
        "title": title or f"Paper {oid}",
        "abstract": None,
        "pub_year": year,
        "authors": ["A. Author", "B. Author"],
        "citation_count": 3,
        "ref_complete": True,
        "depth": depth,
        "in_degree": 0,
        "phase": None,
    }


def _work(wid: str, year: int, title: str) -> dict:
    return {
        "id": f"https://openalex.org/{wid}",
        "display_name": title,
        "publication_year": year,
        "cited_by_count": 7,
        "doi": f"https://doi.org/10.9/{wid.lower()}",
        "authorships": [{"author": {"display_name": "C. Citer"}}],
        "referenced_works": [],
        "abstract_inverted_index": None,
    }


def _make_runs():
    run_a = {
        "schema_version": 1,
        "run_id": "seed-a-20260701",
        "created_at": "2026-07-01T00:00:00",
        "seed": {"doi": "10.1/wa", "openalex_id": "WA", "title": "Seed A"},
        "depth": 2,
        "top_k": 15,
        "nodes": [_node("WA", 2020, 0, "Seed A"), _node("W1", 2000, 1),
                  _node("W2", 1990, 2)],
        "edges": [["WA", "W1"], ["W1", "W2"]],
        "meta": {"unresolved_count": 1, "failed_count": 0},
    }
    run_b = {
        "schema_version": 1,
        "run_id": "seed-b-20260701",
        "created_at": "2026-07-01T00:00:00",
        "seed": {"doi": "10.1/wb", "openalex_id": "WB", "title": "Seed B"},
        "depth": 2,
        "top_k": 15,
        "nodes": [_node("WB", 2021, 0, "Seed B"), _node("W2", 1990, 1),
                  _node("W3", 1980, 2)],
        "edges": [["WB", "W2"], ["W2", "W3"]],
        "meta": {"unresolved_count": 2, "failed_count": 0},
    }
    return run_a, run_b


SELECTION = {
    "narrative": "The arc goes from early surgery to modern imaging.",
    "coverage_gaps": ["1970s cross-sectional imaging"],
    "selections": [
        {"openalex_id": "W2", "rationale": "Shared groundwork."},
        {"openalex_id": "W3", "rationale": "Early basis."},
    ],
}

CITING = {
    "WA": [_work("W9", 2026, "Frontier citer")],
    "W2": [_work("W9", 2026, "Frontier citer"), _work("W1", 2000, "Paper W1")],
}


class TestRenderDossier(unittest.TestCase):
    def setUp(self):
        run_a, run_b = _make_runs()
        self.merged = merge_runs([run_a, run_b], "IBD imaging")
        self.forward = build_forward(self.merged, ["WA", "W2"], lambda w: CITING[w])
        self.text = render_dossier(self.merged, SELECTION, self.forward)

    def test_narrative_and_gaps(self):
        self.assertIn("The arc goes from early surgery to modern imaging.", self.text)
        self.assertIn("## Coverage gaps", self.text)
        self.assertIn("1970s cross-sectional imaging", self.text)
        self.assertIn("3 unresolved", self.text)

    def test_main_studies_decade_grouped_with_consensus(self):
        self.assertIn("## Main studies", self.text)
        self.assertIn("### 1990s", self.text)
        self.assertIn("Shared groundwork.", self.text)
        self.assertIn("(in 2/2 seed trees)", self.text)

    def test_consensus_chart_only_shared_and_seeds(self):
        self.assertIn("```mermaid", self.text)
        chart = self.text.split("```mermaid")[1].split("```")[0]
        self.assertIn("W2[", chart)   # in_degree 2
        self.assertIn("WA[", chart)   # seed
        self.assertIn("WB[", chart)   # seed
        self.assertNotIn("W1[", chart)  # in_degree 1, not a seed
        self.assertIn("WB --> W2", chart)
        self.assertNotIn("WA --> W1", chart)

    def test_frontier_excludes_run_nodes(self):
        self.assertIn("## Frontier", self.text)
        self.assertIn("Frontier citer", self.text)
        frontier = self.text.split("## Frontier")[1]
        self.assertNotIn("Paper W1", frontier)

    def test_every_fact_from_run_not_selection(self):
        # selection carries no titles; the rendered title comes from the run node
        self.assertIn("Paper W2", self.text)

    def test_no_forward_skips_frontier(self):
        text = render_dossier(self.merged, SELECTION, None)
        self.assertNotIn("## Frontier", text)


class TestWriteNote(unittest.TestCase):
    def test_path_and_overwrite_guard(self):
        run_a, run_b = _make_runs()
        merged = merge_runs([run_a, run_b], "IBD imaging")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = write_note(merged, SELECTION, None, vault_root=Path(tmp))
            expected = (
                Path(tmp) / "Inbox" / "Lineages"
                / f"ibd-imaging-merged-{date.today():%Y%m%d}-dossier.md"
            )
            self.assertEqual(out, expected)
            with self.assertRaises(FileExistsError):
                write_note(merged, SELECTION, None, vault_root=Path(tmp))

    def test_single_seed_uses_author_year_not_doi_run_id(self):
        # A single (unmerged) run's run_id is DOI-based and unreadable
        # (store.make_run_id); the filename swaps it for author-year instead.
        run_a, _ = _make_runs()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            out = write_note(run_a, SELECTION, None, vault_root=Path(tmp))
            expected = (
                Path(tmp) / "Inbox" / "Lineages"
                / f"author-2020-{date.today():%Y-%m-%d}-dossier.md"
            )
            self.assertEqual(out, expected)


if __name__ == "__main__":
    unittest.main()
