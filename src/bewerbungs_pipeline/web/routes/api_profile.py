from fastapi import APIRouter, HTTPException, Request, UploadFile

router = APIRouter(prefix="/api/profile")

# Dateiname ist im Template hart verdrahtet (templates/bewerbung.html) —
# ein Upload ersetzt genau diese Datei, keine beliebigen Namen/Formate.
_ASSETS = {
    "portrait": ("portrait.jpg", {"image/jpeg"}),
    "signature": ("signature.png", {"image/png"}),
}


@router.post("/{art}")
async def asset_hochladen(art: str, datei: UploadFile, request: Request) -> dict:
    if art not in _ASSETS:
        raise HTTPException(404, f"Unbekannter Asset-Typ: {art}")
    dateiname, erlaubte_typen = _ASSETS[art]
    if datei.content_type not in erlaubte_typen:
        erwartet = ", ".join(sorted(erlaubte_typen))
        raise HTTPException(400, f"Erwarte {erwartet}, erhalten: {datei.content_type}")

    cfg = request.app.state.cfg
    ziel = cfg.template_path.parent / "assets" / dateiname
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(await datei.read())
    return {"pfad": f"/template-assets/assets/{dateiname}"}
