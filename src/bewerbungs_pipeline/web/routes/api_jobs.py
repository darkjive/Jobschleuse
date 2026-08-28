import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ... import applications, db, tasks
from ...config import Config
from ...sources import arbeitsagentur, indeed
from ..app import get_conn
from ..schemas import (
    BulkStatusUpdate,
    FetchRequest,
    JobOut,
    StatusUpdate,
    TaskRef,
    job_out,
)

router = APIRouter(prefix="/api")


@router.get("/jobs")
def liste(
    status: str = "",
    q: str = "",
    ort: str = "",
    verschwunden: str = "",
    sort: str = "id",
    order: str = "desc",
    limit: int | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[JobOut]:
    stellen = db.suche_jobs(
        conn,
        status=status or None,
        q=q or None,
        ort=ort or None,
        mit_verschwundenen=bool(verschwunden),
        sort=sort,
        order=order,
    )
    if limit is not None:
        stellen = stellen[:limit]
    return [job_out(row) for row in stellen]


@router.get("/jobs/{job_id}")
def detail(job_id: int, conn: sqlite3.Connection = Depends(get_conn)) -> JobOut:
    row = db.get_job(conn, job_id)
    if row is None:
        raise HTTPException(404, "Stelle nicht gefunden.")
    bewerbung = applications.get_by_job(conn, job_id)
    return job_out(row, application_id=bewerbung["id"] if bewerbung else None)


@router.post("/jobs/{job_id}/status")
def status_setzen(
    job_id: int, body: StatusUpdate, conn: sqlite3.Connection = Depends(get_conn)
) -> JobOut:
    if db.get_job(conn, job_id) is None:
        raise HTTPException(404, "Stelle nicht gefunden.")
    db.set_status(conn, job_id, body.status)
    return job_out(db.get_job(conn, job_id))


@router.post("/jobs/status")
def status_bulk(
    body: BulkStatusUpdate, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, int]:
    return {"aktualisiert": db.set_status_bulk(conn, body.ids, body.status)}


def suche_ausfuehren(
    cfg: Config,
    was: str,
    wo: str,
    umkreis: int,
    veroeffentlicht_seit: int | None,
    ohne_zeitarbeit: bool,
    nur_arbeit: bool,
) -> str:
    """Läuft im Hintergrund-Thread — öffnet deshalb eine eigene Verbindung."""
    items = arbeitsagentur.fetch_jobs(
        was=was,
        wo=wo,
        umkreis=umkreis,
        veroeffentlicht_seit=veroeffentlicht_seit,
        ohne_zeitarbeit=ohne_zeitarbeit,
        nur_arbeit=nur_arbeit,
    )
    conn = db.connect(cfg.db_path)
    try:
        neu = sum(1 for item in items if db.insert_job(conn, item))
        # Bei der Gelegenheit den Bestand nachziehen: derselbe Abruf, der
        # gerade neue Treffer geprueft hat, taugt auch fuer die alten.
        weg = db.mark_gone(conn, arbeitsagentur.check_alive(db.offene_referenzen(conn)))
    finally:
        conn.close()
    return f"{len(items)} Stellen geholt, {neu} neu, {weg} nicht mehr verfügbar."


def suche_indeed_ausfuehren(
    cfg: Config,
    was: str,
    wo: str,
    umkreis: int,
    seit_tage: int | None,
) -> str:
    """Läuft im Hintergrund-Thread — öffnet deshalb eine eigene Verbindung."""
    items = indeed.fetch_jobs(
        was=was,
        wo=wo,
        umkreis=umkreis,
        seit_stunden=seit_tage * 24 if seit_tage is not None else None,
    )
    conn = db.connect(cfg.db_path)
    try:
        neu = sum(1 for item in items if db.insert_job(conn, item))
    finally:
        conn.close()
    return f"{len(items)} Stellen geholt, {neu} neu."


@router.post("/jobs/fetch")
def fetch(body: FetchRequest, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    if body.quelle == "indeed":
        task_id = tasks.start(
            f"Indeed-Suche „{body.was}“ in {body.wo}",
            suche_indeed_ausfuehren,
            cfg,
            body.was,
            body.wo,
            body.umkreis,
            body.seit,
        )
    else:
        task_id = tasks.start(
            f"Suche „{body.was}“ in {body.wo}",
            suche_ausfuehren,
            cfg,
            body.was,
            body.wo,
            body.umkreis,
            body.seit,
            body.ohne_zeitarbeit,
            body.nur_arbeit,
        )
    return TaskRef(task_id=task_id)
