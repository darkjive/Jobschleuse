from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ... import tasks as tasks_modul
from ..app import templates

router = APIRouter()


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
        {"task": task, "ziel": ziel, "ziel_element": ziel_element},
    )
