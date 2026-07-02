import unittest

from src.digest.blocks import parse_block, split_into_blocks

NEW_BLOCK = [
    "- [ ] **Deep learning for MRE**",
    "- [x] Relevant",
    "- [ ] Read later",
    "  A. One, B. Two, C. Corr",
    "  Radiology | 2026-06-30",
    "  [10.1/abc](https://doi.org/10.1/abc) | Score: 0.93",
    "  Nearest seed: A corpus paper title",
    "",
    "  > [!abstract]-",
    "  > Background: first paragraph.",
    "  >",
    "  > Methods: second paragraph.",
]

OLD_BLOCK = [
    "- [ ] **Old format paper**",
    "- [x] Read later",
    "  X. Author, Y. Author",
    "  Gut | 2026-05-01",
    "  [10.1/old](https://doi.org/10.1/old) | Score: 0.91",
    "",
    "  > [!abstract]-",
    "  > Only paragraph.",
]


class TestSplitIntoBlocks(unittest.TestCase):
    def test_splits_on_title_lines(self):
        lines = NEW_BLOCK + [""] + OLD_BLOCK
        blocks = split_into_blocks(lines)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0][0], NEW_BLOCK[0])
        self.assertEqual(blocks[1][0], OLD_BLOCK[0])


class TestParseBlock(unittest.TestCase):
    def test_new_format_fields(self):
        p = parse_block(NEW_BLOCK)
        self.assertEqual(p["title"], "Deep learning for MRE")
        self.assertTrue(p["relevant_checked"])
        self.assertFalse(p["read_later_checked"])
        self.assertEqual(p["authors"], "A. One, B. Two, C. Corr")
        self.assertEqual(p["journal"], "Radiology")
        self.assertEqual(p["pub_date"], "2026-06-30")
        self.assertEqual(p["doi"], "10.1/abc")
        self.assertEqual(p["score"], "0.93")
        self.assertEqual(
            p["abstract"],
            "Background: first paragraph.\n\nMethods: second paragraph.",
        )

    def test_old_format_fields(self):
        p = parse_block(OLD_BLOCK)
        self.assertEqual(p["title"], "Old format paper")
        self.assertFalse(p["relevant_checked"])
        self.assertTrue(p["read_later_checked"])
        self.assertEqual(p["authors"], "X. Author, Y. Author")
        self.assertEqual(p["journal"], "Gut")
        self.assertEqual(p["pub_date"], "2026-05-01")
        self.assertEqual(p["doi"], "10.1/old")
        self.assertEqual(p["abstract"], "Only paragraph.")

    def test_relevant_tick_does_not_count_as_read_later(self):
        block = list(NEW_BLOCK)
        p = parse_block(block)
        self.assertTrue(p["relevant_checked"])
        self.assertFalse(p["read_later_checked"])

    def test_nearest_seed_line_does_not_shift_fields(self):
        no_nearest = NEW_BLOCK[:6] + NEW_BLOCK[7:]
        p = parse_block(no_nearest)
        self.assertEqual(p["authors"], "A. One, B. Two, C. Corr")
        self.assertEqual(p["doi"], "10.1/abc")


if __name__ == "__main__":
    unittest.main()
