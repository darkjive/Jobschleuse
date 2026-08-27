from fastapi import APIRouter, HTTPException

from ... import tasks as tasks_modul
from ..schemas import TaskOut

router = APIRouter(prefix="/api")


@router.get("/tasks/{task_id}")
def status(task_id: str) -> TaskOut:
    task = tasks_modul.get(task_id)
    if task is None:
        raise HTTPException(404, "Vorgang nicht gefunden.")
    return TaskOut.model_validate(task)
