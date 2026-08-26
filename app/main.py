import io
import os
import secrets
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from . import audit_log, auth, config
from .engine import mask_text
from .file_processing import (
    mask_csv_file,
    mask_docx_file,
    mask_pdf_file,
    mask_plain_text_file,
    mask_pptx_file,
    mask_xlsx_file,
)

MEDIA_TYPES = {
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
}

app = FastAPI(title="日本語マスキングツール")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

VALID_STYLES = {"tag", "mask", "redact"}

PUBLIC_PATHS = {"/login", "/auth/login", "/auth/callback"}


class AuthMiddleware(BaseHTTPMiddleware):
    """未ログインのアクセスを /login へ誘導する(APIは401を返す)。"""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if (
            not config.AUTH_ENABLED
            or path in PUBLIC_PATHS
            or path.startswith("/static/")
            or auth.is_authenticated(request)
        ):
            return await call_next(request)

        if path.startswith("/api/"):
            return JSONResponse({"detail": "ログインが必要です"}, status_code=401)
        return RedirectResponse(url="/login")


app.include_router(auth.router)

# ミドルウェアは後から追加したものほど外側(先に実行)になるため、
# セッションを参照する AuthMiddleware より後に SessionMiddleware を追加する。
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET_KEY or secrets.token_hex(32),
    same_site="lax",
    https_only=config.SESSION_HTTPS_ONLY,
)


@app.get("/api/me")
def get_me(request: Request):
    return request.session.get("user")


class MaskTextRequest(BaseModel):
    text: str = Field(..., description="マスキング対象のテキスト")
    entities: Optional[List[str]] = Field(
        default=None, description="検出したいエンティティ種別。未指定時は全種別。"
    )
    style: str = Field(default="tag", description="置換方式: tag / mask / redact")


class DetectionItem(BaseModel):
    entity_type: str
    entity_label: str
    start: int
    end: int
    score: float
    text: str


class MaskTextResponse(BaseModel):
    masked_text: str
    detections: List[DetectionItem]


def _validate_entities(entities: Optional[List[str]]) -> List[str]:
    if not entities:
        return config.ALL_ENTITY_CODES
    invalid = [e for e in entities if e not in config.ALL_ENTITY_CODES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"不明なエンティティ種別です: {invalid}")
    return entities


def _validate_style(style: str) -> str:
    if style not in VALID_STYLES:
        raise HTTPException(status_code=400, detail=f"不明なマスキング方式です: {style}")
    return style


@app.get("/api/entities")
def get_entities():
    return {"entities": config.ENTITY_DEFINITIONS}


@app.post("/api/mask/text", response_model=MaskTextResponse)
def mask_text_endpoint(request: MaskTextRequest):
    entities = _validate_entities(request.entities)
    style = _validate_style(request.style)

    if len(request.text) > 200_000:
        raise HTTPException(status_code=400, detail="テキストが長すぎます(20万文字以内)")

    masked_text, detections = mask_text(request.text, entities=entities, style=style)
    audit_log.log_text_request(request.text, style, entities, detections)
    return {"masked_text": masked_text, "detections": detections}


@app.post("/api/mask/file")
async def mask_file_endpoint(
    file: UploadFile = File(...),
    entities: Optional[str] = Form(default=None, description="カンマ区切りのエンティティ種別"),
    style: str = Form(default="tag"),
):
    entity_list = _validate_entities(
        [e.strip() for e in entities.split(",") if e.strip()] if entities else None
    )
    style = _validate_style(style)

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config.SUPPORTED_EXTENSIONS:
        supported = " / ".join(config.SUPPORTED_EXTENSIONS)
        raise HTTPException(status_code=400, detail=f"対応していないファイル形式です({supported} のみ)")

    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="ファイルサイズが上限を超えています")

    handlers = {
        ".csv": mask_csv_file,
        ".txt": mask_plain_text_file,
        ".xlsx": mask_xlsx_file,
        ".docx": mask_docx_file,
        ".pptx": mask_pptx_file,
        ".pdf": mask_pdf_file,
    }

    try:
        masked_bytes, detections, raw_text = handlers[ext](raw, entity_list, style)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit_log.log_file_request(filename, ext, style, entity_list, detections, raw_text)

    media_type = MEDIA_TYPES[ext]

    download_name = f"masked_{filename}"
    headers = {
        "Content-Disposition": f'attachment; filename="{download_name}"',
        "X-Detection-Count": str(len(detections)),
    }
    return StreamingResponse(io.BytesIO(masked_bytes), media_type=media_type, headers=headers)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()
