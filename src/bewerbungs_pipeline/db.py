import hashlib
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from .models import JobItem

STATUSES = {"new", "selected", "rejected"}

SCHEMA_VERSION = 2

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
    status TEXT NOT NULL DEFAULT 'new',
    job_kind TEXT,
    employer_kind TEXT,
    source_partner TEXT,
    external_host TEXT,
    homeoffice TEXT,
    salary TEXT,
    contract TEXT,
    worktime TEXT,
    distance_km INTEGER,
    start_date TEXT,
    changed_at TEXT,
    street TEXT,
    plz TEXT,
    education TEXT,
    employer_hash TEXT,
    gone_at TEXT
)
"""

# Spalten, die Bestandsdatenbanken aus Schema-Version 1 nachgeruestet bekommen.
NEUE_SPALTEN_V2 = (
    ("job_kind", "TEXT"),
    ("employer_kind", "TEXT"),
    ("source_partner", "TEXT"),
    ("external_host", "TEXT"),
    ("homeoffice", "TEXT"),
    ("salary", "TEXT"),
    ("contract", "TEXT"),
    ("worktime", "TEXT"),
    ("distance_km", "INTEGER"),
    ("start_date", "TEXT"),
    ("changed_at", "TEXT"),
    ("street", "TEXT"),
    ("plz", "TEXT"),
    ("education", "TEXT"),
    ("employer_hash", "TEXT"),
    ("gone_at", "TEXT"),
)

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
    if version < 2:
        # Spaltenweise statt Tabellenneubau: die Bestandsdatenbank haengt an
        # Bewerbungen, die einen Fremdschluessel auf jobs.id halten.
        vorhanden = {
            zeile["name"] for zeile in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        for name, typ in NEUE_SPALTEN_V2:
            if name not in vorhanden:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {typ}")
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
            description_md, scraped_at, job_kind, employer_kind, source_partner,
            external_host, homeoffice, salary, contract, worktime, distance_km,
            start_date, changed_at, street, plz, education, employer_hash, gone_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            item.job_kind,
            item.employer_kind,
            item.source_partner,
            item.external_host,
            item.homeoffice,
            item.salary,
            item.contract,
            item.worktime,
            item.distance_km,
            item.start_date.isoformat() if item.start_date else None,
            item.changed_at.isoformat() if item.changed_at else None,
            item.street,
            item.plz,
            item.education,
            item.employer_hash,
            item.gone_at.isoformat() if item.gone_at else None,
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
    mit_verschwundenen: bool = False,
) -> list[sqlite3.Row]:
    """Stellenliste mit optionalen Filtern.

    `q` sucht in Titel und Firma, `ort` im Ort — beides ohne
    Beachtung der Groß-/Kleinschreibung. Stellen, deren Anzeige bei der
    Quelle verschwunden ist, bleiben aussen vor, solange
    `mit_verschwundenen` nicht gesetzt ist.
    """
    sql = "SELECT * FROM jobs WHERE 1=1"
    werte: list[str] = []
    if not mit_verschwundenen:
        sql += " AND gone_at IS NULL"
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


def offene_referenzen(conn: sqlite3.Connection) -> list[str]:
    """Referenznummern aller Stellen, die noch als verfügbar gelten."""
    zeilen = conn.execute(
        "SELECT source_ref FROM jobs"
        " WHERE source_ref IS NOT NULL AND gone_at IS NULL ORDER BY id"
    ).fetchall()
    return [zeile["source_ref"] for zeile in zeilen]


def mark_gone(conn: sqlite3.Connection, refnrs: set[str]) -> int:
    """Markiert die genannten Stellen als bei der Quelle verschwunden."""
    if not refnrs:
        return 0
    jetzt = datetime.now(UTC).isoformat()
    platzhalter = ",".join("?" * len(refnrs))
    cur = conn.execute(
        f"UPDATE jobs SET gone_at = ?"
        f" WHERE gone_at IS NULL AND source_ref IN ({platzhalter})",
        (jetzt, *sorted(refnrs)),
    )
    conn.commit()
    return cur.rowcount


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
        job_kind=row["job_kind"],
        employer_kind=row["employer_kind"],
        source_partner=row["source_partner"],
        external_host=row["external_host"],
        homeoffice=row["homeoffice"],
        salary=row["salary"],
        contract=row["contract"],
        worktime=row["worktime"],
        distance_km=row["distance_km"],
        start_date=date.fromisoformat(row["start_date"]) if row["start_date"] else None,
        changed_at=datetime.fromisoformat(row["changed_at"]) if row["changed_at"] else None,
        street=row["street"],
        plz=row["plz"],
        education=row["education"],
        employer_hash=row["employer_hash"],
        gone_at=datetime.fromisoformat(row["gone_at"]) if row["gone_at"] else None,
    )
