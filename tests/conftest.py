"""Gemeinsame Vorbereitung für die Testsuite.

Die Suite läuft mit ``filterwarnings = error`` (siehe pyproject.toml). Eine
sqlite3.Connection, die niemand schließt, meldet beim Aufräumen eine
ResourceWarning — die würde die Suite rot färben, obwohl fachlich nichts
falsch ist.
"""

import sqlite3
import threading

import pytest

from bewerbungs_pipeline import db


@pytest.fixture(autouse=True)
def _verbindungen_aufraeumen(monkeypatch):
    """Schließt die Verbindungen, die ein Test selbst geöffnet hat.

    Bewusst nur Verbindungen aus dem Test-Thread: was in einem
    Hintergrund-Thread entsteht, gehört dem Produktionscode, der sie selbst
    schließen muss — solche Lecks sollen weiterhin auffallen. Außerdem darf
    eine sqlite3.Connection ohnehin nicht aus einem fremden Thread
    geschlossen werden.
    """
    test_thread = threading.get_ident()
    offen: list[sqlite3.Connection] = []
    original = db.connect

    def merkend(db_path):
        conn = original(db_path)
        if threading.get_ident() == test_thread:
            offen.append(conn)
        return conn

    monkeypatch.setattr(db, "connect", merkend)
    yield
    for conn in offen:
        conn.close()


@pytest.fixture(autouse=True)
def _kein_abruf_von_firmenseiten(monkeypatch):
    """`ensure_description` fragt bei kurzer Beschreibung die Firmenseite an.

    Tests, die Stellen mit Beispiel-URLs anlegen, sollen dabei nicht ins
    Netz gehen. Wer den Abruf selbst prüft, importiert die echte Funktion
    beim Laden des Moduls (vor diesem Fixture) oder patcht erneut.
    """
    from bewerbungs_pipeline.sources import jsonld

    monkeypatch.setattr(jsonld, "abrufen", lambda url, client=None: None)
    jsonld._robots_cache.clear()
