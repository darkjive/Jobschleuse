import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ... import db
from ..app import get_conn, templates

router = APIRouter()


def _detail(request: Request, conn: sqlite3.Connection, job_id: int) -> HTMLResponse:
    stelle = db.get_job(conn, job_id)
    if stelle is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Stelle nicht gefunden.</p>',
            status_code=404,
        )
    return templates.TemplateResponse(request, "_stellendetail.html", {"stelle": stelle})


@router.get("/jobs", response_class=HTMLResponse)
def liste(
    request: Request,
    status: str = "",
    q: str = "",
    ort: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
):
    stellen = db.suche_jobs(conn, status=status or None, q=q or None, ort=ort or None)
    return templates.TemplateResponse(request, "_stellenliste.html", {"stellen": stellen})


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def detail(request: Request, job_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    return _detail(request, conn, job_id)


@router.post("/jobs/{job_id}/pick", response_class=HTMLResponse)
def pick(request: Request, job_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    if db.get_job(conn, job_id) is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Stelle nicht gefunden.</p>',
            status_code=404,
        )
    db.set_status(conn, job_id, "selected")
    return _detail(request, conn, job_id)


@router.post("/jobs/{job_id}/reject", response_class=HTMLResponse)
def reject(request: Request, job_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    if db.get_job(conn, job_id) is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Stelle nicht gefunden.</p>',
            status_code=404,
        )
    db.set_status(conn, job_id, "rejected")
    return _detail(request, conn, job_id)
