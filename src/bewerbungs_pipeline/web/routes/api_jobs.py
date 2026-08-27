import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ... import applications, db
from ..app import get_conn
from ..schemas import BulkStatusUpdate, JobOut, StatusUpdate, job_out

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
