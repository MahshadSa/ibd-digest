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

1. **Fetch.** Each day, the pipeline queries PubMed via E-utilities and Crossref
   for three target journals (Radiology, Radiology: AI, European Radiology),
   deduplicates by DOI, and stores new papers in SQLite.
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
│   ├── fetchers/             pubmed.py, crossref.py
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

Thresholds should be re-checked monthly as the corpus grows.

### Known limitations

- Corpus is provisional (~40 DOIs). Ranking will improve as it grows.
- No feedback loop yet. Checking boxes in the digest does not currently affect
  future rankings.
- Preprint servers (bioRxiv, medRxiv) and additional journals not yet
  integrated.
- The system is single-user. No multi-user or sharing primitives.