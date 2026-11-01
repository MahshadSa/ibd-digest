import tempfile
import unittest
from pathlib import Path

from src.corpus import _parse_note
from src.digest.feedback import run as feedback_run

DIGEST = """# IBD Imaging Digest - 2026-07-01

> [!important] Must-read (3)

- [ ] **Ticked relevant paper**
- [x] Relevant
- [ ] Read later
  A. One, B. Two
  Radiology | 2026-06-30
  [10.1/ticked](https://doi.org/10.1/ticked) | Score: 0.96

  > [!abstract]-
  > Background: para one.
  >
  > Methods: para two.

- [ ] **Read later only paper**
- [ ] Relevant
- [x] Read later
  C. Three, D. Four
  Gut | 2026-06-29
  [10.1/rlonly](https://doi.org/10.1/rlonly) | Score: 0.95

- [ ] **Unticked paper**
- [ ] Relevant
- [ ] Read later
  E. Five
  Gut | 2026-06-28
  [10.1/none](https://doi.org/10.1/none) | Score: 0.94
"""

LANCET_A = "10.1016/s2468-1253(26)00292-x"
LANCET_B = "10.1016/s2468-1253(26)00148-2"

OLD_DIGEST = f"""# IBD Imaging Digest - 2026-07-17

> [!important] Must-read (2)

- [ ] **Lancet paper A**
- [x] Relevant
- [ ] Read later
  A. One
  The Lancet Gastroenterology & Hepatology | 2026-07-01
  [{LANCET_A}](https://doi.org/{LANCET_A}) | Score: 0.96

- [ ] **Lancet paper B**
- [x] Relevant
- [ ] Read later
  B. Two
  The Lancet Gastroenterology & Hepatology | 2026-07-01
  [{LANCET_B}](https://doi.org/{LANCET_B}) | Score: 0.95
"""


class TestFeedbackScanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.vault = Path(self.tmp.name)
        papers = self.vault / "Inbox" / "Papers"
        papers.mkdir(parents=True)
        (papers / "2026-07-01.md").write_text(DIGEST, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_relevant_tick_becomes_corpus_note(self):
        added = feedback_run(str(self.vault), window=7)
        self.assertEqual(added, 1)
        note = self.vault / "Corpus" / "10.1_ticked.md"
        self.assertTrue(note.exists())
        doi, title, abstract = _parse_note(note)
        self.assertEqual(doi, "10.1/ticked")
        self.assertEqual(title, "Ticked relevant paper")
        self.assertEqual(abstract, "Background: para one.\n\nMethods: para two.")

    def test_read_later_tick_never_reaches_corpus(self):
        feedback_run(str(self.vault), window=7)
        self.assertFalse((self.vault / "Corpus" / "10.1_rlonly.md").exists())
        self.assertFalse((self.vault / "Corpus" / "10.1_none.md").exists())

    def test_rerun_is_idempotent(self):
        feedback_run(str(self.vault), window=7)
        added = feedback_run(str(self.vault), window=7)
        self.assertEqual(added, 0)

    def test_tick_older_than_seven_digests_is_picked_up(self):
        papers = self.vault / "Inbox" / "Papers"
        (papers / "2026-07-17.md").write_text(OLD_DIGEST, encoding="utf-8")
        for day in range(1, 11):
            (papers / f"2026-10-{day:02d}.md").write_text("", encoding="utf-8")
        added = feedback_run(str(self.vault))
        self.assertEqual(added, 3)
        self.assertTrue((self.vault / "Corpus" / "10.1_ticked.md").exists())

    def test_parenthesised_dois_get_distinct_full_slug_notes(self):
        papers = self.vault / "Inbox" / "Papers"
        (papers / "2026-07-17.md").write_text(OLD_DIGEST, encoding="utf-8")
        corpus = self.vault / "Corpus"
        corpus.mkdir()
        (corpus / "10.1016_s2468-1253(26.md").write_text(
            "# Truncated\n\nDOI: [10.1016/s2468-1253(26](https://doi.org/x)\n",
            encoding="utf-8",
        )
        feedback_run(str(self.vault))
        for doi in (LANCET_A, LANCET_B):
            note = corpus / f"{doi.replace('/', '_')}.md"
            self.assertTrue(note.exists(), note.name)
            self.assertEqual(_parse_note(note)[0], doi)


if __name__ == "__main__":
    unittest.main()
