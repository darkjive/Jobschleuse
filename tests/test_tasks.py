import time

from bewerbungs_pipeline import tasks


def _warte_auf_ende(task_id: str, timeout: float = 5.0) -> tasks.Task:
    frist = time.monotonic() + timeout
    while time.monotonic() < frist:
        task = tasks.get(task_id)
        if task is not None and task.status != "läuft":
            return task
        time.sleep(0.01)
    raise AssertionError(f"Task {task_id} wurde nicht fertig")


def test_start_runs_function_and_stores_result():
    task_id = tasks.start("Testlauf", lambda a, b: a + b, 2, 3)
    task = _warte_auf_ende(task_id)
    assert task.status == "fertig"
    assert task.ergebnis == 5


def test_failing_function_is_reported_as_error():
    def kaputt():
        raise ValueError("etwas ging schief")

    task_id = tasks.start("Testlauf", kaputt)
    task = _warte_auf_ende(task_id)
    assert task.status == "fehler"
    assert "etwas ging schief" in task.meldung


def test_get_unknown_task_returns_none():
    assert tasks.get("gibtsnicht") is None


def test_beschreibung_is_kept():
    task_id = tasks.start("Stellen werden gesucht", lambda: None)
    _warte_auf_ende(task_id)
    assert tasks.get(task_id).beschreibung == "Stellen werden gesucht"
