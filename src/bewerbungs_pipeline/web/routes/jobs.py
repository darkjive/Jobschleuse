import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from ... import applications, db, tasks
from ...config import Config
from ...sources import arbeitsagentur
from ..app import get_conn, templates

router = APIRouter()


def _detail(request: Request, conn: sqlite3.Connection, job_id: int) -> HTMLResponse:
    stelle = db.get_job(conn, job_id)
    if stelle is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Stelle nicht gefunden.</p>',
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "_stellendetail.html",
        {"stelle": stelle, "bewerbung": applications.get_by_job(conn, job_id)},
    )


@router.get("/jobs", response_class=HTMLResponse)
def liste(
    request: Request,
    status: str = "",
    q: str = "",
    ort: str = "",
    verschwunden: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
):
    stellen = db.suche_jobs(
        conn,
        status=status or None,
        q=q or None,
        ort=ort or None,
        mit_verschwundenen=bool(verschwunden),
    )
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


@router.post("/jobs/fetch", response_class=HTMLResponse)
def fetch(
    request: Request,
    was: str = Form(...),
    wo: str = Form(...),
    umkreis: int = Form(25),
    seit: str = Form(""),
    ohne_zeitarbeit: str = Form(""),
    nur_arbeit: str = Form(""),
):
    cfg = request.app.state.cfg
    task_id = tasks.start(
        f"Suche „{was}“ in {wo}",
        suche_ausfuehren,
        cfg,
        was,
        wo,
        umkreis,
        int(seit) if seit else None,
        bool(ohne_zeitarbeit),
        bool(nur_arbeit),
    )
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {
            "task": tasks.get(task_id),
            "ziel": "/jobs?status=new",
            "ziel_element": "#stellenliste",
        },
    )
