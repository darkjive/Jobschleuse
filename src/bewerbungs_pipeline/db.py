import hashlib
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import JobItem

STATUSES = {"new", "selected", "generated", "rejected"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    dedupe_hash TEXT NOT NULL UNIQUE,
    source_ref TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    company_website TEXT,
    location TEXT NOT NULL,
    source TEXT NOT NULL,
    posted_at TEXT,
    contact_name TEXT,
    contact_email TEXT,
    description_md TEXT NOT NULL DEFAULT '',
    scraped_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'
)
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def dedupe_hash(item: JobItem) -> str:
    key = "|".join(s.strip().lower() for s in (item.company, item.title, item.location))
    return hashlib.sha256(key.encode()).hexdigest()


def insert_job(conn: sqlite3.Connection, item: JobItem) -> bool:
    cur = conn.execute(
        """INSERT OR IGNORE INTO jobs
           (url, dedupe_hash, source_ref, title, company, company_website,
            location, source, posted_at, contact_name, contact_email,
            description_md, scraped_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            item.url,
            dedupe_hash(item),
            item.source_ref,
            item.title,
            item.company,
            item.company_website,
            item.location,
            item.source,
            item.posted_at.isoformat() if item.posted_at else None,
            item.contact_name,
            item.contact_email,
            item.description_md,
            item.scraped_at.isoformat(),
        ),
    )
    conn.commit()
    return cur.rowcount == 1


def list_jobs(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status is not None:
        return conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY id", (status,)
        ).fetchall()
    return conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()


def get_job(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def set_status(conn: sqlite3.Connection, job_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Unbekannter Status: {status}")
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()


def update_description(conn: sqlite3.Connection, job_id: int, text: str) -> None:
    conn.execute("UPDATE jobs SET description_md = ? WHERE id = ?", (text, job_id))
    conn.commit()


def row_to_item(row: sqlite3.Row) -> JobItem:
    return JobItem(
        title=row["title"],
        company=row["company"],
        location=row["location"],
        url=row["url"],
        source=row["source"],
        source_ref=row["source_ref"],
        company_website=row["company_website"],
        posted_at=date.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
        contact_name=row["contact_name"],
        contact_email=row["contact_email"],
        description_md=row["description_md"],
        scraped_at=datetime.fromisoformat(row["scraped_at"]),
    )
