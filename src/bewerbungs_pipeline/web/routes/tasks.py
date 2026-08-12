import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ... import tasks as tasks_modul
from ..app import templates

router = APIRouter()

# ziel und ziel_element durchlaufen den Browser, obwohl nur die App selbst sie
# setzt. Was nicht wie ein eigener Pfad bzw. eine eigene Element-Id aussieht,
# wird verworfen: sonst ließe sich das Fragment dazu bringen, fremdes HTML
# nachzuladen und in die Seite zu setzen — htmx führt darin auch Skripte aus.
ZIEL_ELEMENT = re.compile(r"#[A-Za-z0-9_-]+")


def _sicheres_ziel(ziel: str) -> str:
    return ziel if ziel.startswith("/") and not ziel.startswith("//") else ""


def _sicheres_ziel_element(ziel_element: str) -> str:
    return ziel_element if ZIEL_ELEMENT.fullmatch(ziel_element) else ""


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
def status(request: Request, task_id: str, ziel: str = "", ziel_element: str = ""):
    task = tasks_modul.get(task_id)
    if task is None:
        return HTMLResponse(
            '<p class="meldung meldung--fehler">Vorgang nicht gefunden.</p>',
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "_fortschritt.html",
        {
            "task": task,
            "ziel": _sicheres_ziel(ziel),
            "ziel_element": _sicheres_ziel_element(ziel_element),
        },
    )
