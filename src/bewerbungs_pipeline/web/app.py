import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import db
from ..config import Config

HIER = Path(__file__).parent

# Vite baut hierher (siehe frontend/vite.config.ts, base: '/'). Das
# Verzeichnis wird committed — kein Node zur Laufzeit nötig (siehe Spec).
FRONTEND_DIST = HIER.parent.parent.parent / "frontend" / "dist"


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

    vorlagen_ordner = cfg.template_path.parent
    if vorlagen_ordner.is_dir():
        app.mount(
            "/template-assets",
            StaticFiles(directory=str(vorlagen_ordner)),
            name="template-assets",
        )

    # Erst hier importieren: die Module greifen auf get_conn aus diesem
    # Modul zu — ein Import auf Modulebene wäre zirkulär.
    from .routes import api_applications as api_applications_routen
    from .routes import api_jobs as api_jobs_routen
    from .routes import api_tasks as api_tasks_routen
    from .routes import preview as preview_routen

    app.include_router(api_jobs_routen.router)
    app.include_router(api_tasks_routen.router)
    app.include_router(api_applications_routen.router)
    app.include_router(preview_routen.router)

    if FRONTEND_DIST.is_dir():
        dist_resolved = FRONTEND_DIST.resolve()

        @app.get("/", include_in_schema=False)
        @app.get("/{pfad:path}", include_in_schema=False)
        def spa(pfad: str = "") -> FileResponse:
            """Liefert das React-Frontend; unbekannte Pfade gehen an React Router.

            `pfad` kommt aus der URL und könnte `../`-Sequenzen enthalten —
            `is_relative_to` verhindert, dass damit Dateien außerhalb von
            FRONTEND_DIST ausgelesen werden. Muss nach allen anderen Routen
            registriert werden, sonst verschluckt der Catch-all die echten
            Endpunkte (/api/*, /applications/*/preview, /template-assets/*).
            """
            datei = (FRONTEND_DIST / pfad).resolve()
            if pfad and datei.is_relative_to(dist_resolved) and datei.is_file():
                return FileResponse(datei)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app
