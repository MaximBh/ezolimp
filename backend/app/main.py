import base64
import hashlib
import os
import re
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pathlib import Path
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from urllib.parse import urlencode, quote, urlsplit

from app.database import get_db, create_tables, ensure_auth_schema_columns, User, Task, Solution, Match
from app.task_import import ensure_tasks_schema_columns, import_tasks_from_json, split_compound_tasks_after_import, has_seed_tasks
from app.config import _sync_tasks_on_startup_enabled, IS_PRODUCTION, PUBLIC_ORIGIN, CORS_ALLOWED_ORIGINS
from app.routers import auth, users, tasks, admin, pvp
import app.cache as app_cache
from app.rate_limits import limiter
from app.request_limits import RequestSizeLimitMiddleware

app = FastAPI(title="EzOlimp")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
_allowed_origins = list(CORS_ALLOWED_ORIGINS)
if "*" in _allowed_origins:
    raise RuntimeError("CORS_ALLOWED_ORIGINS must list explicit origins; wildcard is not allowed")
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
    max_age=600,
)


class SecurityHeadersMiddleware:
    def __init__(self, wrapped_app):
        self.wrapped_app = wrapped_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.wrapped_app(scope, receive, send)
            return

        async def add_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                security = {
                    b"x-content-type-options": b"nosniff",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                    b"x-frame-options": b"SAMEORIGIN",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                }
                if IS_PRODUCTION:
                    security[b"strict-transport-security"] = b"max-age=31536000"
                headers.extend((key, value) for key, value in security.items() if key not in existing)
                message["headers"] = headers
            await send(message)

        await self.wrapped_app(scope, receive, add_headers)


app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(admin.router)
app.include_router(pvp.router)


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": "Внутренняя ошибка сервера"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    messages = []
    for error in exc.errors():
        msg = error.get("msg", "")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        messages.append(msg)
    detail = "; ".join(messages) if messages else "Ошибка валидации данных"
    return JSONResponse(status_code=422, content={"error": detail})


@app.on_event("startup")
def startup():
    create_tables()
    ensure_auth_schema_columns()
    ensure_tasks_schema_columns()
    if not has_seed_tasks() or _sync_tasks_on_startup_enabled():
        import_tasks_from_json()
        split_compound_tasks_after_import()
    else:
        print("Skipped tasks.json sync on startup: tasks already exist (set SYNC_TASKS_ON_STARTUP=1 to force)")
    # Pre-warm caches
    app_cache.clear()


_frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
_inline_script_pattern = re.compile(rb"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)


def _content_security_policy(filename: str) -> str:
    try:
        page = (_frontend_dir / filename).read_bytes()
    except OSError:
        page = b""
    script_hashes = []
    for attrs, script in _inline_script_pattern.findall(page):
        if re.search(rb"\bsrc\s*=", attrs, re.IGNORECASE):
            continue
        normalized_script = script.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest = base64.b64encode(hashlib.sha256(normalized_script).digest()).decode("ascii")
        script_hashes.append(f"'sha256-{digest}'")
    script_sources = " ".join(["'self'", *script_hashes])
    if IS_PRODUCTION:
        public_host = urlsplit(PUBLIC_ORIGIN).netloc
        connect_sources = f"'self' wss://{public_host}"
        image_sources = "'self' data: https:"
    else:
        connect_sources = (
            "'self' http://localhost:8001 http://127.0.0.1:8001 "
            "ws://localhost:8001 ws://127.0.0.1:8001"
        )
        image_sources = "'self' data: https: http://localhost:8001 http://127.0.0.1:8001"
    return (
        "default-src 'self'; "
        f"script-src {script_sources}; script-src-attr 'none'; "
        "style-src 'self' 'unsafe-inline'; "
        f"img-src {image_sources}; font-src 'self' data:; "
        f"connect-src {connect_sources}; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
    )


def _frontend_page(filename: str):
    return FileResponse(
        _frontend_dir / filename,
        headers={"Content-Security-Policy": _content_security_policy(filename)},
    )


@app.get("/")
def root():
    return _frontend_page("main.html")


@app.get("/catalog")
def catalog_page():
    return _frontend_page("catalog.html")


@app.get("/training")
def training_page(request: Request):
    task_id = request.query_params.get("task")
    if task_id:
        query = [(key, value) for key, value in request.query_params.multi_items() if key != "task"]
        destination = f"/training/{quote(task_id, safe='')}"
        if query:
            destination = f"{destination}?{urlencode(query)}"
        return RedirectResponse(destination, status_code=308)
    return _frontend_page("training.html")


@app.get("/training/{task_id}")
def training_task_page(task_id: str):
    return _frontend_page("training.html")


@app.get("/pvp")
def pvp_page():
    return _frontend_page("pvp.html")


@app.get("/leaderboard")
def leaderboard_page():
    return _frontend_page("leaderboard.html")


@app.get("/analytics")
def analytics_page():
    return _frontend_page("analytics.html")


@app.get("/profile")
def profile_page(request: Request):
    user_id = request.query_params.get("id")
    if user_id:
        query = [(key, value) for key, value in request.query_params.multi_items() if key != "id"]
        destination = f"/profile/{quote(user_id, safe='')}"
        if query:
            destination = f"{destination}?{urlencode(query)}"
        return RedirectResponse(destination, status_code=308)
    return _frontend_page("profile.html")


@app.get("/profile/{user_id}")
def profile_user_page(user_id: str):
    return _frontend_page("profile.html")


@app.get("/admin")
def admin_page():
    return _frontend_page("admin.html")


@app.get("/{page_name}.html")
def legacy_page(page_name: str, request: Request):
    routes = {
        "index": "/",
        "main": "/",
        "catalog": "/catalog",
        "training": "/training",
        "pvp": "/pvp",
        "leaderboard": "/leaderboard",
        "analytics": "/analytics",
        "profile": "/profile",
        "admin": "/admin",
    }
    destination = routes.get(page_name)
    if destination is None:
        raise HTTPException(status_code=404, detail="Страница не найдена")

    query = list(request.query_params.multi_items())
    if page_name == "training":
        task_id = next((value for key, value in query if key == "task" and value), None)
        if task_id:
            destination = f"/training/{quote(task_id, safe='')}"
            query = [(key, value) for key, value in query if key != "task"]
    elif page_name == "profile":
        user_id = next((value for key, value in query if key == "id" and value), None)
        if user_id:
            destination = f"/profile/{quote(user_id, safe='')}"
            query = [(key, value) for key, value in query if key != "id"]

    if query:
        destination = f"{destination}?{urlencode(query)}"
    return RedirectResponse(destination, status_code=308)


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    cached = app_cache.get("stats")
    if cached is not None:
        return cached
    try:
        result = {
            "users": db.query(func.count(User.id)).scalar(),
            "tasks": db.query(func.count(Task.id)).scalar(),
            "solutions": db.query(func.count(Solution.id)).scalar(),
            "matches": db.query(func.count(Match.id)).scalar(),
        }
        app_cache.put("stats", result, ttl_sec=30)
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Ошибка при получении статистики")


@app.get("/healthz", include_in_schema=False)
def healthz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Сервис временно недоступен") from exc


if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
