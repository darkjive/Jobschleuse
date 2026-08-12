import hashlib
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import JobItem

STATUSES = {"new", "selected", "rejected"}

SCHEMA_VERSION = 1

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

SCHEMA_APPLICATIONS = """
CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER NOT NULL REFERENCES jobs(id),
    template_path TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(job_id)
)
"""

SCHEMA_APPLICATION_SLOTS = """
CREATE TABLE IF NOT EXISTS application_slots (
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    slot           TEXT NOT NULL,
    value          TEXT NOT NULL,
    source         TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (application_id, slot)
)
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Führt Schemaschritte aus, die über CREATE TABLE hinausgehen."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        conn.execute("UPDATE jobs SET status = 'selected' WHERE status = 'generated'")
    if version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False, weil FastAPI die Verbindung einer Anfrage in
    # einem Arbeits-Thread öffnet und in einem anderen wieder schließt.
    # Ungefährlich: jede Anfrage und jeder Hintergrundlauf bekommt eine eigene
    # Verbindung, geteilt wird keine.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(SCHEMA)
    conn.execute(SCHEMA_APPLICATIONS)
    conn.execute(SCHEMA_APPLICATION_SLOTS)
    _migrate(conn)
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


def suche_jobs(
    conn: sqlite3.Connection,
    status: str | None = None,
    q: str | None = None,
    ort: str | None = None,
) -> list[sqlite3.Row]:
    """Stellenliste mit optionalen Filtern.

    `q` sucht in Titel und Firma, `ort` im Ort — beides ohne
    Beachtung der Groß-/Kleinschreibung.
    """
    sql = "SELECT * FROM jobs WHERE 1=1"
    werte: list[str] = []
    if status:
        sql += " AND status = ?"
        werte.append(status)
    if q:
        sql += " AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ?)"
        werte.extend([f"%{q.lower()}%"] * 2)
    if ort:
        sql += " AND LOWER(location) LIKE ?"
        werte.append(f"%{ort.lower()}%")
    sql += " ORDER BY id DESC"
    return conn.execute(sql, werte).fetchall()


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
