import os
import tempfile
import unittest
from pathlib import Path

from src.digest.feedback import run as feedback_run
from src.digest.to_read import run as to_read_run, save_queued_dois

DIGEST = """- [ ] **Crohn relevant paper**
- [x] Relevant
- [ ] Read later
  A. Author
  Gut | 2026-06-30
  [10.1/rel](https://doi.org/10.1/rel) | Score: 0.95

- [ ] **Crohn queued paper**
- [ ] Relevant
- [x] Read later
  B. Author
  Gut | 2026-06-30
  [10.1/rl](https://doi.org/10.1/rl) | Score: 0.94
"""


class TestVaultIsolation(unittest.TestCase):
    def test_sweeps_write_only_under_vault_root(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as vault_tmp, \
                tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd_tmp:
            vault = Path(vault_tmp)
            papers = vault / "Inbox" / "Papers"
            papers.mkdir(parents=True)
            (papers / "2026-07-17.md").write_text(DIGEST, encoding="utf-8")
            save_queued_dois(str(vault / "data" / "queued_dois.txt"), set())

            old_cwd = os.getcwd()
            os.chdir(cwd_tmp)
            try:
                feedback_run(vault_tmp)
                to_read_run(vault_tmp)
            finally:
                os.chdir(old_cwd)

            self.assertEqual(os.listdir(cwd_tmp), [])
            self.assertTrue((vault / "Corpus" / "10.1_rel.md").exists())
            to_read = (vault / "Inbox" / "To Read.md").read_text(encoding="utf-8")
            self.assertIn("10.1/rl", to_read)
            self.assertNotIn("10.1/rel)", to_read)
            queued = (vault / "data" / "queued_dois.txt").read_text(encoding="utf-8")
            self.assertEqual(queued, "10.1/rl\n")


if __name__ == "__main__":
    unittest.main()
