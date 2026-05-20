import json
import sqlite3
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    doi                  TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    authors              TEXT NOT NULL,
    corresponding_author TEXT,
    journal              TEXT NOT NULL,
    pub_date             TEXT NOT NULL,
    abstract             TEXT,
    source               TEXT NOT NULL,
    embedding            BLOB,
    similarity_score     REAL,
    matching_corpus_doi  TEXT,
    tier                 TEXT,
    seen_date            TEXT NOT NULL,
    relevance_status     TEXT
);

CREATE TABLE IF NOT EXISTS corpus (
    doi        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    abstract   TEXT,
    embedding  BLOB NOT NULL,
    added_date TEXT NOT NULL
);
"""


def migrate(db_path: str) -> None:
    """Create tables if they do not exist."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)


def migrate_embedding_columns(db_path: str) -> None:
    """Add embedding-related columns to papers and corpus tables idempotently."""
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        if "corpus" not in tables:
            conn.execute(
                """
                CREATE TABLE corpus (
                    doi        TEXT PRIMARY KEY,
                    title      TEXT NOT NULL,
                    abstract   TEXT,
                    embedding  BLOB NOT NULL,
                    added_date TEXT NOT NULL
                )
                """
            )

        papers_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(papers)").fetchall()
        }
        corpus_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(corpus)").fetchall()
        }

        for col, typedef in [
            ("embedding", "BLOB"),
            ("similarity_score", "REAL"),
            ("matching_corpus_doi", "TEXT"),
            ("tier", "TEXT"),
        ]:
            if col not in papers_cols:
                conn.execute(f"ALTER TABLE papers ADD COLUMN {col} {typedef}")

        if "abstract" not in corpus_cols:
            conn.execute("ALTER TABLE corpus ADD COLUMN abstract TEXT")


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_existing_dois(conn: sqlite3.Connection) -> set[str]:
    """Return all DOIs already in the papers table."""
    rows = conn.execute("SELECT doi FROM papers").fetchall()
    return {row["doi"] for row in rows}


def insert_paper(conn: sqlite3.Connection, paper: dict) -> None:
    """Insert a paper dict into papers; skips silently if DOI already exists."""
    conn.execute(
        """
        INSERT OR IGNORE INTO papers
            (doi, title, authors, corresponding_author, journal,
             pub_date, abstract, source, seen_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            paper["doi"],
            paper["title"],
            json.dumps(paper["authors"]),
            paper.get("corresponding_author"),
            paper["journal"],
            paper["pub_date"],
            paper.get("abstract"),
            paper["source"],
            date.today().isoformat(),
        ),
    )
