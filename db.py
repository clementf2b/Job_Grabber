"""
SQLite persistence layer for JobGrab.

Schema
------
jobs(
  url         TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  company     TEXT NOT NULL,
  location    TEXT,
  source      TEXT,
  description TEXT,
  salary      TEXT,
  job_type    TEXT,
  posted_at   TEXT,
  scraped_at  TEXT
)
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from models import Job

DB_PATH = Path("jobs.db")

_CREATE = """
CREATE TABLE IF NOT EXISTS jobs (
    url         TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    company     TEXT NOT NULL,
    location    TEXT,
    source      TEXT,
    description TEXT,
    salary      TEXT,
    job_type    TEXT,
    posted_at   TEXT,
    scraped_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_source    ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped   ON jobs(scraped_at);
CREATE INDEX IF NOT EXISTS idx_jobs_posted    ON jobs(posted_at);
"""

_COLS = ("url", "title", "company", "location", "source",
         "description", "salary", "job_type", "posted_at", "scraped_at")


def init_db() -> None:
    """Create the jobs table (and indexes) if they don't exist yet."""
    with _conn() as con:
        con.executescript(_CREATE)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")   # safe concurrent reads
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def upsert_jobs(jobs: list[Job]) -> int:
    """
    Insert or replace a list of Job objects.
    Returns the number of rows affected.
    """
    rows = [
        (j.url or f"__no_url__{j.title}|{j.company}",
         j.title, j.company, j.location, j.source,
         j.description, j.salary, j.job_type, j.posted_at, j.scraped_at)
        for j in jobs
    ]
    sql = f"""
        INSERT OR REPLACE INTO jobs ({', '.join(_COLS)})
        VALUES ({', '.join(['?'] * len(_COLS))})
    """
    with _conn() as con:
        cur = con.executemany(sql, rows)
        return cur.rowcount


def load_jobs(source: str | None = None, limit: int = 0) -> list[dict]:
    """
    Return all jobs as dicts, optionally filtered by source.
    Ordered newest scraped_at first.
    """
    where = "WHERE source = ?" if source else ""
    params: tuple = (source,) if source else ()
    lim = f"LIMIT {limit}" if limit > 0 else ""
    sql = f"SELECT * FROM jobs {where} ORDER BY scraped_at DESC {lim}"
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def count_jobs(source: str | None = None) -> int:
    """Return the total number of stored jobs."""
    where = "WHERE source = ?" if source else ""
    params: tuple = (source,) if source else ()
    with _conn() as con:
        return con.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]


def clear_jobs() -> None:
    """Delete all rows (used before a full re-scrape if desired)."""
    with _conn() as con:
        con.execute("DELETE FROM jobs")
