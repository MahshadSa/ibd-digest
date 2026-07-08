# Candidate-distribution threshold calibration

Date: 2026-07-08

## Problem

Since the 2026-07-02 overhaul, every scheduled run has placed 100% of papers in
the archive tier (must=0, skim=0 on 07-03 through 07-08 in `data/metrics.txt`).
Papers directly in the maintainer's niche (for example the ECCO UC therapeutics
guideline, 10.1093/ecco-jcc/jjag066) are archived alongside genuine off-domain
noise.

Root cause: `compute_thresholds` in `src/ranking/score.py` derives the tier
cutoffs from the corpus leave-one-out distribution (`corpus_normed @
corpus_normed.T`), i.e. how similar the 42 hand-picked corpus papers are to each
other. Candidates are scored on a different distribution (candidate-vs-corpus
top-3 mean). A curated corpus is far more self-similar than fresh literature is
to it, so the cutoffs land at p96 (skim, 0.9674) and p98 (must, 0.9750) of the
actual candidate-score distribution. Only the top ~2-4% of candidates can clear
the line, so essentially everything archives.

Measured candidate distribution (1233 papers in the local DB snapshot):
p50 = 0.9174, p85 ~ 0.950, p90 = 0.9575, p95 = 0.9640. Relevant IBD-imaging
papers cluster 0.95-0.99; off-domain noise (brain-computer interface,
dermatology, sickle cell) sits 0.83-0.90.

Scoring itself is correct and unchanged. The bug is entirely in how the
surface/archive cutoff is drawn.

## Goal

Draw tier cutoffs from where candidate papers actually land, so that only
genuinely off-domain papers archive. Preserve the existing design intent:
self-calibrating, no manual threshold re-checks, tracks corpus/source drift.
Corpus-anchored scoring and the Relevant -> Corpus feedback loop are unchanged.

## Approach: candidate-distribution calibration

Replace the corpus-self-similarity reference with the distribution of candidate
scores that the system actually produces, persisted across runs so the sample is
large and stable even though the CI database is ephemeral.

### 1. Score history persistence

New committed artifact `data/score_history.txt`: one similarity score per line,
recency-ordered (oldest first, newest appended), capped at the last N = 2000
scores (FIFO trim from the front). Matches the committed-text pattern of
`data/seen_dois.txt` and `data/metrics.txt`.

Recency window (not all-time) is deliberate: as the feedback loop grows the
corpus, candidate scores drift upward, and a rolling window lets the thresholds
track that drift. N = 2000 is roughly 2-3 months at current volume.

New helpers in `src/ranking/score.py` (or a small sibling module, implementer's
choice, kept in `src/ranking/`):
- `load_score_history(path) -> np.ndarray` (empty array if the file is absent).
- `append_scores(path, scores, cap=SCORE_HISTORY_CAP)` appends and trims to the
  last `cap`, writing atomically.

Caveat, recorded and accepted: unlike `seen_dois.txt`, this file is not
rebuildable from the digests (archived papers render no score). If lost it
self-heals over ~2 months of runs, with the fallback constants covering the gap.

### 2. Threshold computation

`compute_thresholds` changes signature to take the candidate score history
instead of the corpus matrix:

    compute_thresholds(score_history: np.ndarray) -> tuple[float, float]

- If `score_history.size < MIN_CALIBRATION`, return the fixed fallbacks
  (`FALLBACK_MUST_READ`, `FALLBACK_SKIM`) as today.
- Otherwise `must = percentile(score_history, MUST_PERCENTILE)`,
  `skim = percentile(score_history, SKIM_PERCENTILE)`.

Anchor constants (starting values, tunable, logged per run in
`data/metrics.txt`):
- `MUST_PERCENTILE = 85`  (~0.950; top ~15%, the clear IBD-imaging hits)
- `SKIM_PERCENTILE = 40`  (~0.908; archive is the bottom ~40%, the off-domain tail)

The corpus leave-one-out code path is removed. `top_k_mean` and `assign_tier`
are unchanged.

### 3. score_and_tier becomes two-pass

`score_and_tier(db_path)`:
1. Load and normalize the corpus (unchanged).
2. Pass 1: for every candidate paper with an embedding, compute its score
   (top-3 mean cosine vs corpus) and its `matching_corpus_doi`. Collect the
   scores in memory; do not tier yet.
3. Append this run's scores to `data/score_history.txt`, then load the full
   (trimmed) window.
4. `compute_thresholds(window)`; record `tier_threshold_must` /
   `tier_threshold_skim` in the meta table as today.
5. Pass 2: assign each paper's tier with `assign_tier(score, must, skim)` and
   write `similarity_score`, `matching_corpus_doi`, `tier`.

Including this run's scores in its own calibration is fine: a single day's batch
(8-33) is a small fraction of a 2000-score window.

The score-history path is a parameter with a default, so tests can point it at a
temp file.

### 4. Bootstrap

Seed `data/score_history.txt` before the first run, so calibration is stable
immediately (CI's DB is empty each run). Source: the local
`data/papers.db` snapshot (1233 papers). Re-score those papers against the
CURRENT corpus (embeddings are already stored in the DB; this is a local,
no-network recompute) and write the resulting scores as the initial history
file. This is the maintainer's ~2 months of candidates, complete with the noise
tail the digests dropped. A one-off script under `scripts/` or a documented
one-liner; it is not part of the daily pipeline.

If the trimmed cap is 2000 and the snapshot has 1233 scores, the file starts
with 1233 lines and grows to the 2000 cap over subsequent runs.

### 5. Workflow

Add `data/score_history.txt` to the commit step in
`.github/workflows/daily-digest.yml` alongside `data/seen_dois.txt` and
`data/metrics.txt`. No other workflow change; `score_and_tier` reads and writes
the file within the existing `src.rank` step.

## Testing (TDD)

Rewrite the threshold tests in `tests/` to the new mechanism:
- `compute_thresholds` returns the correct percentiles on a known distribution,
  and the fallbacks when the history is below `MIN_CALIBRATION`.
- `load_score_history` on a missing file returns an empty array; round-trips a
  written file.
- `append_scores` appends in order and trims to the last `cap` (FIFO from the
  front).
- Two-pass `score_and_tier` on a seeded temp history assigns must/skim/archive
  consistent with the seeded distribution's percentiles, and writes an updated
  history file.
- `top_k_mean` and `assign_tier` unchanged (existing tests kept).

Remove or rewrite any test that pins the old corpus-leave-one-out behavior.
Run: `python -m unittest discover -s tests -t .`

## Documentation

Update to describe candidate-distribution calibration and why the switch was
made (the corpus-self-similarity cutoff sat at p96/p98 of real candidate
scores):
- CLAUDE.md: the Ranking section and the 2026-07-02 overhaul scoring note.
- README.md: the "Rank" step and the "Ranking calibration" section.

## Out of scope

- Scoring method (top-3 mean vs corpus) is unchanged.
- Wildcard tier, digest writer, blocks parser, feedback loop, column, metrics
  format are unchanged (tiers just redistribute).
- Label-driven anchor tuning (using Relevant-ticked papers' scores to validate
  the cutoff) is a later refinement, possible only once surfaced papers
  accumulate Relevant ticks. Recorded as the next step, not built here.
- Verifying the feedback loop writes a corpus note end-to-end (the corpus is
  still the original 42; the loop has never been exercised in production) is a
  separate follow-up.

## Success criteria

- A scheduled run produces a non-trivial must-read + skim split; archive is no
  longer 100%.
- Niche-relevant papers (ECCO-class IBD papers) surface to skim or must-read.
- `data/metrics.txt` shows thresholds near the candidate-distribution
  percentiles (must ~0.95, skim ~0.908) rather than 0.9750/0.9674.
- Both test suites green.
