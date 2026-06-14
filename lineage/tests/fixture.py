"""Shared fixture loader for the lineage tests."""
import json
from collections import Counter
from pathlib import Path

from lineage.resolve import WorkNotFound

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "openalex_sample.json"
SEED_DOI = "10.1000/seed"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def make_fetch(data: dict | None = None):
    """Return (fetch, calls) where fetch looks works up in data (the fixture by
    default) and calls counts how many times each ref was requested. A missing
    ref raises WorkNotFound, modeling the live 404 contract.
    """
    if data is None:
        data = load_fixture()
    calls: Counter[str] = Counter()

    def fetch(ref: str) -> dict:
        calls[ref] += 1
        if ref not in data:
            raise WorkNotFound(ref)
        return data[ref]

    return fetch, calls
