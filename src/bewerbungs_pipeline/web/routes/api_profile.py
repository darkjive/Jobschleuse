from fastapi import APIRouter, HTTPException, Request, UploadFile

router = APIRouter(prefix="/api/profile")

# Portrait und Unterschrift sind klein; alles darüber ist ein Versehen.
MAX_BYTES = 10 * 1024 * 1024

# Dateiname ist im Template hart verdrahtet (templates/bewerbung.html) —
# ein Upload ersetzt genau diese Datei, keine beliebigen Namen/Formate.
# Geprüft wird die Signatur der Bytes, nicht der Content-Type: den setzt
# der Client.
_ASSETS = {
    "portrait": ("portrait.jpg", "image/jpeg", b"\xff\xd8\xff"),
    "signature": ("signature.png", "image/png", b"\x89PNG\r\n\x1a\n"),
}


@router.post("/{art}")
async def asset_hochladen(art: str, datei: UploadFile, request: Request) -> dict:
    if art not in _ASSETS:
        raise HTTPException(404, f"Unbekannter Asset-Typ: {art}")
    dateiname, typ, signatur = _ASSETS[art]

    inhalt = await datei.read(MAX_BYTES + 1)
    if len(inhalt) > MAX_BYTES:
        raise HTTPException(413, f"Datei zu groß (max. {MAX_BYTES // 1024 // 1024} MB).")
    if not inhalt.startswith(signatur):
        raise HTTPException(400, f"Erwarte {typ}, die Datei ist keines.")

    cfg = request.app.state.cfg
    ziel = cfg.template_path.parent / "assets" / dateiname
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(inhalt)
    return {"pfad": f"/template-assets/assets/{dateiname}"}
