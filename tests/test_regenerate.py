import tempfile
import unittest
from pathlib import Path

from scripts.regenerate_digests import dois_from_digest


SAMPLE = """# IBD Imaging Digest - 2026-07-08

- [ ] **Paper One**
  A B, C D
  Radiology | 2026-07-01
  [10.1/aaa](https://doi.org/10.1/aaa) | Score: 0.95

> [!abstract]- Archive (2)
>
> - **Paper Two**
>   E F
>   [10.1/bbb](https://doi.org/10.1/bbb)
>
> - **Paper Three**
>   G H
>   [10.1/aaa](https://doi.org/10.1/aaa)
"""


class TestDoisFromDigest(unittest.TestCase):
    def test_extracts_ordered_unique_dois(self):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "2026-07-08.md"
        path.write_text(SAMPLE, encoding="utf-8")
        self.assertEqual(dois_from_digest(str(path)), ["10.1/aaa", "10.1/bbb"])
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
