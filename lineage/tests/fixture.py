"""Shared fixture loader for the lineage tests."""
import json
from collections import Counter
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "openalex_sample.json"
SEED_DOI = "10.1000/seed"


def make_fetch():
    """Return (fetch, calls) where fetch looks works up in the fixture and calls
    counts how many times each ref was requested.
    """
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    calls: Counter[str] = Counter()

    def fetch(ref: str) -> dict:
        calls[ref] += 1
        return data[ref]

    return fetch, calls
