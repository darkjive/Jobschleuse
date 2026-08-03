from pathlib import Path

from . import applications
from .applications import ApplicationError, slugify  # noqa: F401  (Re-Export fürs CLI)
from .config import Config


def generate_application(conn, job_id: int, cfg: Config, client) -> Path:
    """Fassade fürs CLI: Bewerbung erzeugen und sofort exportieren."""
    try:
        app_id = applications.create(conn, job_id, cfg, client)
        return applications.export(conn, app_id, cfg)
    except ApplicationError as exc:
        raise SystemExit(str(exc)) from exc
