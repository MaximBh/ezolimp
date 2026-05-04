"""
Lightweight in-memory TTL cache for hot endpoints.
No external dependencies — uses dict + time.monotonic.
Thread-safe via threading.Lock.
"""
import time
import threading
from typing import Any, Optional

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}  # key -> (expires_at, value)


def get(key: str) -> Optional[Any]:
    """Return cached value or None if expired/missing."""
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del _store[key]
            return None
        return value


def put(key: str, value: Any, ttl_sec: int = 60):
    """Store value with TTL in seconds."""
    with _lock:
        _store[key] = (time.monotonic() + ttl_sec, value)


def invalidate(key: str):
    """Remove a specific cache entry."""
    with _lock:
        _store.pop(key, None)


def invalidate_prefix(prefix: str):
    """Remove all entries whose key starts with prefix."""
    with _lock:
        keys = [k for k in _store if k.startswith(prefix)]
        for k in keys:
            del _store[k]


def clear():
    """Clear entire cache."""
    with _lock:
        _store.clear()
