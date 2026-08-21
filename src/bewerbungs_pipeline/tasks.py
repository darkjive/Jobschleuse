"""Hintergrundläufe für langsame Aufrufe (LLM, Arbeitsagentur).

Bewusst minimal: der Zustand liegt im Speicher und überlebt keinen Neustart
der App. Für den Einzelbetrieb ist das ausreichend — persistente Queues wären
Infrastruktur ohne Gegenwert.
"""

import itertools
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bewerbung")
_lock = threading.Lock()
_tasks: dict[str, "Task"] = {}
_counter = itertools.count(1)


@dataclass
class Task:
    id: str
    beschreibung: str
    status: str = "läuft"  # "läuft" | "fertig" | "fehler"
    meldung: str = ""
    ergebnis: object | None = field(default=None)


def start(beschreibung: str, fn, *args, **kwargs) -> str:
    task_id = str(next(_counter))
    task = Task(id=task_id, beschreibung=beschreibung)
    with _lock:
        _tasks[task_id] = task

    def lauf() -> None:
        try:
            ergebnis = fn(*args, **kwargs)
        except Exception as exc:
            with _lock:
                task.status = "fehler"
                task.meldung = str(exc)
        else:
            with _lock:
                task.status = "fertig"
                task.ergebnis = ergebnis

    _executor.submit(lauf)
    return task_id


def get(task_id: str) -> Task | None:
    with _lock:
        task = _tasks.get(task_id)
        # Rückgabe einer Kopie verhindert Race Conditions:
        # Der Aufrufer sieht einen konsistenten Schnappschuss,
        # während der Hintergrund-Thread das Original weiter verändern kann.
        return replace(task) if task is not None else None


def shutdown() -> None:
    _executor.shutdown(wait=False)
