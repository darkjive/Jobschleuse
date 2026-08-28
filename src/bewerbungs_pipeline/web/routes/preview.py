import html
import re
import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from ... import applications
from ...applications import ApplicationError
from ..app import get_conn

router = APIRouter()

_ASSET_RE = re.compile(
    r'(?P<attr>\b(?:href|src)=")(?P<pfad>(?!https?:|/|data:|#)[^"]+)"'
)


def pfade_umschreiben(quelltext: str) -> str:
    """Macht relative Vorlagen-Pfade im iframe auflösbar.

    Betrifft nur die Vorschau — die exportierte Datei in out/ bleibt
    unverändert, dort liegen styles.css und assets/ daneben.
    """
    return _ASSET_RE.sub(r'\g<attr>/template-assets/\g<pfad>"', quelltext)


def _fehler(meldung: object, status: int = 400) -> HTMLResponse:
    """Fehlerfragment mit maskiertem Text — hier landet z. B. eine fehlende
    Vorlage oder ein fehlendes Profil, beides kann Nutzertext enthalten."""
    return HTMLResponse(
        f'<p class="meldung meldung--fehler">{html.escape(str(meldung))}</p>',
        status_code=status,
    )


@router.get("/applications/{app_id}/preview", response_class=HTMLResponse)
def vorschau(
    request: Request, app_id: int, conn: sqlite3.Connection = Depends(get_conn)
):
    cfg = request.app.state.cfg
    try:
        quelltext = applications.render(conn, app_id, cfg)
    except ApplicationError as exc:
        return _fehler(exc)
    return HTMLResponse(pfade_umschreiben(quelltext))
