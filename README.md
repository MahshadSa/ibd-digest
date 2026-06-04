# IBD Imaging Digest

A daily pipeline that surfaces newly published inflammatory bowel disease imaging
research, ranks it for clinical and methodological relevance using SPECTER2
scientific paper embeddings, and delivers a structured digest to a personal
Obsidian knowledge vault.

Built to solve a concrete problem in my own research workflow: the literature on
IBD imaging is spread across radiology, gastroenterology, and AI venues, and
manual triage was costing more time than it returned. The system runs without
supervision, ranks against a curated personal corpus, and is designed to learn
from reading behavior over time.

## How it works

1. **Fetch.** Each day, the pipeline queries PubMed via E-utilities (a
   topic-filtered, journal-agnostic search) and Crossref (a journal-filtered,
   topic-agnostic pull of recent papers from a curated journal list),
   deduplicates by DOI, and stores new papers in SQLite. See Source selection
   below for why both paths exist.
2. **Embed.** Each paper is embedded with SPECTER2 (`allenai/specter2_base`),
   a scientific document embedding model, using the title and abstract.
3. **Rank.** Each paper is scored by maximum cosine similarity against a corpus
   of seed DOIs representing the research interests of the maintainer. Papers
   are sorted into three tiers (must-read, skim, archive) using
   percentile-anchored thresholds calibrated to the corpus.
4. **Deliver.** A Markdown digest is written to the Obsidian vault at
   `Inbox/Papers/YYYY-MM-DD.md`, with each tier in its own callout block. Must-read
   and skim papers each carry two independent checkboxes: `Relevant` feeds the
   corpus feedback loop; `Read later` queues the paper for offline review.
5. **Collect.** Running `src.digest.to_read` after reviewing a digest scans for
   checked `Read later` boxes and appends each paper's title, authors, abstract,
   and a backlink to a persistent rolling note at `Inbox/To Read.md`. Re-running
   is idempotent: deduplication is by DOI.
6. **Schedule.** A GitHub Actions workflow runs the pipeline daily and commits
   state back to the repository.

A feedback loop that adds `Relevant`-checked papers to the corpus, refining the
ranker over time, is planned as the next phase.

## Status

Operational since May 2026. Scheduling, persistence, and the Read later queue
complete. The corpus feedback loop (Relevant checkbox to ranker) is deferred
pending two weeks of sustained daily use.

## Stack

Python, SQLite, SPECTER2 via HuggingFace Transformers, NumPy, NCBI E-utilities,
Crossref REST API, GitHub Actions, Obsidian.

---

## Operational notes

### Project structure

\`\`\`
ibd-digest-vault/
├── src/
│   ├── fetch.py              entry point: fetch new papers
│   ├── rank.py               entry point: embed pending + score and tier
│   ├── corpus.py             entry point: rebuild corpus from seed DOIs
│   ├── db.py                 SQLite schema and migrations
│   ├── fetchers/             pubmed.py, journals.py
│   ├── ranking/              embed.py, score.py
│   └── digest/
│       ├── writer.py         Markdown digest generator
│       └── to_read.py        Read later queue scanner
├── data/papers.db            SQLite, committed
├── Corpus/seed_dois.txt      curated DOIs defining "relevant"
├── Inbox/Papers/             daily digests, YYYY-MM-DD.md
├── Inbox/To Read.md          rolling Read later queue
└── .github/workflows/daily-digest.yml
\`\`\`

### Source selection

Two independent fetch paths, merged and deduplicated by DOI:

- **PubMed** is topic-filtered and journal-agnostic. The query gates on IBD terms
  AND imaging/AI terms, plus a review/guideline branch and a non-IBD-gated branch
  for abdominal radiology AI and agentic AI. It searches all indexed journals, so
  broad venues are covered here on topic.
- **Crossref** is journal-filtered and topic-agnostic. It pulls the most recent
  papers from a fixed journal list, regardless of subject. Used because Crossref
  surfaces DOIs days after online publication while PubMed indexing lags weeks.
  Direct journal pulls are how we see key-journal papers early.

Broad journals are pulled via Crossref despite the noise (they contribute mostly
off-topic papers) because timeliness is prioritized over digest cleanliness.
SPECTER2 ranking and percentile thresholds push off-topic papers to the archive
tier. This is an accepted trade, not an oversight.

Narrow journals (Radiology: AI, JCC, Inflammatory Bowel Diseases, etc.) are
trusted wholesale. Broad journals (Gut-class, Alimentary Pharmacology &
Therapeutics, Lancet Gastroenterology & Hepatology, Clinical Gastroenterology and
Hepatology) carry significant off-topic volume.

Planned mitigation: a keyword prefilter on the Crossref path only, applied to
broad journals, gating on IBD/imaging terms before embedding to cut compute and
digest length. Deferred until enough days of real data show what the term list
needs to catch. Narrow journals will bypass the prefilter via an allowlist.

Deliberately excluded: IEEE TMI and other foundational-methods venues (mostly
non-abdominal, non-IBD). The input is kept IBD-imaging focused even though
reading is wider than the column's scope.

### Local development

\`\`\`
.venv\Scripts\python.exe -m src.fetch
.venv\Scripts\python.exe -m src.rank
.venv\Scripts\python.exe -m src.digest.writer .
.venv\Scripts\python.exe -m src.digest.to_read .
\`\`\`

The writer refuses to overwrite an existing daily digest by default. Pass
`--force` to overwrite (used by the scheduled workflow).

After marking `Read later` boxes in a digest, run `src.digest.to_read` to append
those papers to `Inbox/To Read.md`. Pass `--date YYYY-MM-DD` to process a past
digest. Re-running the same date is safe; entries already in the note are skipped.

### Scheduled runs

The workflow runs at 02:00 UTC daily (05:30 Tehran time). To trigger manually,
use `workflow_dispatch` from the Actions tab.

After a successful run, pull from the vault root to see the new digest locally:

\`\`\`
git pull
\`\`\`

### Configuration

Required environment variables (local `.env`, or repo secrets for Actions):

- `NCBI_API_KEY`
- `NCBI_EMAIL`

### Ranking calibration

SPECTER2 produces high cosine similarities for in-domain biomedical text, so
fixed thresholds do not generalize. Current tiers are anchored to corpus
percentiles:

- must-read: similarity >= 0.958 (top 10%)
- skim: 0.924 to 0.958 (next 40%)
- archive: < 0.924 (bottom 50%)

Thresholds should be re-checked monthly as the corpus grows, and off-cycle after
any source expansion. Adding journals shifts the tier distribution because more
papers are scored against the same corpus.

### Known limitations

- Corpus is provisional (~40 DOIs). Ranking will improve as it grows.
- No feedback loop yet. Checking boxes in the digest does not currently affect
  future rankings.
- Broad-journal Crossref pulls are unfiltered, so the archive tier carries
  significant off-topic volume until the planned keyword prefilter lands.
- Preprint servers (bioRxiv, medRxiv) not yet integrated.
- The system is single-user. No multi-user or sharing primitives.