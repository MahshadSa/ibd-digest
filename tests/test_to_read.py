import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.digest.to_read import (
    append_entries,
    categorize_paper,
    extract_read_later_entries,
    run,
)

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
            "digest_date": date(2026, 7, 1),
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

            self.assertEqual(append_entries(path, entries), 2)
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

            self.assertEqual(append_entries(path, []), 0)
            migrated = path.read_text(encoding="utf-8")
            self.assertTrue(migrated.startswith("# IBD\n"))
            self.assertEqual(migrated.count("# IBD"), 1)
            self.assertEqual(migrated.count("# AI"), 1)
            self.assertIn("### Existing Crohn's paper", migrated)
            self.assertIn("> [!abstract]- Abstract\n> Artificial intelligence study.", migrated)
            self.assertNotIn("\n## Existing", migrated)

            duplicate = self._entry("10.1/existing", "Crohn's duplicate")
            self.assertEqual(append_entries(path, [duplicate]), 0)
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
            (papers_dir / "2026-07-01.md").write_text(digest, encoding="utf-8")

            run(tmp, digest_date=date(2026, 7, 1))

            text = (Path(tmp) / "Inbox" / "To Read.md").read_text(encoding="utf-8")
            ibd_section, separator, ai_section = text.partition("\n# AI\n")
            self.assertEqual(separator, "\n# AI\n")
            self.assertIn("10.1/mixed", ibd_section)
            self.assertIn("10.1/ai", ai_section)
            self.assertIn("### AI-assisted Crohn's disease assessment", ibd_section)


if __name__ == "__main__":
    unittest.main()
