"""Unit tests for cache infrastructure: InMemoryCache and RedisCache resilience."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

import core.infra.cache as cache_mod
from core.infra.cache import InMemoryCache, RedisCache, get_cache


def test_in_memory_cache_crud_and_ttl():
    cache = InMemoryCache()
    # Non-existent
    assert cache.get("key1") is None

    # Set and Get
    cache.set("key1", {"data": 123}, ttl_seconds=10)
    assert cache.get("key1") == {"data": 123}

    # Delete
    cache.delete("key1")
    assert cache.get("key1") is None

    # TTL Expiry
    cache.set("short_lived", "value", ttl_seconds=0)  # expires immediately
    time.sleep(0.01)
    assert cache.get("short_lived") is None

    # Clear
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_redis_cache_connection_failure():
    # If redis connection fails or redis is not installed, it should log warning and mark self._connected = False
    mock_redis = MagicMock()
    mock_redis.from_url.side_effect = Exception("Redis connection refused")
    with patch.dict("sys.modules", {"redis": mock_redis}):
        rc = RedisCache("redis://localhost:6379/0")
        assert rc._connected is False

        # Should fall back to in-memory cache transparently
        rc.set("key_fallback", "val", ttl_seconds=60)
        assert rc.get("key_fallback") == "val"
        rc.delete("key_fallback")
        assert rc.get("key_fallback") is None
        rc.set("key_clear", "val")
        rc.clear()
        assert rc.get("key_clear") is None


def test_redis_cache_connected_success():
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = json.dumps({"test": 42})

    mock_redis = MagicMock()
    mock_redis.from_url.return_value = mock_client

    with patch.dict("sys.modules", {"redis": mock_redis}):
        rc = RedisCache("redis://localhost:6379/0")
        assert rc._connected is True

        # GET
        val = rc.get("some_key")
        assert val == {"test": 42}
        mock_client.get.assert_called_with("some_key")

        # GET None
        mock_client.get.return_value = None
        assert rc.get("missing_key") is None

        # SET
        rc.set("some_key", {"foo": "bar"}, ttl_seconds=120)
        mock_client.setex.assert_called_with("some_key", 120, json.dumps({"foo": "bar"}))

        # DELETE
        rc.delete("some_key")
        mock_client.delete.assert_called_with("some_key")

        # CLEAR
        rc.clear()
        mock_client.flushdb.assert_called_once()


def test_redis_cache_runtime_errors_fall_back_to_in_memory():
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    # Simulate Redis throwing errors during operations
    mock_client.get.side_effect = RuntimeError("Redis timeout")
    mock_client.setex.side_effect = RuntimeError("Redis full")
    mock_client.delete.side_effect = RuntimeError("Redis err")
    mock_client.flushdb.side_effect = RuntimeError("Redis err")

    mock_redis = MagicMock()
    mock_redis.from_url.return_value = mock_client

    with patch.dict("sys.modules", {"redis": mock_redis}):
        rc = RedisCache("redis://localhost:6379/0")
        assert rc._connected is True

        # SET falls back to memory
        rc.set("safe_key", "safe_val")
        # GET falls back to memory and retrieves the stored fallback value!
        assert rc.get("safe_key") == "safe_val"

        # DELETE falls back to memory
        rc.delete("safe_key")
        assert rc.get("safe_key") is None

        # CLEAR falls back to memory
        rc.set("k1", "v1")
        rc.clear()
        assert rc.get("k1") is None


def test_get_cache_factory():
    # Reset global cache
    cache_mod._global_cache = None

    # 1. Without REDIS_URL -> InMemoryCache
    with patch.dict("os.environ", {"REDIS_URL": ""}):
        c1 = get_cache()
        assert isinstance(c1, InMemoryCache)
        # Calling again returns cached instance
        assert get_cache() is c1

    # 2. With REDIS_URL -> RedisCache
    cache_mod._global_cache = None
    mock_redis = MagicMock()
    mock_redis.from_url.side_effect = Exception("mock err")
    with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379/1"}), \
         patch.dict("sys.modules", {"redis": mock_redis}):
        c2 = get_cache()
        assert isinstance(c2, RedisCache)
        assert get_cache() is c2

    # Clean up
    cache_mod._global_cache = None
