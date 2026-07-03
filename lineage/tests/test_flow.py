"""Interactive single-seed flow wrapper: scratch cleanup, reuse, retry, end-to-end."""
import json
import tempfile
import unittest
from pathlib import Path

from lineage import store
from lineage.flow import clear_scratch, crawl_or_reuse, ingest_reply, run_flow
from lineage.tests.fixture import SEED_DOI, make_fetch


def _citer(wid: str, year: int) -> dict:
    return {
        "id": f"https://openalex.org/{wid}",
        "display_name": f"Citer {wid}",
        "publication_year": year,
        "cited_by_count": 3,
        "doi": f"https://doi.org/10.9/{wid.lower()}",
        "authorships": [{"author": {"display_name": "A. Citer"}}],
        "referenced_works": [],
        "abstract_inverted_index": None,
    }


def _fetch_citing(_wid: str) -> list[dict]:
    return [_citer("W9000000001", 2026)]


def _good_reply(*ids: str) -> str:
    return json.dumps(
        {
            "narrative": "An arc.",
            "coverage_gaps": ["some era"],
            "selections": [{"openalex_id": i, "rationale": "role"} for i in ids],
        }
    )


class TestClearScratch(unittest.TestCase):
    def test_deletes_on_confirm(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            a = Path(tmp) / "payload.txt"
            b = Path(tmp) / "reply.json"
            a.write_text("x", encoding="utf-8")
            b.write_text("y", encoding="utf-8")
            deleted = clear_scratch([a, b], confirm=lambda _m: True)
            self.assertEqual(set(deleted), {a, b})
            self.assertFalse(a.exists())
            self.assertFalse(b.exists())

    def test_keeps_when_declined(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            a = Path(tmp) / "payload.txt"
            a.write_text("x", encoding="utf-8")
            self.assertEqual(clear_scratch([a], confirm=lambda _m: False), [])
            self.assertTrue(a.exists())

    def test_no_prompt_when_nothing_stale(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            missing = Path(tmp) / "payload.txt"
            called = []
            clear_scratch([missing], confirm=lambda m: called.append(m) or True)
            self.assertEqual(called, [])


class TestCrawlOrReuse(unittest.TestCase):
    def test_fresh_crawl_writes_run(self):
        fetch, calls = make_fetch()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            run, reused = crawl_or_reuse(SEED_DOI, fetch, Path(tmp))
            self.assertFalse(reused)
            self.assertTrue((Path(tmp) / f"{run['run_id']}.json").exists())
            self.assertGreater(sum(calls.values()), 0)

    def test_second_call_reuses_without_fetching(self):
        fetch, calls = make_fetch()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            crawl_or_reuse(SEED_DOI, fetch, Path(tmp))
            first = sum(calls.values())
            run, reused = crawl_or_reuse(SEED_DOI, fetch, Path(tmp))
            self.assertTrue(reused)
            self.assertEqual(sum(calls.values()), first)


class TestIngestReply(unittest.TestCase):
    def test_retries_until_reply_validates(self):
        fetch, _ = make_fetch()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            runs_dir = Path(tmp)
            run, _ = crawl_or_reuse(SEED_DOI, fetch, runs_dir)
            reply = runs_dir / "reply.json"
            state = {"n": 0}

            def prompt():
                state["n"] += 1
                if state["n"] == 1:
                    reply.write_text("this is prose, not json", encoding="utf-8")
                else:
                    reply.write_text(_good_reply("W3000000001"), encoding="utf-8")

            block = ingest_reply(run, reply, runs_dir, prompt)
            self.assertEqual(state["n"], 2)
            self.assertEqual(block["selections"][0]["openalex_id"], "W3000000001")


class TestRunFlowEndToEnd(unittest.TestCase):
    def test_produces_dossier_and_sidecars(self):
        fetch, _ = make_fetch()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            runs_dir = root / "runs"
            reply = root / "reply.json"
            payload = root / "payload.txt"

            def prompt():
                reply.write_text(_good_reply("W3000000001", "W4000000006"), encoding="utf-8")

            note = run_flow(
                SEED_DOI,
                fetch=fetch,
                fetch_citing=_fetch_citing,
                prompt=prompt,
                confirm=lambda _m: False,
                runs_dir=runs_dir,
                vault_root=root,
                payload_path=payload,
                reply_path=reply,
                clipboard=lambda _p: None,
            )
            self.assertTrue(note.exists())
            self.assertTrue(str(note).endswith("-dossier.md"))
            self.assertTrue(payload.exists())
            run_id = note.name.replace("-dossier.md", "")
            self.assertTrue(store.forward_path(run_id, runs_dir).exists())
            self.assertTrue(store.selection_path(run_id, runs_dir).exists())
            body = note.read_text(encoding="utf-8")
            self.assertIn("Depth-1 paper A", body)


if __name__ == "__main__":
    unittest.main()
