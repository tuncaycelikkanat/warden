"""Tests for SlidingWindowRateLimiter and RateLimitMiddleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.rate_limiter import RateLimitMiddleware, SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    def test_allow_within_limit(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=10)
        for _ in range(5):
            allowed, retry_after = limiter.is_allowed("client-1")
            assert allowed
            assert retry_after == 0

    def test_block_exceeding_limit(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = limiter.is_allowed("client-2")
            assert allowed

        allowed, retry_after = limiter.is_allowed("client-2")
        assert not allowed
        assert retry_after > 0

    def test_separate_clients_tracked_independently(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("client-A")
        limiter.is_allowed("client-A")
        assert not limiter.is_allowed("client-A")[0]

        # client-B should still be allowed
        assert limiter.is_allowed("client-B")[0]


class TestRateLimitMiddlewareIntegration:
    @pytest.fixture
    def test_app(self) -> FastAPI:
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=2, window_seconds=10)

        @app.get("/api/v1/health")
        def health():
            return {"status": "ok"}

        @app.get("/api/v1/resource")
        def resource():
            return {"data": "success"}

        return app

    def test_exempt_route_never_blocked(self, test_app: FastAPI) -> None:
        client = TestClient(test_app)
        # /api/v1/health should not be blocked even after 10 requests
        for _ in range(10):
            res = client.get("/api/v1/health")
            assert res.status_code == 200

    def test_regular_route_blocked_after_limit(self, test_app: FastAPI) -> None:
        client = TestClient(test_app)
        assert client.get("/api/v1/resource").status_code == 200
        assert client.get("/api/v1/resource").status_code == 200

        # 3rd request should return 429
        blocked = client.get("/api/v1/resource")
        assert blocked.status_code == 429
        assert "Too Many Requests" in blocked.json()["error"]
        assert "Retry-After" in blocked.headers
