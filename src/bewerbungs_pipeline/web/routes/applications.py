import html
import re
import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from ... import applications, db, tasks
from ...applications import ApplicationError
from ...config import Config
from ...llm import make_client
from ..app import get_conn, templates

router = APIRouter()

_ASSET_RE = re.compile(r'(?P<attr>\b(?:href|src)=")(?P<pfad>(?!https?:|/|data:|#)[^"]+)"')


def pfade_umschreiben(quelltext: str) -> str:
    """Macht relative Vorlagen-Pfade im iframe auflösbar.

    Betrifft nur die Vorschau — die exportierte Datei in out/ bleibt
    unverändert, dort liegen styles.css und assets/ daneben.
    """
    return _ASSET_RE.sub(r'\g<attr>/template-assets/\g<pfad>"', quelltext)


def _fehler(meldung: object, status: int = 400) -> HTMLResponse:
    """Fehlerfragment mit maskiertem Text.

    Slot-Namen stammen aus dem Pfad und stecken in den Meldungen — roh
    eingesetzt landete fremdes Markup in der Seite.
    """
    return HTMLResponse(
        f'<p class="meldung meldung--fehler">{html.escape(str(meldung))}</p>',
        status_code=status,
    )


def _client(cfg: Config):
    if not (cfg.llm_base_url and cfg.llm_api_key and cfg.llm_model):
        raise ApplicationError("LLM_BASE_URL, LLM_API_KEY und LLM_MODEL in .env setzen.")
    return make_client(cfg.llm_base_url, cfg.llm_api_key)


def bewerbung_erzeugen(cfg: Config, job_id: int) -> int:
    """Hintergrund-Thread: eigene Verbindung, eigener Client."""
    conn = db.connect(cfg.db_path)
    try:
        return applications.create(conn, job_id, cfg, _client(cfg))
    finally:
        conn.close()


def exportieren_lauf(cfg: Config, app_id: int) -> str:
    """Hintergrund-Thread: eigene Verbindung.

    Der Export druckt das PDF über einen Browser und braucht dafür Sekunden —
    zu lang, um eine Anfrage darauf warten zu lassen.
    """
    conn = db.connect(cfg.db_path)
    try:
        ziel = applications.export(conn, app_id, cfg)
        return f"Exportiert nach {ziel}"
    finally:
        conn.close()


def slot_erzeugen(cfg: Config, app_id: int, slot: str) -> str:
    """Hintergrund-Thread: eigene Verbindung, eigener Client."""
    conn = db.connect(cfg.db_path)
    try:
        return applications.regenerate_slot(conn, app_id, slot, cfg, _client(cfg))
    finally:
        conn.close()


@router.post("/applications", response_class=HTMLResponse)
def erzeugen(request: Request, job_id: int = Form(...)):
    cfg = request.app.state.cfg
    task_id = tasks.start("Bewerbung wird geschrieben", bewerbung_erzeugen, cfg, job_id)
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {
            "task": tasks.get(task_id),
            # Nach dem Lauf das Stellendetail neu laden: dort steht dann der
            # Knopf „Bewerbung öffnen“ statt „Bewerbung erstellen“.
            "ziel": f"/jobs/{job_id}",
            "ziel_element": "#stellendetail",
        },
    )


@router.get("/bewerbung/{app_id}", response_class=HTMLResponse)
def seite(request: Request, app_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    bewerbung = applications.get(conn, app_id)
    if bewerbung is None:
        return _fehler("Bewerbung nicht gefunden.", 404)
    stelle = db.get_job(conn, bewerbung["job_id"])
    return templates.TemplateResponse(
        request,
        "bewerbung.html",
        {"bewerbung": bewerbung, "stelle": stelle, "app_id": app_id},
    )


@router.get("/applications/{app_id}/slots/{slot}", response_class=HTMLResponse)
def slot_fragment(
    request: Request,
    app_id: int,
    slot: str,
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Liefert einen einzelnen Block — damit ihn ein Hintergrundlauf nachladen kann."""
    bewerbung = applications.get(conn, app_id)
    if bewerbung is None:
        return _fehler("Bewerbung nicht gefunden.", 404)
    daten = bewerbung["slots"].get(slot)
    if daten is None:
        return _fehler(f"Unbekannter Slot: {slot}", 404)
    return templates.TemplateResponse(
        request, "_slot.html", {"name": slot, "daten": daten, "app_id": app_id}
    )


@router.put("/applications/{app_id}/slots/{slot}", response_class=HTMLResponse)
def slot_speichern(
    request: Request,
    app_id: int,
    slot: str,
    value: str = Form(...),
    conn: sqlite3.Connection = Depends(get_conn),
):
    try:
        applications.set_slot(conn, app_id, slot, value)
    except ApplicationError as exc:
        return _fehler(exc)
    daten = applications.get(conn, app_id)["slots"][slot]
    return templates.TemplateResponse(
        request, "_slot.html", {"name": slot, "daten": daten, "app_id": app_id}
    )


@router.post(
    "/applications/{app_id}/slots/{slot}/regenerate", response_class=HTMLResponse
)
def slot_neu(request: Request, app_id: int, slot: str):
    cfg = request.app.state.cfg
    task_id = tasks.start(
        f"Block „{slot}“ wird neu geschrieben", slot_erzeugen, cfg, app_id, slot
    )
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {
            "task": tasks.get(task_id),
            # Nach dem Lauf den Block selbst nachladen — sonst stünde im
            # Textfeld weiter der alte Stand.
            "ziel": f"/applications/{app_id}/slots/{slot}",
            "ziel_element": f"#slot-{slot}",
            "ziel_swap": "outerHTML",
        },
    )


@router.get("/applications/{app_id}/preview", response_class=HTMLResponse)
def vorschau(
    request: Request, app_id: int, conn: sqlite3.Connection = Depends(get_conn)
):
    cfg = request.app.state.cfg
    try:
        quelltext = applications.render(conn, app_id, cfg)
    except ApplicationError as exc:
        return _fehler(exc)
    return HTMLResponse(pfade_umschreiben(quelltext))


@router.post("/applications/{app_id}/export", response_class=HTMLResponse)
def exportieren(app_id: int, request: Request):
    cfg = request.app.state.cfg
    task_id = tasks.start("Bewerbung wird exportiert", exportieren_lauf, cfg, app_id)
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {"task": tasks.get(task_id), "ziel": "", "ziel_element": ""},
    )
