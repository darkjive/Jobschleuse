import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ... import applications, db, tasks
from ...applications import ApplicationError
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
from .applications import bewerbung_erzeugen, exportieren_lauf, slot_erzeugen

router = APIRouter(prefix="/api")


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
