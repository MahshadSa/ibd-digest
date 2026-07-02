import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from src.digest.column import last_completed_week, run as column_run

DIGEST_A = """# IBD Imaging Digest - {d}

> [!important] Must-read (1)

- [ ] **Weekly must paper**
- [ ] Relevant
- [ ] Read later
  A. One, B. Two
  Radiology | 2026-06-20
  [10.1/must](https://doi.org/10.1/must) | Score: 0.97

---

> [!note] Skim (1)

- [ ] **Queued skim paper**
- [ ] Relevant
- [x] Read later
  C. Three
  Gut | 2026-06-19
  [10.1/queue](https://doi.org/10.1/queue) | Score: 0.94
"""

DIGEST_B = """# IBD Imaging Digest - {d}

> [!important] Must-read (1)

- [ ] **Weekly must paper**
- [ ] Relevant
- [ ] Read later
  A. One, B. Two
  Radiology | 2026-06-20
  [10.1/must](https://doi.org/10.1/must) | Score: 0.97

---

> [!question] Wildcard (1)

- [ ] **Ticked wildcard paper**
- [x] Relevant
- [ ] Read later
  D. Four
  Nature Medicine | 2026-06-21
  [10.1/wild](https://doi.org/10.1/wild) | Score: 0.80
"""


class TestLastCompletedWeek(unittest.TestCase):
    def test_returns_previous_monday(self):
        # 2026-07-02 is a Thursday; previous week's Monday is 2026-06-22
        monday = last_completed_week(date(2026, 7, 2))
        self.assertEqual(monday.weekday(), 0)
        self.assertEqual(monday, date(2026, 6, 22))

    def test_monday_still_returns_completed_week(self):
        monday = last_completed_week(date(2026, 6, 29))
        self.assertEqual(monday, date(2026, 6, 22))


class TestColumnPacket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.vault = Path(self.tmp.name)
        papers = self.vault / "Inbox" / "Papers"
        papers.mkdir(parents=True)
        self.today = date(2026, 7, 2)
        self.monday = date(2026, 6, 22)
        d1 = self.monday + timedelta(days=1)
        d2 = self.monday + timedelta(days=3)
        (papers / f"{d1.isoformat()}.md").write_text(
            DIGEST_A.format(d=d1.isoformat()), encoding="utf-8"
        )
        (papers / f"{d2.isoformat()}.md").write_text(
            DIGEST_B.format(d=d2.isoformat()), encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _packet_path(self) -> Path:
        iso = self.monday.isocalendar()
        return self.vault / "Inbox" / "Column" / f"{iso.year}-W{iso.week:02d}.md"

    def test_packet_collects_and_dedups(self):
        out = column_run(str(self.vault), today=self.today)
        self.assertEqual(out, self._packet_path())
        text = out.read_text(encoding="utf-8")
        self.assertIn("## Must-read this week", text)
        self.assertEqual(text.count("Weekly must paper"), 1)  # deduped across days
        self.assertIn("## Marked relevant", text)
        self.assertIn("Ticked wildcard paper", text)
        self.assertIn("## Queued to read", text)
        self.assertIn("Queued skim paper", text)

    def test_write_once(self):
        column_run(str(self.vault), today=self.today)
        again = column_run(str(self.vault), today=self.today)
        self.assertIsNone(again)


if __name__ == "__main__":
    unittest.main()
