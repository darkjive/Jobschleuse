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

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request, "basis.html", {})

    return app
