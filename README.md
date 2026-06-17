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
   deduplicates by DOI against a persistent seen-DOI list
   (`data/seen_dois.txt`), and stores new papers in SQLite. See Source
   selection below for why both paths exist.
2. **Embed.** Each paper is embedded with SPECTER2 (`allenai/specter2_base`),
   a scientific document embedding model, using the title and abstract.
3. **Rank.** Each paper is scored by maximum cosine similarity against a corpus
   of seed DOIs representing the research interests of the maintainer. Papers
   are sorted into three tiers (must-read, skim, archive) using
   percentile-anchored thresholds calibrated to the corpus. The corpus
   embeddings are rebuilt from committed Markdown notes at the start of each
   run, so ranking works even though the database itself is not persisted.
4. **Deliver.** A Markdown digest is written to the Obsidian vault at
   `Inbox/Papers/YYYY-MM-DD.md`, with each tier in its own callout block. Must-read
   and skim papers each carry two independent checkboxes: `Relevant` feeds the
   corpus feedback loop; `Read later` queues the paper for offline review.
5. **Collect.** Running `src.digest.to_read` after reviewing a digest scans for
   checked `Read later` boxes and appends each paper's title, authors, abstract,
   and a backlink to a persistent rolling note at `Inbox/To Read.md`. Re-running
   is idempotent: deduplication is by DOI.
6. **Schedule.** A GitHub Actions workflow runs the pipeline daily and commits
   the digests, the Read later queue, and the dedup list back to the repository.
   The SQLite database is not committed; it is rebuilt from committed text each
   run (see State and persistence).

A feedback loop that adds `Relevant`-checked papers to the corpus, refining the
ranker over time, is planned as the next phase.

## Status

Operational since May 2026. Scheduling, persistence, the Read later queue, and
an expanded source list (17 Crossref journals plus a broadened PubMed query) are
complete. The corpus feedback loop (Relevant checkbox to ranker) is the one
unbuilt pipeline step; it is deferred in favor of beginning the weekly column,
which will reveal whether ranking quality is the real bottleneck.

## Stack

Python, SQLite, SPECTER2 via HuggingFace Transformers, NumPy, NCBI E-utilities,
Crossref REST API, GitHub Actions, Obsidian.

---

## Operational notes

### Project structure

\`\`\`
ibd-digest-vault/
├── src/
│   ├── fetch.py              entry point: fetch new papers, dedup vs seen list
│   ├── rank.py               entry point: embed pending + score and tier
│   ├── corpus.py             entry point: build corpus from seed DOIs (network)
│   │                         or rebuild from committed notes (offline)
│   ├── seen.py               persistent seen-DOI dedup list IO + recovery
│   ├── db.py                 SQLite schema and migrations
│   ├── fetchers/             pubmed.py, journals.py
│   ├── ranking/              embed.py, score.py
│   └── digest/
│       ├── writer.py         Markdown digest generator
│       └── to_read.py        Read later queue scanner
├── data/papers.db            SQLite, gitignored, rebuilt empty each run
├── data/seen_dois.txt        durable dedup list (every DOI surfaced), committed
├── Corpus/seed_dois.txt      curated DOIs defining "relevant"
├── Corpus/*.md               corpus seed notes; corpus embeddings rebuilt from these
├── Inbox/Papers/             daily digests, YYYY-MM-DD.md
├── Inbox/To Read.md          rolling Read later queue
└── .github/workflows/daily-digest.yml
\`\`\`

### State and persistence

The SQLite database is deliberately not committed (a tracked binary caused
push/pull merge failures). It is gitignored via `data/*.db` and rebuilt empty on
every scheduled run. Two committed text artifacts carry the state that must
survive across runs, both line-based and merge-friendly:

- **Corpus.** The seed papers live as committed Markdown notes in `Corpus/`.
  `python -m src.corpus from-notes` re-embeds them into the fresh database's
  corpus table at the start of each run, with no network. Rebuilding at runtime
  (rather than committing pre-baked vectors) keeps the corpus and the candidate
  papers embedded by the same model, so cosine scores stay consistent.
- **Dedup.** `data/seen_dois.txt` is the durable record of every DOI ever
  surfaced. `src.fetch` deduplicates against it (unioned with the database on a
  persistent local checkout), then writes the updated set back; the workflow
  commits it alongside the digests. Because the writer selects papers by
  `seen_date = today`, only the genuinely new papers inserted this run reach the
  digest. `python -m src.seen rebuild-from-notes` resyncs the list from the DOIs
  in `Inbox/Papers/*.md` after editing or regenerating digests by hand.

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
.venv\Scripts\python.exe -m src.corpus from-notes
.venv\Scripts\python.exe -m src.rank
.venv\Scripts\python.exe -m src.digest.writer .
.venv\Scripts\python.exe -m src.digest.to_read .
\`\`\`

`src.corpus from-notes` rebuilds the corpus table from the committed `Corpus/`
notes; it is required on a fresh database (such as a clean clone or any CI run)
and a fast no-op once the corpus is already embedded locally.

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