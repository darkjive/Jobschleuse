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
    r'(?P<attr>\b(?:href|src)=")(?P<pfad>(?!https?:|mailto:|tel:|/|data:|#)[^"]+)"'
)


def pfade_umschreiben(quelltext: str) -> str:
    """Macht relative Vorlagen-Pfade im iframe auflösbar.

    Betrifft nur die Vorschau — die exportierte Datei in out/ bleibt
    unverändert, dort liegen styles.css und assets/ daneben.
    """
    return _ASSET_RE.sub(r'\g<attr>/template-assets/\g<pfad>"', quelltext)


_SKALIERUNGS_SNIPPET = """
<style>
  html, body { margin: 0; overflow-x: hidden; }
  .doc { transform-origin: top center; }
</style>
<script>
(function () {
  function anpassen() {
    var doc = document.querySelector(".doc");
    var blatt = document.querySelector(".sheet");
    if (!doc || !blatt) return;
    doc.style.transform = "none";
    // .doc selbst ist width:auto und füllt den Container (siehe styles.css) —
    // seine eigene Breite verrät nichts über den festen A4-Inhalt, der ihn
    // überragt. Die tatsächliche Breite kommt vom ersten .sheet.
    var breite = blatt.getBoundingClientRect().width;
    var hoehe = doc.getBoundingClientRect().height;
    var faktor = Math.min(1, window.innerWidth / breite);
    doc.style.transform = "scale(" + faktor + ")";
    document.body.style.height = (hoehe * faktor) + "px";
  }
  window.addEventListener("resize", anpassen);
  window.addEventListener("load", anpassen);
  anpassen();
})();
</script>
</body>
"""


def skalierung_injizieren(quelltext: str) -> str:
    """Skaliert das Dokument im iframe auf die verfügbare Breite.

    Die Vorlage ist fest auf A4-Breite (210mm) ausgelegt (siehe styles.css)
    — ohne das würde sie im schmäleren Vorschau-Panel abgeschnitten statt
    verkleinert dargestellt. Betrifft nur die Vorschau, nicht den PDF-Export.
    """
    if "</body>" not in quelltext:
        return quelltext
    return quelltext.replace("</body>", _SKALIERUNGS_SNIPPET, 1)


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
    return HTMLResponse(skalierung_injizieren(pfade_umschreiben(quelltext)))
