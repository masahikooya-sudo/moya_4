"""Googleアカウントによるログイン(OpenID Connect)。

有効時(config.AUTH_ENABLED)は、指定したGoogle Workspaceドメイン
(config.GOOGLE_ALLOWED_DOMAIN)に属するアカウントでログインしたユーザーのみ
アプリへのアクセスを許可する。main.py 側の AuthMiddleware が全リクエストに
対してログイン状態を確認する。
"""

import logging
import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from starlette.responses import FileResponse, RedirectResponse

from . import config

logger = logging.getLogger("uvicorn.error")

router = APIRouter()

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

oauth = OAuth()
if config.AUTH_ENABLED:
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "AUTH_ENABLED=true ですが GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET が"
            "設定されていません。Google Cloud Consoleで発行した値を環境変数に設定するか、"
            "動作確認のため一時的に AUTH_ENABLED=false を指定してください。"
        )
    oauth.register(
        name="google",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("user"))


def _is_allowed(email: str, hosted_domain: str) -> bool:
    allowed = config.GOOGLE_ALLOWED_DOMAIN
    return hosted_domain == allowed or email.lower().endswith(f"@{allowed.lower()}")


@router.get("/login")
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/")
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@router.get("/auth/login")
async def start_login(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/")
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email", "")
    hosted_domain = userinfo.get("hd", "")

    if not email or not userinfo.get("email_verified") or not _is_allowed(email, hosted_domain):
        logger.warning("Googleログイン拒否: email=%s hd=%s", email, hosted_domain)
        request.session.clear()
        return RedirectResponse(url="/login?error=forbidden")

    request.session["user"] = {
        "email": email,
        "name": userinfo.get("name", email),
    }
    return RedirectResponse(url="/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")
