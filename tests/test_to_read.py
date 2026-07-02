import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.digest.to_read import extract_read_later_entries

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

    def test_old_format_still_parses(self):
        entries = self._extract(OLD_FORMAT_DIGEST, date(2026, 5, 1))
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e["title"], "Old style paper")
        self.assertEqual(e["authors"], "X. Author, Y. Author")
        self.assertEqual(e["doi"], "10.1/old")
        self.assertEqual(e["abstract"], "Old abstract.")


if __name__ == "__main__":
    unittest.main()
