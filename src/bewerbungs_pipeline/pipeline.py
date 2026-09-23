"""Gemeinsame Fetch-Läufe für CLI und Web — beide Oberflächen sollen exakt
dasselbe tun, nicht zwei Varianten pflegen."""

import sqlite3
from typing import NamedTuple

import httpx

from . import db
from .sources import arbeitsagentur, karriereseiten


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
    # Kostet keinen Netzabruf: die neuen Treffer verraten, welche Firmen
    # einen eigenen Stellenfeed haben (siehe fetch_karriereseiten).
    karriereseiten_entdecken(conn)
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


def karriereseiten_entdecken(conn: sqlite3.Connection) -> int:
    """Trägt die Karriereseiten ein, auf die gespeicherte Anzeigen verlinken.

    Gibt die Zahl der neu entdeckten Seiten zurück.
    """
    neu = 0
    for link, firma in db.link_kandidaten(conn):
        seite = karriereseiten.erkenne(link)
        if seite and db.karriereseite_merken(conn, seite.system, seite.kennung, firma):
            neu += 1
    return neu


def karriereseite_hinzufuegen(
    conn: sqlite3.Connection, url: str, firma: str | None = None
) -> karriereseiten.Karriereseite | None:
    """Trägt eine Karriereseite von Hand ein; ``None`` bei unbekanntem System."""
    seite = karriereseiten.erkenne(url)
    if seite is not None:
        db.karriereseite_merken(conn, seite.system, seite.kennung, firma or seite.kennung)
    return seite


class KarriereErgebnis(NamedTuple):
    geholt: int
    neu: int
    weg: int
    fehler: int


def fetch_karriereseiten(
    conn: sqlite3.Connection, was: str | None = None, wo: str | None = None
) -> KarriereErgebnis:
    """Fragt alle eingetragenen Karriereseiten ab und speichert passende Stellen.

    Ein Feed ist die vollständige Liste einer Firma: Was darin fehlt, ist
    weg. Das gilt aber nur nach erfolgreichem Abruf — scheitert er, bleibt
    der Bestand dieser Firma unangetastet und der Fehler wird vermerkt.
    Die Filter `was`/`wo` wirken nur auf das Speichern neuer Stellen, nicht
    auf die Bestandsprüfung.
    """
    geholt = neu = weg = fehler = 0
    with httpx.Client() as client:
        for zeile in db.karriereseiten(conn):
            seite = karriereseiten.Karriereseite(zeile["system"], zeile["kennung"])
            try:
                items = karriereseiten.fetch_seite(seite, zeile["company"], client)
            except Exception as exc:
                # Netz-, HTTP- oder Formatfehler einer Firma dürfen die
                # übrigen nicht aufhalten.
                db.karriereseite_abgerufen(conn, zeile["id"], f"{type(exc).__name__}: {exc}")
                fehler += 1
                continue
            db.karriereseite_abgerufen(conn, zeile["id"])
            weg += db.mark_gone_ausser(
                conn, seite.praefix, {item.source_ref for item in items}
            )
            passende = [i for i in items if karriereseiten.passt(i, was, wo)]
            geholt += len(passende)
            neu += sum(1 for item in passende if db.insert_job(conn, item))
    return KarriereErgebnis(geholt, neu, weg, fehler)
