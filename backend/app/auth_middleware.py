import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import jwt
from fastapi import Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

# Importing config loads the external and project environment files before reading secrets.
from app import config as _config
from app.database import User, get_db
from app.config import CORS_ALLOWED_ORIGINS, IS_PRODUCTION

_SECRET = os.getenv("JWT_SECRET", "").strip()
if len(_SECRET.encode("utf-8")) < 32 or _SECRET == "change-me-in-production":
    raise RuntimeError("JWT_SECRET must be configured with at least 32 bytes of random data")

_ALGORITHM = "HS256"
_ISSUER = "ezolimp"
_AUDIENCE = "ezolimp-web"
SESSION_COOKIE_NAME = "ezolimp_session"
try:
    _TOKEN_TTL_MINUTES = int(os.getenv("JWT_TTL_MINUTES", "720"))
except ValueError as exc:
    raise RuntimeError("JWT_TTL_MINUTES must be an integer") from exc
if not 10 <= _TOKEN_TTL_MINUTES <= 10080:
    raise RuntimeError("JWT_TTL_MINUTES must be between 10 and 10080")


def create_token(user_id: int, session_version: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "ver": int(session_version),
        "jti": uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=_TOKEN_TTL_MINUTES),
        "iss": _ISSUER,
        "aud": _AUDIENCE,
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=_TOKEN_TTL_MINUTES * 60,
        path="/",
        secure=IS_PRODUCTION,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=IS_PRODUCTION,
        httponly=True,
        samesite="strict",
    )


def authenticate_token(token: str, db: Session) -> User:
    raw_token = str(token or "").strip()
    if raw_token.lower().startswith("bearer "):
        raw_token = raw_token[7:].strip()
    if not raw_token or len(raw_token) > 8192:
        raise HTTPException(status_code=401, detail="Неверный токен")

    try:
        payload = jwt.decode(
            raw_token,
            _SECRET,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            audience=_AUDIENCE,
            options={"require": ["sub", "ver", "jti", "iat", "exp", "iss", "aud"]},
        )
        user_id = int(payload["sub"])
        token_version = int(payload["ver"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истёк")
    except Exception:
        raise HTTPException(status_code=401, detail="Неверный токен")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Пользователь заблокирован")
    if token_version != user.session_version:
        raise HTTPException(status_code=401, detail="Сессия отозвана")
    return user


def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if authorization:
        return authenticate_token(authorization, db)

    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_token:
        raise HTTPException(status_code=401, detail="Требуется авторизация")

    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if not origin or origin not in CORS_ALLOWED_ORIGINS:
            raise HTTPException(status_code=403, detail="Недопустимый Origin")

    return authenticate_token(cookie_token, db)


def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Нужны права администратора")
    return current_user


def _invalidate_user_cache(user_id: int = None):
    # Kept for existing callers; authentication no longer caches user sessions.
    return None
