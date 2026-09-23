import shutil
from pathlib import Path

import pytest

from bewerbungs_pipeline import pdf

HTML = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<style>@page{ size:A4; margin:0 } *{ margin:0 }
.blatt{ width:210mm; height:297mm; break-after:page }
.blatt:last-child{ break-after:auto }</style></head>
<body>
  <div class="blatt"><h1>Erstes Blatt</h1></div>
  <div class="blatt"><p>Zweites Blatt</p></div>
</body></html>
"""

braucht_browser = pytest.mark.skipif(
    pdf.browser_pfad() is None, reason="kein Chromium im System gefunden"
)


def test_browser_pfad_findet_chromium_oder_gibt_none():
    pfad = pdf.browser_pfad()
    assert pfad is None or shutil.which(pfad) or pfad.startswith("/")


def test_browser_pfad_faellt_auf_playwright_zurueck(monkeypatch, tmp_path):
    """Docker-Images ohne Systempaket: `playwright install chromium` muss
    reichen, auch ohne `chromium`/`google-chrome` im PATH."""
    fake = tmp_path / "chrome"
    fake.write_text("")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(pdf, "_playwright_browser_pfad", lambda: str(fake))
    assert pdf.browser_pfad() == str(fake)


def test_browser_pfad_ohne_systempaket_und_ohne_playwright_browser(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(pdf, "_playwright_browser_pfad", lambda: None)
    assert pdf.browser_pfad() is None


@braucht_browser
def test_erzeuge_schreibt_pdf(tmp_path):
    quelle = tmp_path / "seite.html"
    quelle.write_text(HTML)
    ziel = tmp_path / "ergebnis.pdf"
    ergebnis = pdf.erzeuge(quelle, ziel)
    assert ergebnis == ziel
    assert ziel.read_bytes().startswith(b"%PDF")


@braucht_browser
def test_erzeuge_haelt_seitenumbrueche_ein(tmp_path):
    """Die Vorlage setzt jedes Blatt auf exakt A4 — das darf nicht verrutschen."""
    quelle = tmp_path / "seite.html"
    quelle.write_text(HTML)
    ziel = pdf.erzeuge(quelle, tmp_path / "ergebnis.pdf")
    assert pdf.seitenzahl(ziel) == 2


@braucht_browser
def test_erzeuge_behaelt_den_text(tmp_path):
    """Ohne echte Textebene kann kein Bewerbungssystem das PDF lesen."""
    quelle = tmp_path / "seite.html"
    quelle.write_text(HTML)
    ziel = pdf.erzeuge(quelle, tmp_path / "ergebnis.pdf")
    roh = ziel.read_bytes()
    assert b"/Font" in roh


def test_erzeuge_meldet_fehlende_quelle_deutsch(tmp_path):
    with pytest.raises(pdf.PdfError, match="nicht gefunden"):
        pdf.erzeuge(tmp_path / "gibtsnicht.html", tmp_path / "x.pdf")
