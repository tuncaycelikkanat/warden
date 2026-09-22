"""Tests for caching infrastructure."""

import time
import pytest

from core.infra.cache import InMemoryCache, RedisCache, get_cache


class TestInMemoryCache:
    def test_set_and_get(self) -> None:
        cache = InMemoryCache()
        cache.set("foo", {"bar": 123}, ttl_seconds=60)
        assert cache.get("foo") == {"bar": 123}

    def test_get_nonexistent(self) -> None:
        cache = InMemoryCache()
        assert cache.get("missing") is None

    def test_ttl_expiration(self) -> None:
        cache = InMemoryCache()
        cache.set("quick", "value", ttl_seconds=0.01)  # 10ms TTL
        time.sleep(0.02)
        assert cache.get("quick") is None

    def test_delete(self) -> None:
        cache = InMemoryCache()
        cache.set("key", "val", ttl_seconds=60)
        cache.delete("key")
        assert cache.get("key") is None

    def test_clear(self) -> None:
        cache = InMemoryCache()
        cache.set("k1", 1)
        cache.set("k2", 2)
        cache.clear()
        assert cache.get("k1") is None
        assert cache.get("k2") is None


class TestRedisFallback:
    def test_redis_fallback_when_unreachable(self) -> None:
        # Invalid Redis port/host should safely fall back to InMemoryCache
        cache = RedisCache("redis://localhost:9999/0")
        cache.set("test_key", "test_value", ttl_seconds=60)
        assert cache.get("test_key") == "test_value"

    def test_get_cache_factory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REDIS_URL", raising=False)
        cache = get_cache()
        assert cache is not None
        cache.set("global_key", "global_val")
        assert cache.get("global_key") == "global_val"
