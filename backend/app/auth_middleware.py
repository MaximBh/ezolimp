import os
import time
import threading
from datetime import datetime, timedelta
from typing import Optional
import jwt
from fastapi import HTTPException, Depends, Header
from sqlalchemy.orm import Session
from app.database import get_db, User

_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
_ALGORITHM = "HS256"
_TOKEN_TTL_DAYS = int(os.getenv("JWT_TTL_DAYS", "30"))

# In-memory user cache: token -> (expires_at, user_id, user_obj)
_USER_CACHE_TTL = 60  # seconds
_user_cache: dict[str, tuple[float, int, User]] = {}
_user_cache_lock = threading.Lock()


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=_TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def _invalidate_user_cache(user_id: int = None):
    """Invalidate cache entries for a specific user or all entries."""
    with _user_cache_lock:
        if user_id is None:
            _user_cache.clear()
        else:
            keys_to_remove = [k for k, (_, uid, _) in _user_cache.items() if uid == user_id]
            for k in keys_to_remove:
                del _user_cache[k]


def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    token = authorization[7:]

    # Check cache first
    with _user_cache_lock:
        cached = _user_cache.get(token)
        if cached is not None:
            expires_at, user_id, user_obj = cached
            if time.monotonic() > expires_at:
                del _user_cache[token]
            else:
                # Verify user still exists and is active (use cached object's state)
                return user_obj

    # Decode JWT
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истёк")
    except Exception:
        raise HTTPException(status_code=401, detail="Неверный токен")

    # DB lookup
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Пользователь заблокирован")

    # Cache the result
    with _user_cache_lock:
        _user_cache[token] = (time.monotonic() + _USER_CACHE_TTL, user_id, user)
        # Evict old entries periodically (keep cache bounded)
        if len(_user_cache) > 500:
            now = time.monotonic()
            expired = [k for k, (exp, _, _) in _user_cache.items() if now > exp]
            for k in expired:
                del _user_cache[k]

    return user


def get_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Нужны права администратора")
    return current_user
