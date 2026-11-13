import hashlib
import hmac
import os
from datetime import datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.database import AuthRateAttempt
from app import config as _config


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
)
_RATE_LIMIT_HASH_KEY = os.getenv("JWT_SECRET", "").encode("utf-8")


def enforce_persistent_auth_ip_limit(request: Request, db: Session, action: str,
                                    limit: int, window_seconds: int = 60) -> None:
    """Apply an IP limit in SQLite so auth limits are shared by local workers."""
    client = request.client
    remote_ip = client.host if client and client.host else "unknown"
    ip_hash = hmac.new(_RATE_LIMIT_HASH_KEY, remote_ip.encode("utf-8"), hashlib.sha256).hexdigest()
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=window_seconds)

    try:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        db.query(AuthRateAttempt).filter(
            AuthRateAttempt.attempted_at < now - timedelta(days=2)
        ).delete(synchronize_session=False)
        recent = db.query(func.count(AuthRateAttempt.id)).filter(
            AuthRateAttempt.action == action,
            AuthRateAttempt.ip_hash == ip_hash,
            AuthRateAttempt.attempted_at >= cutoff,
        ).scalar() or 0
        if recent >= limit:
            db.rollback()
            raise HTTPException(status_code=429, detail="Слишком много запросов. Повторите позже.")
        db.add(AuthRateAttempt(action=action, ip_hash=ip_hash, attempted_at=now))
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Сервис авторизации временно недоступен") from exc
