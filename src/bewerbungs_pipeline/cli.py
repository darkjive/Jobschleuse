import argparse
import sys

from . import db
from .config import load_config
from .sources import arbeitsagentur


def _cmd_fetch(args: argparse.Namespace) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    items = arbeitsagentur.fetch_jobs(was=args.was, wo=args.wo, umkreis=args.umkreis)
    inserted = sum(1 for item in items if db.insert_job(conn, item))
    print(f"{len(items)} Stellen geholt, {inserted} neu.")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    rows = db.list_jobs(conn, status=args.status)
    if not rows:
        print("Keine Stellen gefunden.")
        return 0
    print(f"{'ID':>4}  {'Status':<9} {'Titel':<40} {'Firma':<30} Ort")
    for row in rows:
        print(
            f"{row['id']:>4}  {row['status']:<9} "
            f"{row['title'][:40]:<40} {row['company'][:30]:<30} {row['location']}"
        )
    return 0


def _set_status(job_id: int, status: str) -> int:
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    if db.get_job(conn, job_id) is None:
        print(f"Job {job_id} nicht gefunden.", file=sys.stderr)
        return 1
    db.set_status(conn, job_id, status)
    print(f"Job {job_id} → {status}")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    from .generate import generate_application
    from .llm import make_client

    cfg = load_config()
    if not (cfg.llm_base_url and cfg.llm_api_key and cfg.llm_model):
        print("LLM_BASE_URL, LLM_API_KEY und LLM_MODEL in .env setzen.", file=sys.stderr)
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
    adresse = f"http://127.0.0.1:{args.port}"
    print(f"Bewerbungs-App läuft auf {adresse} — mit Strg+C beenden.")
    if not args.no_browser:
        webbrowser.open(adresse)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobs", description="Bewerbungs-Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="Stellen von der Arbeitsagentur holen")
    p_fetch.add_argument("--was", required=True, help="Suchbegriff, z. B. Beruf")
    p_fetch.add_argument("--wo", required=True, help="Ort")
    p_fetch.add_argument("--umkreis", type=int, default=25, help="Umkreis in km")
    p_fetch.set_defaults(func=_cmd_fetch)

    p_list = sub.add_parser("list", help="Stellen anzeigen")
    p_list.add_argument("--status", choices=sorted(db.STATUSES), default=None)
    p_list.set_defaults(func=_cmd_list)

    p_pick = sub.add_parser("pick", help="Stelle auswählen")
    p_pick.add_argument("id", type=int)
    p_pick.set_defaults(func=lambda a: _set_status(a.id, "selected"))

    p_reject = sub.add_parser("reject", help="Stelle aussortieren")
    p_reject.add_argument("id", type=int)
    p_reject.set_defaults(func=lambda a: _set_status(a.id, "rejected"))

    p_gen = sub.add_parser("generate", help="Bewerbung für ausgewählte Stelle erzeugen")
    p_gen.add_argument("id", type=int)
    p_gen.set_defaults(func=_cmd_generate)

    p_serve = sub.add_parser("serve", help="Weboberfläche starten")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--no-browser", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
