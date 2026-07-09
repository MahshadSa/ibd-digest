# Regenerate the broken July digests via DOI rehydration

Date: 2026-07-09

## Problem

The digests for 2026-07-03 through 2026-07-08 were produced under the broken
corpus-self-similarity calibration, so all papers archived (must=0, skim=0 on
every day; see data/metrics.txt). The candidate-distribution calibration fix has
landed on main. We want those six days re-ranked and re-written with the correct
p85/p40 thresholds so the niche-relevant papers that were buried in archive
surface.

The blocker: the digests do not preserve the data needed to re-rank. Scoring
needs title + abstract, but the digest stores an abstract only for surfaced
papers (07-08 has 33 papers, 1 abstract). Everything archived, so those
abstracts were discarded, and data/papers.db is ephemeral. The abstracts must be
re-acquired from the sources by DOI.

## Scope

- Regenerate exactly 2026-07-03, 04, 05, 06, 07, 08 (the all-archive days).
- Leave 2026-07-01 (must 1 / skim 8) and 2026-07-02 (must 4 / skim 14): they
  predate the bug and have correct splits.
- Do NOT preserve existing checkbox ticks (explicit decision). The files are
  rewritten fresh. No feedback/to_read preservation step.
- The corpus is unchanged (42 notes); this is a re-rank, not a corpus change.

## Approach: rehydrate by DOI, then re-run the normal pipeline per date

Mirror the production pipeline (corpus from-notes -> rank -> writer) but replace
the date-range fetch with a by-DOI rehydration that reads DOIs from the existing
digest files and pins each paper's seen_date to the digest it came from.

### 1. Fetch-by-DOI helper

New `src/fetchers/by_doi.py`:

    fetch_by_doi(doi: str, email: str, api_key: str | None) -> dict | None

Returns a paper dict in the same shape the existing fetchers emit (doi, title,
authors, corresponding_author, journal, pub_date, abstract, source), or None if
the DOI cannot be resolved at all.

- Try Crossref `https://api.crossref.org/works/{doi}` first, parse with the
  existing `_parse_crossref_item` from `src/fetchers/journals.py` (reused, not
  duplicated). source label "crossref-rehydrate".
- If Crossref returns no abstract, try PubMed: esearch the DOI (as `{doi}[AID]`,
  the Article Identifier field; exact tag pinned and fixture-tested in the plan)
  -> PMID -> efetch -> parse with the existing `_parse_article` from
  `src/fetchers/pubmed.py`. Keep whichever result has an abstract; prefer the
  PubMed record when it supplies the abstract Crossref lacked.
- If neither yields an abstract, return the Crossref record with abstract=None.
  Title-only embedding is what the live pipeline already does for
  abstract-less papers, so this is faithful, not a degradation introduced here.

Network: Crossref and PubMed are unreachable from the container, so this runs on
the laptop. Build and unit-test in the container against fixtures.

### 2. Orchestration script

New `scripts/regenerate_digests.py` (one-off maintenance, like
scripts/bootstrap_score_history.py, not part of the daily pipeline):

    python -m scripts.regenerate_digests [vault_root] [db_path]

Steps (all on the laptop):
1. Start a fresh DB at db_path (default data/papers.db): `migrate` +
   `migrate_embedding_columns`. The mid-June snapshot is no longer needed (its
   scores were already captured into data/score_history.txt by the bootstrap).
2. `rebuild_corpus_from_notes(db_path)` to populate the corpus table (needs
   SPECTER2, cached locally).
3. For each date in 2026-07-03..08: read the DOIs from
   `Inbox/Papers/<date>.md` (reuse the DOI link regex), `fetch_by_doi` each,
   and `insert_paper` with `seen_date` set to that date. A DOI that returns
   None is logged and skipped.
4. `embed_pending(db_path, MODEL_NAME)` then
   `score_and_tier(db_path)` once over all rehydrated papers: one consistent
   threshold set from the current score-history window, applied to all six days.
5. For each date: run the digest writer with force for that date, then
   `src.metrics` for that date (replaces the all-archive line in
   data/metrics.txt).

Per-date DOI extraction and the seen_date pin are what let the unchanged writer
(`WHERE seen_date = <date>`) regroup the papers back onto their original day.

### 3. Score-history interaction

`score_and_tier` appends the ~148 rehydrated scores to data/score_history.txt
and calibrates from the window (1233 seed + 148 = 1381, under the 2000 cap).
This is legitimate real candidate data and makes the window more current; it is
an accepted side effect, not a problem. Because the regeneration DB is fresh
(only the July papers), only those ~148 scores are appended, not the whole
snapshot.

## Testing (TDD)

Container, against fixtures (stdlib unittest):
- `fetch_by_doi` parses a Crossref `/works/{doi}` payload into the paper dict
  (fixture JSON).
- `fetch_by_doi` falls back to PubMed when the Crossref payload has no abstract
  (injected fetch callables / fixture XML).
- `fetch_by_doi` returns abstract=None when neither source has an abstract.
- Per-date DOI extraction pulls exactly the DOI links from a sample digest file
  and ignores DOIs inside abstract text.

HTTP is injected (callable parameters) so the tests never hit the network,
matching the lineage fetcher test pattern. End-to-end is the laptop run.

## Out of scope

- The calibration fix itself (already on main).
- 07-01, 07-02, and any pre-July digest.
- Tick preservation, feedback loop, Read later queue.
- A general by-DOI fetch entry point in `src.fetch` (this is a one-off script;
  keep it in scripts/).

## Success criteria

- After the laptop run, 2026-07-03..08 each show a non-trivial must/skim split
  and niche-relevant papers (e.g. the ECCO UC guideline on 07-08) surface out of
  archive.
- data/metrics.txt lines for those six dates show real per-tier counts and the
  candidate-distribution thresholds (~0.947 / ~0.900), not 0.975 / 0.967.
- Each regenerated digest carries the normal checkboxes so the now-surfaced
  papers can feed the corpus going forward.
- Unit tests for `fetch_by_doi` and DOI extraction pass in the container.
