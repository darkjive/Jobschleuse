import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import db
from ..config import Config

HIER = Path(__file__).parent
templates = Jinja2Templates(directory=str(HIER / "templates"))

# Vite baut hierher (siehe frontend/vite.config.ts, base: '/app/'). Das
# Verzeichnis wird committed — kein Node zur Laufzeit nötig (siehe Spec).
FRONTEND_DIST = HIER.parent.parent.parent / "frontend" / "dist"


def _alter(wert: str | None) -> str | None:
    """ISO-Zeitstempel → 'heute' / 'vor 3 Tagen' / 'vor 5 Wochen'."""
    if not wert:
        return None
    try:
        zeitpunkt = datetime.fromisoformat(wert)
    except ValueError:
        return None
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=UTC)
    tage = (datetime.now(UTC) - zeitpunkt).days
    if tage <= 0:
        return "heute"
    if tage == 1:
        return "gestern"
    if tage < 14:
        return f"vor {tage} Tagen"
    return f"vor {tage // 7} Wochen"


templates.env.filters["alter"] = _alter


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
    from .routes import api_applications as api_applications_routen
    from .routes import api_jobs as api_jobs_routen
    from .routes import api_tasks as api_tasks_routen
    from .routes import applications as bewerbungs_routen
    from .routes import jobs as jobs_routen
    from .routes import tasks as tasks_routen

    app.include_router(jobs_routen.router)
    app.include_router(tasks_routen.router)
    app.include_router(bewerbungs_routen.router)
    app.include_router(api_jobs_routen.router)
    app.include_router(api_tasks_routen.router)
    app.include_router(api_applications_routen.router)

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request, "stellen.html", {})

    if FRONTEND_DIST.is_dir():
        dist_resolved = FRONTEND_DIST.resolve()

        @app.get("/app", include_in_schema=False)
        @app.get("/app/{pfad:path}", include_in_schema=False)
        def spa(pfad: str = "") -> FileResponse:
            """Liefert das React-Frontend; unbekannte Pfade gehen an React Router.

            `pfad` kommt aus der URL und könnte `../`-Sequenzen enthalten —
            `is_relative_to` verhindert, dass damit Dateien außerhalb von
            FRONTEND_DIST ausgelesen werden.
            """
            datei = (FRONTEND_DIST / pfad).resolve()
            if pfad and datei.is_relative_to(dist_resolved) and datei.is_file():
                return FileResponse(datei)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app
