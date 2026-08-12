import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import db
from ..config import Config

HIER = Path(__file__).parent
templates = Jinja2Templates(directory=str(HIER / "templates"))


def get_conn(request: Request) -> sqlite3.Connection:
    """Eine eigene Verbindung pro Anfrage — SQLite ist nicht thread-sicher.

    Generator-Dependency: FastAPI schließt die Verbindung nach der Antwort.
    """
    conn = db.connect(request.app.state.cfg.db_path)
    try:
        yield conn
    finally:
        conn.close()


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="Bewerbungs-App")
    app.state.cfg = cfg
    app.mount("/static", StaticFiles(directory=str(HIER / "static")), name="static")

    vorlagen_ordner = cfg.template_path.parent
    if vorlagen_ordner.is_dir():
        app.mount(
            "/template-assets",
            StaticFiles(directory=str(vorlagen_ordner)),
            name="template-assets",
        )

    # Erst hier importieren: routes/jobs.py greift auf get_conn und templates
    # aus diesem Modul zu — ein Import auf Modulebene wäre zirkulär.
    from .routes import applications as bewerbungs_routen
    from .routes import jobs as jobs_routen
    from .routes import tasks as tasks_routen

    app.include_router(jobs_routen.router)
    app.include_router(tasks_routen.router)
    app.include_router(bewerbungs_routen.router)

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request, "stellen.html", {})

    return app
