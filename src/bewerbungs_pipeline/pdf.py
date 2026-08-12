"""HTML zu PDF, so wie es der Browser druckt.

Warum ein echter Browser und nicht WeasyPrint o. ä.: die Vorlage lebt von
CSS-Grid, exakten mm-Massen und `@page`. Nur eine Browser-Engine gibt das so
wieder, wie die Vorschau es zeigt.
"""

import re
import shutil
from pathlib import Path

# Chromium bringt Playwright zwar selbst mit, aber der Download waere ein
# halbes Gigabyte. Ein im System vorhandener Browser tut es genauso.
BROWSER_KANDIDATEN = (
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
    "google-chrome",
    "brave",
)


class PdfError(Exception):
    """Fachlicher Fehler mit deutscher, benutzertauglicher Meldung."""


def browser_pfad() -> str | None:
    """Erster im System gefundener Chromium-Abkömmling."""
    for name in BROWSER_KANDIDATEN:
        pfad = shutil.which(name)
        if pfad:
            return pfad
    return None


def seitenzahl(pdf_pfad: Path) -> int:
    """Seitenzahl aus dem Seitenbaum, ohne ein weiteres Werkzeug vorauszusetzen.

    /Count steht im Wurzelknoten des Baums; verschachtelte Knoten tragen
    kleinere Werte, deshalb der groesste gewinnt.
    """
    treffer = re.findall(rb"/Count\s+(\d+)", pdf_pfad.read_bytes())
    if not treffer:
        raise PdfError(f"Seitenzahl nicht lesbar: {pdf_pfad}")
    return max(int(t) for t in treffer)


def erzeuge(html_pfad: Path, ziel: Path) -> Path:
    """Druckt eine lokale HTML-Datei nach PDF.

    Laeuft ueber file://, damit Schriften, Bilder und Stylesheet daneben
    gefunden werden — die Vorlage verweist relativ auf sie.
    """
    if not html_pfad.exists():
        raise PdfError(f"Vorlage nicht gefunden: {html_pfad}")

    browser = browser_pfad()
    if browser is None:
        raise PdfError(
            "Kein Chromium gefunden. Bitte 'chromium' installieren "
            f"(gesucht wurde nach: {', '.join(BROWSER_KANDIDATEN)})."
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - Abhaengigkeit ist gesetzt
        raise PdfError(f"Playwright fehlt: {exc}") from exc

    ziel.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            instanz = p.chromium.launch(executable_path=browser)
            seite = instanz.new_page()
            try:
                seite.goto(html_pfad.resolve().as_uri(), wait_until="networkidle")
                # Ohne das Warten druckt Chromium mit der Ersatzschrift los:
                # font-display:swap rendert sofort, das Layout verschiebt sich
                # und der Text landet in falscher Breite.
                seite.wait_for_function("document.fonts.ready.then(() => true)")
                seite.pdf(
                    path=str(ziel),
                    prefer_css_page_size=True,
                    print_background=True,
                )
            finally:
                instanz.close()
    except PdfError:
        raise
    except Exception as exc:
        raise PdfError(f"PDF-Erzeugung fehlgeschlagen: {exc}") from exc

    return ziel
