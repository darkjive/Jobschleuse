import argparse
import json
import sys

from . import db
from .config import load_config
from .sources import arbeitsagentur


def _json_out(daten) -> None:
    print(json.dumps(daten, ensure_ascii=False))


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Ausgabe als JSON")


def _cmd_fetch(args: argparse.Namespace) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    items = arbeitsagentur.fetch_jobs(
        was=args.what,
        wo=args.where,
        umkreis=args.radius,
        veroeffentlicht_seit=args.since,
        ohne_zeitarbeit=args.no_temp_agency,
        nur_arbeit=args.jobs_only,
    )
    inserted = sum(1 for item in items if db.insert_job(conn, item))
    weg = db.mark_gone(conn, arbeitsagentur.check_alive(db.offene_referenzen(conn)))
    if args.json:
        _json_out({"fetched": len(items), "new": inserted, "gone": weg})
    else:
        print(f"{len(items)} Stellen geholt, {inserted} neu, {weg} nicht mehr verfügbar.")
    return 0


def _cmd_fetch_indeed(args: argparse.Namespace) -> int:
    from .sources import indeed

    cfg = load_config()
    conn = db.connect(cfg.db_path)
    items = indeed.fetch_jobs(
        was=args.what,
        wo=args.where,
        umkreis=args.radius,
        seit_stunden=args.since * 24 if args.since is not None else None,
        ergebnisse=args.limit,
    )
    inserted = sum(1 for item in items if db.insert_job(conn, item))
    if args.json:
        _json_out({"fetched": len(items), "new": inserted})
    else:
        print(f"{len(items)} Stellen geholt, {inserted} neu.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    referenzen = db.offene_referenzen(conn)
    if not args.json:
        print(f"{len(referenzen)} Stellen werden geprüft …")
    weg = db.mark_gone(conn, arbeitsagentur.check_alive(referenzen))
    if args.json:
        _json_out({"checked": len(referenzen), "gone": weg})
    else:
        print(f"{weg} Stellen sind bei der Quelle nicht mehr vorhanden.")
    return 0


# Kompakte Listenansicht für Agents: ohne Beschreibung, spart Kontext.
_LIST_FELDER = (
    "id", "title", "company", "location", "source", "url", "posted_at", "status",
    "homeoffice", "salary", "distance_km", "score", "tags",
)

# CLI-Sortschlüssel → (Schlüssel in db._SORT_SPALTEN, feste Richtung).
_SORTIERUNG = {
    "id": ("id", "asc"),
    "fresh": ("frische", "desc"),
    "distance": ("distance_km", "asc"),
    "score": ("score", "desc"),
}


def _job_dict(row, felder: tuple[str, ...] | None = None) -> dict:
    daten = dict(row) if felder is None else {f: row[f] for f in felder}
    daten["tags"] = json.loads(row["tags"]) if row["tags"] else []
    return daten


def _cmd_list(args: argparse.Namespace) -> int:
    if args.limit is not None and args.limit < 0:
        print("--limit darf nicht negativ sein.", file=sys.stderr)
        return 2
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    sort, order = _SORTIERUNG[args.sort]
    rows = db.suche_jobs(
        conn,
        status=args.status,
        q=args.query,
        ort=args.location,
        mit_verschwundenen=args.include_gone,
        unbewertet=args.unrated,
        min_score=args.min_score,
        sort=sort,
        order=order,
    )
    if args.limit is not None:
        rows = rows[: args.limit]
    if args.json:
        _json_out([_job_dict(row, _LIST_FELDER) for row in rows])
        return 0
    if not rows:
        print("Keine Stellen gefunden.")
        return 0
    print(f"{'ID':>4}  {'Score':>5}  {'Status':<9} {'Titel':<40} {'Firma':<30} Ort")
    for row in rows:
        score = "" if row["score"] is None else str(row["score"])
        print(
            f"{row['id']:>4}  {score:>5}  {row['status']:<9} "
            f"{row['title'][:40]:<40} {row['company'][:30]:<30} {row['location']}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    from .applications import ensure_description

    cfg = load_config()
    conn = db.connect(cfg.db_path)
    rows = []
    for job_id in args.ids:
        row = db.get_job(conn, job_id)
        if row is None:
            print(f"Job {job_id} nicht gefunden.", file=sys.stderr)
            return 1
        rows.append(row)
    rows = [ensure_description(conn, row) for row in rows]
    if args.json:
        _json_out([_job_dict(row) for row in rows])
        return 0
    for i, row in enumerate(rows):
        if i:
            print("\n" + "─" * 60 + "\n")
        score = "–" if row["score"] is None else row["score"]
        print(f"#{row['id']} {row['title']}")
        print(f"{row['company']} · {row['location']}")
        print(row["url"])
        print(f"Status: {row['status']}  Score: {score}")
        print()
        print(row["description_md"])
    return 0


def _ist_int(wert) -> bool:
    # bool ist in Python eine int-Unterklasse; true/false ist kein Score.
    return isinstance(wert, int) and not isinstance(wert, bool)


def _pruefe_bewertung(daten, conn) -> db.Rating:
    """Prüft eine Bewertung; ValueError mit deutscher Meldung bei Fehlern."""
    if not isinstance(daten, dict):
        raise ValueError("JSON-Objekt erwartet")
    job_id = daten.get("id")
    score = daten.get("score")
    reason = daten.get("reason")
    tags = daten.get("tags", [])
    if not _ist_int(job_id):
        raise ValueError("id fehlt oder ist keine Ganzzahl")
    if db.get_job(conn, job_id) is None:
        raise ValueError(f"Job {job_id} nicht gefunden")
    if not _ist_int(score) or not 0 <= score <= 100:
        raise ValueError("score muss eine Ganzzahl von 0 bis 100 sein")
    if not isinstance(reason, str):
        raise ValueError("reason fehlt oder ist kein Text")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError("tags muss eine Liste aus Texten sein")
    return db.Rating(job_id, score, reason, tags)


def _cmd_rate(args: argparse.Namespace) -> int:
    einzeln = any(v is not None for v in (args.id, args.score, args.reason, args.tags))
    if args.stdin == einzeln:
        print("Entweder ID mit --score/--reason oder --stdin angeben.", file=sys.stderr)
        return 2
    if einzeln and (args.id is None or args.score is None or args.reason is None):
        print("ID, --score und --reason sind Pflicht.", file=sys.stderr)
        return 2
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    bewertungen: list[db.Rating] = []
    if args.stdin:
        for nr, zeile in enumerate(sys.stdin, start=1):
            if not zeile.strip():
                continue
            try:
                # json.JSONDecodeError ist eine ValueError-Unterklasse.
                bewertungen.append(_pruefe_bewertung(json.loads(zeile), conn))
            except ValueError as exc:
                print(f"Zeile {nr}: {exc}", file=sys.stderr)
                return 1
    else:
        tags = args.tags.split(",") if args.tags else []
        daten = {"id": args.id, "score": args.score, "reason": args.reason, "tags": tags}
        try:
            bewertungen.append(_pruefe_bewertung(daten, conn))
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
    anzahl = db.set_ratings_bulk(conn, bewertungen)
    if args.json:
        _json_out({"rated": anzahl})
    else:
        print(f"{anzahl} Stellen bewertet.")
    return 0


def _set_status(ids: list[int], status: str, als_json: bool) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    fehlend = [job_id for job_id in ids if db.get_job(conn, job_id) is None]
    if fehlend:
        print(f"Job {', '.join(map(str, fehlend))} nicht gefunden.", file=sys.stderr)
        return 1
    db.set_status_bulk(conn, ids, status)
    if als_json:
        _json_out({"status": status, "ids": ids})
    else:
        for job_id in ids:
            print(f"Job {job_id} → {status}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    from .generate import generate_application
    from .llm import make_client

    cfg = load_config()
    if not (cfg.llm_base_url and cfg.llm_api_key and cfg.llm_model):
        print(
            "LLM_BASE_URL, LLM_API_KEY und LLM_MODEL in .env setzen.", file=sys.stderr
        )
        return 1
    conn = db.connect(cfg.db_path)
    client = make_client(cfg.llm_base_url, cfg.llm_api_key)
    out_dir = generate_application(conn, args.id, cfg, client)
    print(f"Fertig: {out_dir / 'index.html'}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import webbrowser

    import uvicorn

    from .web.app import create_app

    cfg = load_config()
    app = create_app(cfg)
    adresse = f"http://{args.host}:{args.port}"
    if args.host not in ("127.0.0.1", "localhost", "::1") and not cfg.web_token:
        print(
            "[SECURITY] Achtung: --host ist nicht loopback, aber JOBS_WEB_TOKEN ist nicht "
            "gesetzt — die API ist im ganzen Netz ohne Auth erreichbar. Setze JOBS_WEB_TOKEN "
            "in .env, wenn das Netz nicht vertrauenswürdig ist."
        )
    print(f"Bewerbungs-App läuft auf {adresse} — mit Strg+C beenden.")
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobs", description="Bewerbungs-Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="Stellen von der Arbeitsagentur holen")
    p_fetch.add_argument("--what", required=True, help="Suchbegriff, z. B. Beruf")
    p_fetch.add_argument("--where", required=True, help="Ort")
    p_fetch.add_argument("--radius", type=int, default=25, help="Umkreis in km")
    p_fetch.add_argument(
        "--since", type=int, default=None, help="nur Anzeigen der letzten N Tage"
    )
    p_fetch.add_argument(
        "--no-temp-agency",
        action="store_true",
        help="Arbeitnehmerüberlassung ausblenden",
    )
    p_fetch.add_argument(
        "--jobs-only",
        action="store_true",
        help="nur Arbeitsstellen, keine Ausbildungen",
    )
    _json_flag(p_fetch)
    p_fetch.set_defaults(func=_cmd_fetch)

    p_fetch_indeed = sub.add_parser("fetch-indeed", help="Stellen von Indeed holen")
    p_fetch_indeed.add_argument("--what", required=True, help="Suchbegriff, z. B. Beruf")
    p_fetch_indeed.add_argument("--where", required=True, help="Ort")
    p_fetch_indeed.add_argument("--radius", type=int, default=25, help="Umkreis in km")
    p_fetch_indeed.add_argument(
        "--since", type=int, default=None, help="nur Anzeigen der letzten N Tage"
    )
    p_fetch_indeed.add_argument(
        "--limit", type=int, default=25, help="maximale Trefferzahl"
    )
    _json_flag(p_fetch_indeed)
    p_fetch_indeed.set_defaults(func=_cmd_fetch_indeed)

    p_list = sub.add_parser("list", help="Stellen anzeigen")
    p_list.add_argument("--status", choices=sorted(db.STATUSES), default=None)
    p_list.add_argument("--query", default=None, help="Suche in Titel und Firma")
    p_list.add_argument("--location", default=None, help="Suche im Ort")
    p_list.add_argument("--unrated", action="store_true", help="nur unbewertete Stellen")
    p_list.add_argument("--min-score", type=int, default=None, help="Mindest-Score")
    p_list.add_argument(
        "--include-gone", action="store_true", help="auch verschwundene Anzeigen"
    )
    p_list.add_argument("--sort", choices=list(_SORTIERUNG), default="id")
    p_list.add_argument("--limit", type=int, default=None, help="maximale Anzahl")
    _json_flag(p_list)
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Stellen mit Beschreibung anzeigen")
    p_show.add_argument("ids", type=int, nargs="+", metavar="ID")
    _json_flag(p_show)
    p_show.set_defaults(func=_cmd_show)

    p_rate = sub.add_parser("rate", help="Stellen bewerten (Score 0–100)")
    p_rate.add_argument("id", type=int, nargs="?", metavar="ID")
    p_rate.add_argument("--score", type=int, default=None, help="0 bis 100")
    p_rate.add_argument("--reason", default=None, help="kurze Begründung")
    p_rate.add_argument("--tags", default=None, help="kommagetrennt, z. B. python,react")
    p_rate.add_argument(
        "--stdin",
        action="store_true",
        help='NDJSON von stdin: {"id", "score", "reason", "tags"} je Zeile',
    )
    _json_flag(p_rate)
    p_rate.set_defaults(func=_cmd_rate)

    p_check = sub.add_parser("check", help="Bestand auf verschwundene Anzeigen prüfen")
    _json_flag(p_check)
    p_check.set_defaults(func=_cmd_check)

    p_pick = sub.add_parser("pick", help="Stellen auswählen")
    p_pick.add_argument("ids", type=int, nargs="+", metavar="ID")
    _json_flag(p_pick)
    p_pick.set_defaults(func=lambda a: _set_status(a.ids, "selected", a.json))

    p_reject = sub.add_parser("reject", help="Stellen aussortieren")
    p_reject.add_argument("ids", type=int, nargs="+", metavar="ID")
    _json_flag(p_reject)
    p_reject.set_defaults(func=lambda a: _set_status(a.ids, "rejected", a.json))

    p_gen = sub.add_parser("generate", help="Bewerbung für ausgewählte Stelle erzeugen")
    p_gen.add_argument("id", type=int)
    p_gen.set_defaults(func=_cmd_generate)

    p_serve = sub.add_parser("serve", help="Weboberfläche starten")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--no-browser", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
