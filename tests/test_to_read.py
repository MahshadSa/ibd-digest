import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.digest.to_read import (
    BACKFILL_CUTOFF,
    BACKFILL_HEADING,
    append_entries,
    categorize_paper,
    dois_from_history,
    extract_read_later_entries,
    load_queued_dois,
    run,
    save_queued_dois,
)

PAREN_DOI = "10.1016/s2468-1253(26)00292-x"


def _digest(title: str, doi: str, relevant: bool = False, read_later: bool = True) -> str:
    rel = "x" if relevant else " "
    rl = "x" if read_later else " "
    return f"""- [ ] **{title}**
- [{rel}] Relevant
- [{rl}] Read later
  A. Author
  Journal | 2026-06-30
  [{doi}](https://doi.org/{doi}) | Score: 0.90
"""

NEW_FORMAT_DIGEST = """# IBD Imaging Digest - 2026-07-01

> [!important] Must-read (2)

- [ ] **Queued paper**
- [ ] Relevant
- [x] Read later
  A. One, B. Two
  Radiology | 2026-06-30
  [10.1/queued](https://doi.org/10.1/queued) | Score: 0.96
  Nearest seed: Some seed

  > [!abstract]-
  > First abstract line.
  >
  > Second paragraph.

- [ ] **Relevant only paper**
- [x] Relevant
- [ ] Read later
  C. Three, D. Four
  Gut | 2026-06-29
  [10.1/relonly](https://doi.org/10.1/relonly) | Score: 0.95
"""

OLD_FORMAT_DIGEST = """# IBD Imaging Digest - 2026-05-01

> [!important] Must-read (1)

- [ ] **Old style paper**
- [x] Read later
  X. Author, Y. Author
  Gut | 2026-04-30
  [10.1/old](https://doi.org/10.1/old) | Score: 0.93

  > [!abstract]-
  > Old abstract.
"""


class TestExtractReadLater(unittest.TestCase):
    def _extract(self, text: str, d: date) -> list[dict]:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            p = Path(tmp) / f"{d.isoformat()}.md"
            p.write_text(text, encoding="utf-8")
            return extract_read_later_entries(p, d)

    def test_new_format_only_read_later_ticks(self):
        entries = self._extract(NEW_FORMAT_DIGEST, date(2026, 7, 1))
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["title"], "Queued paper")
        self.assertEqual(e["authors"], "A. One, B. Two")
        self.assertEqual(e["journal"], "Radiology")
        self.assertEqual(e["pub_date"], "2026-06-30")
        self.assertEqual(e["doi"], "10.1/queued")
        self.assertEqual(e["abstract"], "First abstract line.")
        self.assertEqual(e["category"], "IBD")

    def test_old_format_still_parses(self):
        entries = self._extract(OLD_FORMAT_DIGEST, date(2026, 5, 1))
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["title"], "Old style paper")
        self.assertEqual(e["authors"], "X. Author, Y. Author")
        self.assertEqual(e["doi"], "10.1/old")
        self.assertEqual(e["abstract"], "Old abstract.")

    def test_category_uses_the_full_abstract(self):
        digest = """- [ ] **AI-assisted imaging study**
- [x] Read later
  A. Author
  Journal | 2026-06-30
  [10.1/mixed](https://doi.org/10.1/mixed) | Score: 0.90

  > [!abstract]-
  > Artificial intelligence for endoscopy.
  >
  > The target population has Crohn's disease.
"""
        entries = self._extract(digest, date(2026, 7, 1))

        self.assertEqual(entries[0]["abstract"], "Artificial intelligence for endoscopy.")
        self.assertEqual(entries[0]["category"], "IBD")


class TestCategorizePaper(unittest.TestCase):
    def test_ibd_paper(self):
        self.assertEqual(categorize_paper("Crohn's disease monitoring", ""), "IBD")

    def test_ai_paper(self):
        self.assertEqual(
            categorize_paper("Foundation model for radiology", "Deep learning study"),
            "AI",
        )

    def test_mixed_paper_goes_to_ibd(self):
        self.assertEqual(
            categorize_paper(
                "Artificial intelligence for capsule endoscopy",
                "A deep learning system for Crohn's disease",
            ),
            "IBD",
        )

    def test_unmatched_paper_defaults_to_ibd(self):
        self.assertEqual(categorize_paper("Functional MRI in PSC", ""), "IBD")


class TestAppendEntries(unittest.TestCase):
    @staticmethod
    def _entry(doi: str, title: str, abstract: str = "") -> dict:
        return {
            "title": title,
            "authors": "A. Author",
            "journal": "Journal",
            "pub_date": "2026-06-30",
            "doi": doi,
            "abstract": abstract,
            "digest_date": date(2026, 11, 10),
        }

    def test_writes_ibd_and_ai_sections_with_mixed_paper_in_ibd(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "To Read.md"
            entries = [
                self._entry("10.1/ai", "AI system for radiology"),
                self._entry(
                    "10.1/mixed",
                    "Machine learning in ulcerative colitis",
                ),
            ]

            self.assertEqual(len(append_entries(path, entries, set())), 2)
            text = path.read_text(encoding="utf-8")

            ibd_section, separator, ai_section = text.partition("\n# AI\n")
            self.assertEqual(separator, "\n# AI\n")
            self.assertIn("10.1/mixed", ibd_section)
            self.assertNotIn("10.1/ai", ibd_section)
            self.assertIn("10.1/ai", ai_section)
            self.assertIn("### Machine learning in ulcerative colitis", ibd_section)

    def test_migrates_flat_note_and_remains_idempotent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "To Read.md"
            existing = """## Existing Crohn's paper

Added: 2026-07-01 | Source: [[Inbox/Papers/2026-07-01]]
A. Author | Journal | 2026-06-30
[10.1/existing](https://doi.org/10.1/existing)

---

## Existing AI paper

Added: 2026-07-01 | Source: [[Inbox/Papers/2026-07-01]]
A. Author | Journal | 2026-06-30
[10.1/ai](https://doi.org/10.1/ai)

Artificial intelligence study.

---
"""
            path.write_text(existing, encoding="utf-8")

            queued = {"10.1/existing", "10.1/ai"}
            self.assertEqual(append_entries(path, [], queued), [])
            migrated = path.read_text(encoding="utf-8")
            self.assertTrue(migrated.startswith("# IBD\n"))
            self.assertEqual(migrated.count("# IBD"), 1)
            self.assertEqual(migrated.count("# AI"), 1)
            self.assertIn("### Existing Crohn's paper", migrated)
            self.assertIn("> [!abstract]- Abstract\n> Artificial intelligence study.", migrated)
            self.assertNotIn("\n## Existing", migrated)

            duplicate = self._entry("10.1/existing", "Crohn's duplicate")
            self.assertEqual(append_entries(path, [duplicate], queued), [])
            self.assertEqual(path.read_text(encoding="utf-8"), migrated)

    def test_run_files_checked_papers_under_the_correct_sections(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            papers_dir = Path(tmp) / "Inbox" / "Papers"
            papers_dir.mkdir(parents=True)
            digest = """- [ ] **AI-assisted Crohn's disease assessment**
- [x] Read later
  A. Author
  Journal | 2026-06-30
  [10.1/mixed](https://doi.org/10.1/mixed) | Score: 0.90

- [ ] **Foundation model for chest radiology**
- [x] Read later
  B. Author
  Journal | 2026-06-30
  [10.1/ai](https://doi.org/10.1/ai) | Score: 0.89
"""
            (papers_dir / "2026-11-10.md").write_text(digest, encoding="utf-8")
            save_queued_dois(str(Path(tmp) / "data" / "queued_dois.txt"), set())

            run(tmp, digest_date=date(2026, 11, 10))

            text = (Path(tmp) / "Inbox" / "To Read.md").read_text(encoding="utf-8")
            ibd_section, separator, ai_section = text.partition("\n# AI\n")
            self.assertEqual(separator, "\n# AI\n")
            self.assertIn("10.1/mixed", ibd_section)
            self.assertIn("10.1/ai", ai_section)
            self.assertIn("### AI-assisted Crohn's disease assessment", ibd_section)


class TestQueuedDois(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.vault = Path(self.tmp.name)
        self.papers = self.vault / "Inbox" / "Papers"
        self.papers.mkdir(parents=True)
        self.queued_path = self.vault / "data" / "queued_dois.txt"
        self.to_read = self.vault / "Inbox" / "To Read.md"

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, stem: str, text: str) -> None:
        (self.papers / f"{stem}.md").write_text(text, encoding="utf-8")

    def test_round_trip_lowercased_sorted(self):
        save_queued_dois(str(self.queued_path), {"10.1/B", "10.1/a", " "})
        self.assertEqual(
            self.queued_path.read_text(encoding="utf-8"), "10.1/a\n10.1/b\n"
        )
        self.assertEqual(load_queued_dois(str(self.queued_path)), {"10.1/a", "10.1/b"})

    def test_missing_queued_file_raises(self):
        self._write("2026-11-10", _digest("Crohn paper", "10.1/x"))
        with self.assertRaises(FileNotFoundError):
            run(str(self.vault))
        self.assertFalse(self.to_read.exists())

    def test_missing_queued_file_raises_even_with_no_ticks(self):
        self._write("2026-11-10", _digest("Crohn paper", "10.1/x", read_later=False))
        with self.assertRaises(FileNotFoundError):
            run(str(self.vault))

    def test_hand_removed_doi_is_not_readded(self):
        save_queued_dois(str(self.queued_path), {"10.1/removed"})
        self.to_read.write_text("# IBD\n\n# AI\n", encoding="utf-8")
        self._write("2026-11-10", _digest("Crohn paper removed by hand", "10.1/removed"))
        run(str(self.vault))
        self.assertEqual(self.to_read.read_text(encoding="utf-8"), "# IBD\n\n# AI\n")

    def test_added_dois_join_the_queued_set(self):
        save_queued_dois(str(self.queued_path), {"10.1/old"})
        self._write("2026-11-10", _digest("Crohn paper", "10.1/NEW"))
        run(str(self.vault))
        self.assertEqual(load_queued_dois(str(self.queued_path)), {"10.1/old", "10.1/new"})

    def test_relevant_tick_never_reaches_to_read(self):
        save_queued_dois(str(self.queued_path), set())
        self._write(
            "2026-11-10",
            _digest("Crohn relevant only", "10.1/rel", relevant=True, read_later=False),
        )
        run(str(self.vault))
        self.assertFalse(self.to_read.exists())
        self.assertEqual(load_queued_dois(str(self.queued_path)), set())

    def test_parenthesised_doi_kept_whole(self):
        save_queued_dois(str(self.queued_path), set())
        self._write("2026-11-10", _digest("Crohn Lancet paper", PAREN_DOI))
        run(str(self.vault))
        text = self.to_read.read_text(encoding="utf-8")
        self.assertIn(f"[{PAREN_DOI}](https://doi.org/{PAREN_DOI})", text)
        self.assertIn(PAREN_DOI, load_queued_dois(str(self.queued_path)))


class TestBackfill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.vault = Path(self.tmp.name)
        self.papers = self.vault / "Inbox" / "Papers"
        self.papers.mkdir(parents=True)
        save_queued_dois(str(self.vault / "data" / "queued_dois.txt"), set())
        self.to_read = self.vault / "Inbox" / "To Read.md"
        (self.papers / "2026-07-17.md").write_text(
            _digest("Pre-cutoff Crohn paper", "10.1/pre"), encoding="utf-8"
        )
        (self.papers / "2026-11-10.md").write_text(
            _digest("Late-ticked Crohn paper", "10.1/late"), encoding="utf-8"
        )
        for day in range(11, 21):
            (self.papers / f"2026-11-{day}.md").write_text("", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _sections(self) -> tuple[str, str]:
        text = self.to_read.read_text(encoding="utf-8")
        backfill, _, rest = text.partition("\n# IBD\n")
        return backfill, rest

    def test_cutoff_is_fixed(self):
        self.assertEqual(BACKFILL_CUTOFF, date(2026, 11, 2))

    def test_pre_cutoff_goes_to_backfill_post_cutoff_late_tick_goes_to_category(self):
        run(str(self.vault))
        text = self.to_read.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(BACKFILL_HEADING + "\n"))
        backfill, rest = self._sections()
        self.assertIn("10.1/pre", backfill)
        self.assertNotIn("10.1/late", backfill)
        self.assertIn("10.1/late", rest)
        self.assertNotIn("10.1/pre", rest)

    def test_backfill_heading_survives_a_second_run(self):
        run(str(self.vault))
        (self.papers / "2026-11-21.md").write_text(
            _digest("Next Crohn paper", "10.1/next"), encoding="utf-8"
        )
        run(str(self.vault))
        text = self.to_read.read_text(encoding="utf-8")
        self.assertEqual(text.count(BACKFILL_HEADING), 1)
        self.assertTrue(text.startswith(BACKFILL_HEADING + "\n"))
        backfill, rest = self._sections()
        self.assertIn("10.1/pre", backfill)
        self.assertIn("10.1/late", rest)
        self.assertIn("10.1/next", rest)

    def test_no_backfill_heading_without_backfill_entries(self):
        (self.papers / "2026-07-17.md").unlink()
        run(str(self.vault))
        text = self.to_read.read_text(encoding="utf-8")
        self.assertNotIn(BACKFILL_HEADING, text)
        self.assertTrue(text.startswith("# IBD\n"))


class TestSeedFromHistory(unittest.TestCase):
    def test_collects_every_doi_ever_in_to_read(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            note = Path(tmp) / "Inbox" / "To Read.md"
            note.parent.mkdir(parents=True)

            def git(*args: str) -> None:
                subprocess.run(
                    ["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                    check=True,
                    capture_output=True,
                )

            git("init", "-q")
            note.write_text(
                "[10.1/A](https://doi.org/10.1/A)\n"
                f"[{PAREN_DOI}](https://doi.org/{PAREN_DOI})\n"
                "[10.1016/s2468-1253(26](https://doi.org/10.1016/s2468-1253(26)\n",
                encoding="utf-8",
            )
            git("add", "Inbox/To Read.md")
            git("commit", "-q", "-m", "one")
            note.write_text("[10.1/c](https://doi.org/10.1/c)\n", encoding="utf-8")
            git("commit", "-q", "-am", "two")

            self.assertEqual(dois_from_history(tmp), {"10.1/a", PAREN_DOI, "10.1/c"})


if __name__ == "__main__":
    unittest.main()
