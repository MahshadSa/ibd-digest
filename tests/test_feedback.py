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


if __name__ == "__main__":
    unittest.main()
