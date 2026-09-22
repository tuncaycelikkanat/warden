"""Caching infrastructure with in-memory TTL and optional Redis support."""

import json
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseCache(ABC):
    """Abstract cache interface for audit results and scanner outputs."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Retrieves a cached value by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Stores a value with a time-to-live in seconds."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Deletes a key from cache."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clears all cached entries."""
        pass


class InMemoryCache(BaseCache):
    """Thread-safe in-memory cache with TTL expiration."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            if key not in self._store:
                return None
            val, expires_at = self._store[key]
            if now > expires_at:
                del self._store[key]
                return None
            return val

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        expires_at = time.time() + ttl_seconds
        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class RedisCache(BaseCache):
    """Redis-backed distributed cache with in-memory fallback on connection failure."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._fallback = InMemoryCache()
        self._client: Any = None
        self._connected = False
        self._connect()

    def _connect(self) -> None:
        try:
            import redis
            self._client = redis.from_url(self.redis_url, socket_timeout=2)
            self._client.ping()
            self._connected = True
            logger.info("Connected to Redis cache successfully.")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Falling back to InMemoryCache.")
            self._connected = False

    def get(self, key: str) -> Any | None:
        if not self._connected:
            return self._fallback.get(key)
        try:
            val = self._client.get(key)
            if val is not None:
                return json.loads(val)
            return None
        except Exception:
            return self._fallback.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        if not self._connected:
            self._fallback.set(key, value, ttl_seconds)
            return
        try:
            serialized = json.dumps(value)
            self._client.setex(key, ttl_seconds, serialized)
        except Exception:
            self._fallback.set(key, value, ttl_seconds)

    def delete(self, key: str) -> None:
        if not self._connected:
            self._fallback.delete(key)
            return
        try:
            self._client.delete(key)
        except Exception:
            self._fallback.delete(key)

    def clear(self) -> None:
        if not self._connected:
            self._fallback.clear()
            return
        try:
            self._client.flushdb()
        except Exception:
            self._fallback.clear()


_global_cache: BaseCache | None = None
_cache_lock = threading.Lock()


def get_cache() -> BaseCache:
    """Returns the globally configured cache (Redis if REDIS_URL is set, else InMemoryCache)."""
    global _global_cache
    if _global_cache is not None:
        return _global_cache

    with _cache_lock:
        if _global_cache is not None:
            return _global_cache

        redis_url = os.getenv("REDIS_URL", "").strip()
        if redis_url:
            _global_cache = RedisCache(redis_url)
        else:
            _global_cache = InMemoryCache()

        return _global_cache
