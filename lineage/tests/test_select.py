import json
import logging
import tempfile
import unittest
from pathlib import Path

from lineage import select, store


def _run() -> dict:
    nodes = [
        {"openalex_id": "S0", "doi": "10.1/seed", "title": "Seed paper",
         "authors": ["Ada Lovelace"], "pub_year": 2022, "abstract": "seed abstract",
         "citation_count": 5, "depth": 0, "in_degree": 0, "phase": 2020, "kept": True},
        {"openalex_id": "A1", "doi": "10.2/a", "title": "Old foundational work",
         "authors": ["Grace Hopper"], "pub_year": 1965, "abstract": "x " * 600,
         "citation_count": 99, "depth": 2, "in_degree": 2, "phase": 1960, "kept": True},
        {"openalex_id": "A2", "doi": None, "title": "Mid era", "authors": [],
         "pub_year": 1995, "abstract": None, "citation_count": 0,
         "depth": 1, "in_degree": 1, "phase": 1990, "kept": True},
        {"openalex_id": "U1", "doi": "10.4/u", "title": "Undated", "authors": ["No Year"],
         "pub_year": None, "abstract": "later", "citation_count": 1,
         "depth": 2, "in_degree": 1, "phase": None, "kept": True},
    ]
    return {
        "schema_version": 1, "run_id": "synthetic-20260618", "created_at": "x",
        "seed": {"doi": "10.1/seed", "openalex_id": "S0", "title": "Seed paper"},
        "depth": 2, "top_k": 15, "nodes": nodes, "edges": [],
        "meta": {"node_count": 4},
    }


class TestBuildPayload(unittest.TestCase):
    def setUp(self):
        self.payload = select.build_payload(_run())

    def test_lists_every_kept_node(self):
        for oid in ("S0", "A1", "A2", "U1"):
            self.assertIn(oid, self.payload)

    def test_response_format_spec_present(self):
        self.assertIn("```json", self.payload)
        self.assertIn('"selections"', self.payload)
        self.assertIn('"openalex_id"', self.payload)

    def test_abstract_truncated(self):
        line = next(l for l in self.payload.splitlines() if l.startswith("Abstract:") and "x x" in l)
        self.assertLessEqual(len(line), len("Abstract: ") + select.ABSTRACT_CHARS + 3)
        self.assertTrue(line.rstrip().endswith("..."))

    def test_groundwork_first_oldest_then_undated_last(self):
        order = [self.payload.index(f"--- {oid}") for oid in ("A1", "A2", "S0", "U1")]
        self.assertEqual(order, sorted(order))

    def test_depth_is_tiebreaker_only(self):
        # Two same-year nodes: deeper one first.
        run = _run()
        run["nodes"].append(
            {"openalex_id": "A1b", "doi": None, "title": "Shallow 1965", "authors": ["X"],
             "pub_year": 1965, "abstract": None, "citation_count": 0,
             "depth": 1, "in_degree": 1, "phase": 1960, "kept": True})
        payload = select.build_payload(run)
        self.assertLess(payload.index("--- A1 "), payload.index("--- A1b "))


class TestParseSelection(unittest.TestCase):
    def test_fenced_json_object(self):
        text = 'blah\n```json\n{"selections": [{"openalex_id": "A1"}]}\n```\ntrailing'
        self.assertEqual(select.parse_selection(text)["selections"][0]["openalex_id"], "A1")

    def test_bare_json_object(self):
        self.assertIn("selections", select.parse_selection('{"selections": []}'))

    def test_prose_raises(self):
        with self.assertRaises(ValueError):
            select.parse_selection("I think papers A1 and A2 are foundational.")

    def test_non_object_json_raises(self):
        with self.assertRaises(ValueError):
            select.parse_selection("[1, 2, 3]")


class TestValidateSelection(unittest.TestCase):
    def test_keeps_only_ids_in_run(self):
        parsed = {"selections": [
            {"openalex_id": "A1", "rationale": "foundational"},
            {"openalex_id": "GHOST", "rationale": "not in run"},
        ]}
        with self.assertLogs(select.logger, level=logging.WARNING) as cm:
            block = select.validate_selection(parsed, _run())
        self.assertEqual([s["openalex_id"] for s in block["selections"]], ["A1"])
        self.assertIn("GHOST", "".join(cm.output))

    def test_dedupes(self):
        parsed = {"selections": [
            {"openalex_id": "A1", "rationale": "first"},
            {"openalex_id": "A1", "rationale": "dupe"},
        ]}
        with self.assertLogs(select.logger, level=logging.WARNING):
            block = select.validate_selection(parsed, _run())
        self.assertEqual(len(block["selections"]), 1)
        self.assertEqual(block["selections"][0]["rationale"], "first")

    def test_no_selections_list_raises(self):
        with self.assertRaises(ValueError):
            select.validate_selection({"narrative": "hi"}, _run())

    def test_none_survive_raises(self):
        with self.assertRaises(ValueError):
            with self.assertLogs(select.logger, level=logging.WARNING):
                select.validate_selection({"selections": [{"openalex_id": "GHOST"}]}, _run())

    def test_narrative_and_gaps_passthrough(self):
        parsed = {"narrative": "  an arc  ", "coverage_gaps": ["1970s methods", "", "  "],
                  "selections": [{"openalex_id": "A1", "rationale": "x"}]}
        block = select.validate_selection(parsed, _run())
        self.assertEqual(block["narrative"], "an arc")
        self.assertEqual(block["coverage_gaps"], ["1970s methods"])


class TestIngest(unittest.TestCase):
    def test_writes_sidecar_only_no_run_mutation(self):
        run = _run()
        text = '```json\n{"narrative": "arc", "selections": [{"openalex_id": "A1", "rationale": "r"}]}\n```'
        with tempfile.TemporaryDirectory() as tmp:
            path = select.ingest(run, text, Path(tmp))
            self.assertEqual(path, store.selection_path(run["run_id"], Path(tmp)))
            block = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(block["run_id"], "synthetic-20260618")
            self.assertEqual(block["selections"][0]["openalex_id"], "A1")
            # No run file was written next to the sidecar.
            self.assertFalse((Path(tmp) / f"{run['run_id']}.json").exists())


_REAL = Path("runs/10-3390-diagnostics15192457-20260617.json")


@unittest.skipUnless(_REAL.exists(), "real -0617 run file not present")
class TestRealRunPayload(unittest.TestCase):
    def test_payload_lists_every_kept_node(self):
        run = store.read_run(_REAL)
        kept = sum(1 for n in run["nodes"] if n.get("kept", True))
        payload = select.build_payload(run)
        self.assertEqual(payload.count("--- W"), kept)


if __name__ == "__main__":
    unittest.main()
