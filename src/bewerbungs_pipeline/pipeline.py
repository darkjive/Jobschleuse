"""Gemeinsame Fetch-Läufe für CLI und Web — beide Oberflächen sollen exakt
dasselbe tun, nicht zwei Varianten pflegen."""

import sqlite3

from . import db
from .sources import arbeitsagentur


def fetch_arbeitsagentur(
    conn: sqlite3.Connection,
    was: str,
    wo: str,
    umkreis: int = 25,
    veroeffentlicht_seit: int | None = None,
    ohne_zeitarbeit: bool = False,
    nur_arbeit: bool = False,
) -> tuple[int, int, int]:
    """Holt Treffer, speichert neue und prüft den Bestand nach.

    Gibt (geholt, neu, verschwunden) zurück. Der Bestandscheck läuft bei
    der Gelegenheit mit: derselbe Abruf, der gerade neue Treffer geprüft
    hat, taugt auch für die alten.
    """
    items = arbeitsagentur.fetch_jobs(
        was=was,
        wo=wo,
        umkreis=umkreis,
        veroeffentlicht_seit=veroeffentlicht_seit,
        ohne_zeitarbeit=ohne_zeitarbeit,
        nur_arbeit=nur_arbeit,
    )
    neu = sum(1 for item in items if db.insert_job(conn, item))
    weg = db.mark_gone(conn, arbeitsagentur.check_alive(db.offene_referenzen(conn)))
    return len(items), neu, weg


def fetch_indeed(
    conn: sqlite3.Connection,
    was: str,
    wo: str,
    umkreis: int = 25,
    seit_tage: int | None = None,
    ergebnisse: int = 25,
) -> tuple[int, int]:
    """Holt Treffer von Indeed und speichert neue. Gibt (geholt, neu) zurück.

    Lazy-Import: python-jobspy braucht spürbar Zeit beim Import (~200ms) und
    soll nicht jeden CLI-Aufruf verlangsamen, der gar nicht Indeed nutzt.
    """
    from .sources import indeed

    items = indeed.fetch_jobs(
        was=was,
        wo=wo,
        umkreis=umkreis,
        seit_stunden=seit_tage * 24 if seit_tage is not None else None,
        ergebnisse=ergebnisse,
    )
    neu = sum(1 for item in items if db.insert_job(conn, item))
    return len(items), neu
