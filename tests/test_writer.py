import json
import unittest
from datetime import date

from src.digest.writer import render_digest, render_paper_full


def make_paper(doi: str, title: str, tier: str, score: float = 0.9) -> dict:
    return {
        "doi": doi,
        "title": title,
        "authors": json.dumps(["A. One", "B. Two", "C. Three"]),
        "corresponding_author": "Z. Corr",
        "journal": "Radiology",
        "pub_date": "2026-06-30",
        "abstract": "Background: first.\nMethods: second.",
        "source": "pubmed",
        "similarity_score": score,
        "tier": tier,
    }


class TestRenderPaperFull(unittest.TestCase):
    def test_block_layout_with_nearest(self):
        lines = render_paper_full(
            make_paper("10.1/a", "Title A", "must-read"), nearest="Corpus title X"
        ).splitlines()
        self.assertEqual(lines[0], "- [ ] **Title A**")
        self.assertEqual(lines[1], "- [ ] Relevant")
        self.assertEqual(lines[2], "- [ ] Read later")
        self.assertEqual(lines[3], "  A. One, B. Two, Z. Corr")
        self.assertEqual(lines[4], "  Radiology | 2026-06-30")
        self.assertEqual(lines[5], "  [10.1/a](https://doi.org/10.1/a) | Score: 0.90")
        self.assertEqual(lines[6], "  Nearest seed: Corpus title X")
        self.assertIn("  > [!abstract]-", lines)
        self.assertIn("  > Background: first.", lines)

    def test_no_nearest_line_when_absent(self):
        text = render_paper_full(make_paper("10.1/a", "Title A", "must-read"))
        self.assertNotIn("Nearest seed:", text)


class TestRenderDigestWildcard(unittest.TestCase):
    def setUp(self):
        self.papers = [
            make_paper("10.1/m", "Must paper", "must-read", 0.97),
            make_paper("10.1/s", "Skim paper", "skim", 0.94),
            make_paper("10.1/r1", "Archive one", "archive", 0.80),
            make_paper("10.1/r2", "Archive two", "archive", 0.79),
            make_paper("10.1/r3", "Archive three", "archive", 0.78),
            make_paper("10.1/r4", "Archive four", "archive", 0.77),
        ]
        self.day = date(2026, 7, 2)

    def test_wildcard_section_promotes_two_archive_papers(self):
        text = render_digest(self.papers, self.day)
        self.assertIn("> [!question] Wildcard (2)", text)
        # exactly two archive papers remain inside the archive callout body
        archive_titles = [
            line for line in text.splitlines() if line.startswith("> - **")
        ]
        self.assertEqual(len(archive_titles), 2)
        # every archive paper appears exactly once, either promoted or archived
        for title in ["Archive one", "Archive two", "Archive three", "Archive four"]:
            self.assertEqual(text.count(f"**{title}**"), 1)
        # promoted papers carry the full checkbox block
        self.assertEqual(text.count("- [ ] Relevant"), 4)  # must + skim + 2 wildcards

    def test_wildcard_is_deterministic_per_date(self):
        self.assertEqual(
            render_digest(self.papers, self.day), render_digest(self.papers, self.day)
        )

    def test_nearest_by_doi_rendered(self):
        text = render_digest(
            self.papers, self.day, nearest_by_doi={"10.1/m": "Seed title Q"}
        )
        self.assertIn("  Nearest seed: Seed title Q", text)

    def test_empty_day_unchanged(self):
        text = render_digest([], self.day)
        self.assertIn("No new papers today, pipeline ran successfully.", text)
        self.assertNotIn("Wildcard", text)


if __name__ == "__main__":
    unittest.main()
