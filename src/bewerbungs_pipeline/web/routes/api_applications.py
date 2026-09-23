import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ... import applications, db, tasks
from ...applications import ApplicationError
from ...config import Config
from ...llm import client_aus_config
from ..app import get_conn
from ..schemas import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationOut,
    SlotOut,
    SlotValue,
    TaskRef,
    job_out,
)

router = APIRouter(prefix="/api")


def bewerbung_erzeugen(cfg: Config, job_id: int) -> int:
    """Hintergrund-Thread: eigene Verbindung, eigener Client."""
    conn = db.connect(cfg.db_path)
    try:
        return applications.create(conn, job_id, cfg, client_aus_config(cfg))
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
        return applications.regenerate_slot(conn, app_id, slot, cfg, client_aus_config(cfg))
    finally:
        conn.close()


@router.post("/applications")
def erzeugen(body: ApplicationCreate, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    task_id = tasks.start(
        "Bewerbung wird geschrieben", bewerbung_erzeugen, cfg, body.job_id
    )
    return TaskRef(task_id=task_id)


@router.get("/applications/{app_id}")
def seite(
    app_id: int, conn: sqlite3.Connection = Depends(get_conn)
) -> ApplicationDetail:
    bewerbung = applications.get(conn, app_id)
    if bewerbung is None:
        raise HTTPException(404, "Bewerbung nicht gefunden.")
    stelle = db.get_job(conn, bewerbung["job_id"])
    return ApplicationDetail(
        application=ApplicationOut.model_validate(bewerbung), stelle=job_out(stelle)
    )


@router.get("/applications/{app_id}/slots/{slot}")
def slot_fragment(
    app_id: int, slot: str, conn: sqlite3.Connection = Depends(get_conn)
) -> SlotOut:
    bewerbung = applications.get(conn, app_id)
    if bewerbung is None:
        raise HTTPException(404, "Bewerbung nicht gefunden.")
    daten = bewerbung["slots"].get(slot)
    if daten is None:
        raise HTTPException(404, f"Unbekannter Slot: {slot}")
    return SlotOut.model_validate(daten)


@router.put("/applications/{app_id}/slots/{slot}")
def slot_speichern(
    app_id: int,
    slot: str,
    body: SlotValue,
    conn: sqlite3.Connection = Depends(get_conn),
) -> SlotOut:
    try:
        applications.set_slot(conn, app_id, slot, body.value)
    except ApplicationError as exc:
        raise HTTPException(400, str(exc)) from exc
    daten = applications.get(conn, app_id)["slots"][slot]
    return SlotOut.model_validate(daten)


@router.post("/applications/{app_id}/slots/{slot}/regenerate")
def slot_neu(app_id: int, slot: str, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    task_id = tasks.start(
        f"Block „{slot}“ wird neu geschrieben", slot_erzeugen, cfg, app_id, slot
    )
    return TaskRef(task_id=task_id)


@router.post("/applications/{app_id}/export")
def exportieren(app_id: int, request: Request) -> TaskRef:
    cfg = request.app.state.cfg
    task_id = tasks.start("Bewerbung wird exportiert", exportieren_lauf, cfg, app_id)
    return TaskRef(task_id=task_id)
