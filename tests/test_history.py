import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.ranking.history import (
    SCORE_HISTORY_CAP,
    append_scores,
    load_score_history,
)


class TestScoreHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "score_history.txt")

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_file_returns_empty(self):
        arr = load_score_history(self.path)
        self.assertEqual(arr.size, 0)

    def test_append_then_load_roundtrip_in_order(self):
        append_scores(self.path, [0.1, 0.2, 0.3])
        arr = load_score_history(self.path)
        np.testing.assert_allclose(arr, [0.1, 0.2, 0.3], atol=1e-6)

    def test_append_is_additive_and_ordered(self):
        append_scores(self.path, [0.1, 0.2])
        append_scores(self.path, [0.3])
        arr = load_score_history(self.path)
        np.testing.assert_allclose(arr, [0.1, 0.2, 0.3], atol=1e-6)

    def test_cap_keeps_last_n(self):
        append_scores(self.path, [0.1, 0.2, 0.3, 0.4, 0.5], cap=3)
        arr = load_score_history(self.path)
        np.testing.assert_allclose(arr, [0.3, 0.4, 0.5], atol=1e-6)

    def test_cap_default_is_2000(self):
        self.assertEqual(SCORE_HISTORY_CAP, 2000)

    def test_load_ignores_blank_lines(self):
        Path(self.path).write_text("0.1\n\n0.2\n", encoding="utf-8")
        arr = load_score_history(self.path)
        np.testing.assert_allclose(arr, [0.1, 0.2], atol=1e-6)


if __name__ == "__main__":
    unittest.main()
