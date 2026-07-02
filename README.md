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
3. **Rank.** Each paper is scored as the mean of its top 3 cosine similarities
   against a corpus of seed papers representing the research interests of the
   maintainer. Papers are sorted into three tiers (must-read, skim, archive)
   using thresholds recalibrated every run from the corpus's own leave-one-out
   similarity distribution (90th and 50th percentiles), so tiering adapts as
   the corpus grows with no manual re-check. The corpus embeddings are rebuilt
   from committed Markdown notes at the start of each run, so ranking works
   even though the database itself is not persisted.
4. **Deliver.** A Markdown digest is written to the Obsidian vault at
   `Inbox/Papers/YYYY-MM-DD.md`, with each tier in its own callout block. Must-read
   and skim papers each carry two independent checkboxes (`Relevant` feeds the
   corpus feedback loop; `Read later` queues the paper for offline review) plus
   a `Nearest seed` line naming the corpus paper that drove the score. A
   Wildcard section promotes two randomly sampled archive papers to full
   rendering with checkboxes, giving the corpus a path to papers the ranker
   scores low (filter-bubble mitigation).
5. **Learn.** The feedback loop scans recent digests for checked `Relevant`
   boxes and writes each as a corpus seed note, fully offline (the digest block
   already carries title and abstract). The next run embeds the new notes, so
   the complete loop is: tick the box in Obsidian, push. `src.digest.to_read`
   likewise collects checked `Read later` boxes into `Inbox/To Read.md`. Both
   are idempotent, deduplicated by DOI.
6. **Assemble.** After each ISO week completes, a column packet is written to
   `Inbox/Column/YYYY-Www.md`: the week's must-reads plus every ticked paper,
   deduplicated, as prep material for the weekly column.
7. **Schedule.** A GitHub Actions workflow runs the pipeline daily and commits
   the digests, the corpus notes, the queues, the dedup list, and a one-line
   metrics record per run (`data/metrics.txt`: counts per tier plus the
   calibrated thresholds, for drift monitoring). The SQLite database is not
   committed; it is rebuilt from committed text each run (see State and
   persistence).

## Status

Operational since May 2026. Scheduling, persistence, the Read later queue, an
expanded source list (17 Crossref journals plus a broadened PubMed query), the
corpus feedback loop, self-calibrating tier thresholds, the weekly column
packet, and run telemetry are complete (feedback loop and calibration added
2026-07-02).

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
│   ├── db.py                 SQLite schema, migrations, meta key-value table
│   ├── metrics.py            per-run telemetry line into data/metrics.txt
│   ├── fetchers/             pubmed.py, journals.py
│   ├── ranking/              embed.py, score.py (top-3 mean + self-calibration)
│   └── digest/
│       ├── writer.py         Markdown digest generator (checkboxes, wildcard)
│       ├── blocks.py         shared digest-block parser (single contract)
│       ├── to_read.py        Read later queue scanner
│       ├── feedback.py       Relevant ticks -> Corpus/ seed notes
│       └── column.py         weekly column packet builder
├── tests/                    digest-side unit tests (unittest)
├── data/papers.db            SQLite, gitignored, rebuilt empty each run
├── data/seen_dois.txt        durable dedup list (every DOI surfaced), committed
├── data/metrics.txt          one line per run: counts per tier + thresholds
├── Corpus/seed_dois.txt      curated DOIs defining "relevant"
├── Corpus/*.md               corpus seed notes; corpus embeddings rebuilt from
│                             these; the feedback loop appends here
├── Inbox/Papers/             daily digests, YYYY-MM-DD.md
├── Inbox/To Read.md          rolling Read later queue
├── Inbox/Column/             weekly column packets, YYYY-Www.md
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
.venv\Scripts\python.exe -m src.digest.feedback .
.venv\Scripts\python.exe -m src.corpus from-notes
.venv\Scripts\python.exe -m src.rank
.venv\Scripts\python.exe -m src.digest.writer .
.venv\Scripts\python.exe -m src.digest.to_read .
.venv\Scripts\python.exe -m src.digest.column .
.venv\Scripts\python.exe -m src.metrics
\`\`\`

Tests: `python -m unittest discover -s tests -t .` (digest side) and
`python -m unittest discover -s lineage/tests -t .` (lineage).

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
fixed thresholds do not generalize. Since 2026-07-02 thresholds self-calibrate
every run: each corpus paper is scored against the rest with the same top-3
mean statistic used for candidates, and the must-read/skim cuts are the 90th
and 50th percentiles of that leave-one-out distribution. The values are logged
per run in `data/metrics.txt`; watch that file for tier drift instead of
re-checking thresholds by hand. Fixed fallbacks apply only below 5 corpus
papers.

### Known limitations

- Corpus is provisional (~40 DOIs). Ranking improves as the feedback loop
  grows it; only new-format digests (2026-07-02 onward) feed the loop.
- Broad-journal Crossref pulls are unfiltered, so the archive tier carries
  significant off-topic volume until the planned keyword prefilter lands.
- Preprint servers (bioRxiv, medRxiv) not yet integrated.
- The system is single-user. No multi-user or sharing primitives.

---

## Lineage module

A separate tool from the digest, fully decoupled from it (no shared code, no
shared database, no overlapping output). Given one or more seed DOIs on a
topic, it reconstructs the topic's citation story: it walks backward through
references via OpenAlex, optionally merges the trees of sibling seeds, walks
forward to the works citing the groundwork, and renders into the Obsidian
vault under `Inbox/Lineages/`:

- a deterministic chart-everything note per seed (Mermaid flowchart plus
  bulleted trajectory), the raw record;
- a curated, decade-grouped timeline of the ~15 to 20 groundwork papers,
  selected by a Claude session and narrated; and
- a topic dossier (2026-07-02): narrative arc, decade-grouped main studies,
  a consensus chart of ancestors shared across seed trees (in-degree >= 2,
  the honest structural "main study" signal a single capped tree cannot
  provide), a frontier section of recent citing works (the backward walk
  cannot see past the seed), and coverage gaps.

Selection uses a deliberate manual-paste transport: the module makes no API call
and adds no network dependency. It emits a pasteable prompt, you paste it into a
Claude session, and you paste the reply back for validation. An anti-hallucination
validator keeps only paper ids that exist in the crawl; every citation fact in
the rendered note comes from the crawl by id, never from the pasted text.

### End-to-end run for one seed

OpenAlex is reached only by the crawl, which runs on the laptop (not in CI). The
remaining steps are offline. The example uses a scratch reply file `reply.json`;
delete it after ingesting.

\`\`\`
# 1. Crawl: resolve the seed, walk references, write runs/{run_id}.json
.venv\Scripts\python.exe -m lineage.traverse <seed_doi>

# 2. Select: print the pasteable payload to a file (UTF-8 is automatic)
.venv\Scripts\python.exe -m lineage.select runs/<run_id>.json > payload.txt

# 3. Paste payload.txt into a Claude session; save the fenced JSON reply
#    to reply.json (the {narrative, coverage_gaps, selections} object).

# 4. Ingest: validate the reply and write runs/<run_id>.selection.json
.venv\Scripts\python.exe -m lineage.select ingest runs/<run_id>.json reply.json

# 5. Render the curated timeline to Inbox/Lineages/{slug}-{date}-selected.md
.venv\Scripts\python.exe -m lineage.timeline runs/<run_id>.json .

# 6. Read the note in Inbox/Lineages, then delete the scratch reply
rm reply.json payload.txt
\`\`\`

`run_id` is the seed DOI slugified plus the date (printed by step 1). The crawl
run file is immutable: selection is cached to a separate `.selection.json`
sidecar, so re-selecting (re-running steps 2 to 4) overwrites only the sidecar
and never touches the crawl. Both the timeline and the deterministic
chart-everything note (`python -m lineage.render runs/<run_id>.json .`) refuse to
overwrite an existing note without `--force`.

### Topic dossier for multiple seeds

\`\`\`
# 1. Crawl 2 or 3 sibling seeds (recent reviews on the topic)
.venv\Scripts\python.exe -m lineage.traverse <seed_doi_a>
.venv\Scripts\python.exe -m lineage.traverse <seed_doi_b>

# 2. Merge the trees; shared ancestors gain real in-degree and a seed_count
.venv\Scripts\python.exe -m lineage.merge "<topic>" runs/<a>.json runs/<b>.json

# 3. Select groundwork on the merged run (same paste flow as above)
.venv\Scripts\python.exe -m lineage.select runs/<merged>.json > payload.txt
.venv\Scripts\python.exe -m lineage.select ingest runs/<merged>.json reply.json

# 4. Forward walk: works citing the seed and the selected groundwork
.venv\Scripts\python.exe -m lineage.forward runs/<merged>.json

# 5. Render the dossier to Inbox/Lineages/<merged-run-id>-dossier.md
.venv\Scripts\python.exe -m lineage.dossier runs/<merged>.json .
\`\`\`

Every step also works on a single-seed run (merge is optional). The forward
walk writes a `.forward.json` sidecar; source crawls are never mutated.