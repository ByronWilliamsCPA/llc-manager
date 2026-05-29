"""Tests for the security middleware stack.

Covers the high-leverage security primitives that ship with the app:

- ``SSRFPreventionMiddleware``: the private-IP / blocked-host / blocked-scheme
  classifier is the SSRF defense choke point, so each branch (IPv4, IPv6,
  IPv4-mapped IPv6, decimal-obfuscated, malformed) is exercised explicitly.
- ``RateLimitMiddleware``: in-memory bookkeeping (cleanup, burst, per-IP cap).
- ``SecurityHeadersMiddleware``: end-to-end check via TestClient that all
  OWASP headers are attached to responses.
- ``add_security_middleware`` / ``SecurityConfig`` configuration helpers.
"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc_manager.middleware.security import (
    RateLimitMiddleware,
    SecurityConfig,
    SecurityHeadersMiddleware,
    SSRFPreventionMiddleware,
    add_security_middleware,
)


class TestIsPrivateIP:
    """SSRFPreventionMiddleware._is_private_ip classifies IPs as internal."""

    @pytest.mark.unit
    def test_loopback_v4_is_private(self) -> None:
        assert SSRFPreventionMiddleware._is_private_ip("127.0.0.1") is True

    @pytest.mark.unit
    def test_rfc1918_10_is_private(self) -> None:
        assert SSRFPreventionMiddleware._is_private_ip("10.0.0.1") is True

    @pytest.mark.unit
    def test_rfc1918_192_is_private(self) -> None:
        assert SSRFPreventionMiddleware._is_private_ip("192.168.1.1") is True

    @pytest.mark.unit
    def test_link_local_metadata_is_private(self) -> None:
        """AWS instance metadata service must be classified internal."""
        assert SSRFPreventionMiddleware._is_private_ip("169.254.169.254") is True

    @pytest.mark.unit
    def test_unspecified_is_private(self) -> None:
        assert SSRFPreventionMiddleware._is_private_ip("0.0.0.0") is True  # noqa: S104

    @pytest.mark.unit
    def test_public_ip_not_private(self) -> None:
        assert SSRFPreventionMiddleware._is_private_ip("8.8.8.8") is False

    @pytest.mark.unit
    def test_ipv6_loopback_is_private(self) -> None:
        assert SSRFPreventionMiddleware._is_private_ip("::1") is True

    @pytest.mark.unit
    def test_ipv4_mapped_ipv6_private_is_private(self) -> None:
        """An RFC1918 v4 inside an IPv6 wrapper must still classify as private."""
        assert SSRFPreventionMiddleware._is_private_ip("::ffff:10.0.0.1") is True

    @pytest.mark.unit
    def test_invalid_string_not_private(self) -> None:
        """Non-IP strings fall through for the hostname checker to handle."""
        assert SSRFPreventionMiddleware._is_private_ip("not-an-ip") is False


class TestExtractHostAndScheme:
    @pytest.mark.unit
    def test_extract_host_returns_hostname(self) -> None:
        assert (
            SSRFPreventionMiddleware._extract_host_from_url("http://example.com/path")
            == "example.com"
        )

    @pytest.mark.unit
    def test_extract_host_returns_ip(self) -> None:
        assert (
            SSRFPreventionMiddleware._extract_host_from_url("http://127.0.0.1:8080")
            == "127.0.0.1"
        )

    @pytest.mark.unit
    def test_extract_scheme_lowercases(self) -> None:
        assert (
            SSRFPreventionMiddleware._extract_scheme_from_url("HTTPS://example.com")
            == "https"
        )

    @pytest.mark.unit
    def test_extract_scheme_no_scheme_returns_none(self) -> None:
        assert SSRFPreventionMiddleware._extract_scheme_from_url("example.com") is None


class TestIsBlockedURL:
    """The end-to-end SSRF classification used by the middleware dispatch."""

    @pytest.mark.unit
    def test_blocks_file_scheme(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("file:///etc/passwd") is True

    @pytest.mark.unit
    def test_blocks_gopher_scheme(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("gopher://attacker/payload") is True

    @pytest.mark.unit
    def test_blocks_localhost_host(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("http://localhost/admin") is True

    @pytest.mark.unit
    def test_blocks_aws_metadata(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("http://169.254.169.254/latest/meta-data/") is True

    @pytest.mark.unit
    def test_blocks_gcp_metadata_hostname(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("http://metadata.google.internal/x") is True

    @pytest.mark.unit
    def test_blocks_kubernetes_default(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("http://kubernetes.default.svc/api") is True

    @pytest.mark.unit
    def test_blocks_private_ipv4(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("http://10.0.0.5/internal") is True

    @pytest.mark.unit
    def test_blocks_decimal_obfuscated_loopback(self) -> None:
        """2130706433 decimal == 127.0.0.1 -- must be blocked."""
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("http://2130706433/admin") is True

    @pytest.mark.unit
    def test_allows_public_url(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("https://example.com/data") is False

    @pytest.mark.unit
    def test_no_host_returns_false(self) -> None:
        """Schemeless / hostless inputs are not flagged here."""
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_blocked_url("not a url at all") is False

    @pytest.mark.unit
    def test_obfuscated_check_skips_non_digits(self) -> None:
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_obfuscated_private_ip("example") is False

    @pytest.mark.unit
    def test_obfuscated_check_skips_out_of_range(self) -> None:
        """Numbers larger than a 32-bit IPv4 cannot represent a v4 host."""
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_obfuscated_private_ip("99999999999999999999") is False

    @pytest.mark.unit
    def test_obfuscated_check_returns_false_for_public_decimal(self) -> None:
        """134744072 decimal == 8.8.8.8 -- public, not blocked."""
        mw = SSRFPreventionMiddleware(app=lambda *_: None)
        assert mw._is_obfuscated_private_ip("134744072") is False


class TestSSRFMiddlewareDispatch:
    """End-to-end: SSRF middleware blocks suspicious query parameters."""

    @pytest.fixture
    def client(self) -> TestClient:
        app = FastAPI()
        app.add_middleware(SSRFPreventionMiddleware)

        @app.get("/echo")
        async def echo(target: str | None = None) -> dict[str, str | None]:
            return {"target": target}

        return TestClient(app)

    @pytest.mark.unit
    def test_allows_request_without_url_param(self, client: TestClient) -> None:
        assert client.get("/echo").status_code == 200

    @pytest.mark.unit
    def test_allows_public_url_param(self, client: TestClient) -> None:
        assert (
            client.get("/echo", params={"target": "https://example.com"}).status_code
            == 200
        )

    @pytest.mark.unit
    def test_blocks_private_url_param(self, client: TestClient) -> None:
        resp = client.get("/echo", params={"target": "http://10.0.0.1/secret"})
        assert resp.status_code == 400

    @pytest.mark.unit
    def test_blocks_metadata_url_param(self, client: TestClient) -> None:
        resp = client.get(
            "/echo", params={"target": "http://169.254.169.254/latest/meta-data/"}
        )
        assert resp.status_code == 400
        assert "SSRF" in resp.json()["message"]


class TestRateLimitMiddleware:
    """RateLimitMiddleware's request bookkeeping is in-memory and unit-testable."""

    @pytest.mark.unit
    def test_allows_request_under_limit(self) -> None:
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=60, burst_size=10)

        @app.get("/ping")
        async def ping() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        assert client.get("/ping").status_code == 200

    @pytest.mark.unit
    def test_burst_limit_returns_429(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The 3rd request inside 1s with burst_size=2 must 429.

        Wall-clock time is monkey-patched so the test exercises the burst
        bookkeeping deterministically, regardless of how slow the runner is.
        Each request advances the simulated clock by 0.1 s -- well inside the
        middleware's 1-second burst window.
        """
        fake_now = [1_000_000.0]

        def fake_time() -> float:
            fake_now[0] += 0.1
            return fake_now[0]

        monkeypatch.setattr("llc_manager.middleware.security.time.time", fake_time)

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=100, burst_size=2)

        @app.get("/ping")
        async def ping() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 200
        resp = client.get("/ping")
        assert resp.status_code == 429
        assert resp.headers["Retry-After"] == "1"

    @pytest.mark.unit
    def test_per_minute_limit_returns_429(self) -> None:
        """RPM cap is checked before the burst cap so high RPM trips first."""
        app = FastAPI()
        # burst_size>rpm so the per-minute path fires first.
        app.add_middleware(RateLimitMiddleware, requests_per_minute=2, burst_size=100)

        @app.get("/ping")
        async def ping() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 200
        resp = client.get("/ping")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    @pytest.mark.unit
    def test_cleanup_skipped_before_interval(self) -> None:
        """_cleanup_stale_entries should no-op before cleanup_interval elapses."""
        mw = RateLimitMiddleware(app=lambda *_: None, cleanup_interval=10000)
        mw._last_cleanup = time.time()
        mw.requests["1.1.1.1"].append(time.time())
        mw._cleanup_stale_entries(time.time())
        # Untouched: cleanup interval has not elapsed.
        assert "1.1.1.1" in mw.requests

    @pytest.mark.unit
    def test_cleanup_removes_stale_ips(self) -> None:
        mw = RateLimitMiddleware(app=lambda *_: None, cleanup_interval=0)
        mw._last_cleanup = 0
        # All timestamps are well over 60 seconds old.
        mw.requests["stale.ip"].extend([0.0, 1.0])
        mw.requests["fresh.ip"].append(time.time())
        mw._cleanup_stale_entries(time.time())
        assert "stale.ip" not in mw.requests
        assert "fresh.ip" in mw.requests

    @pytest.mark.unit
    def test_cleanup_enforces_max_tracked_ips(self) -> None:
        """Exceeding max_tracked_ips trims to the LRU window."""
        mw = RateLimitMiddleware(
            app=lambda *_: None, cleanup_interval=0, max_tracked_ips=2
        )
        mw._last_cleanup = 0
        now = time.time()
        mw.requests["ip-a"].append(now - 30)
        mw.requests["ip-b"].append(now - 20)
        mw.requests["ip-c"].append(now - 10)
        mw.requests["ip-d"].append(now - 5)
        mw._cleanup_stale_entries(now)
        # Only the two most recently active IPs survive.
        assert len(mw.requests) <= 2
        assert "ip-d" in mw.requests


class TestSecurityHeadersMiddleware:
    """The OWASP header bundle is added on every response."""

    @pytest.fixture
    def client(self) -> TestClient:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/")
        async def root() -> dict[str, str]:
            return {"status": "ok"}

        return TestClient(app)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "header",
        [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Content-Security-Policy",
            "Referrer-Policy",
            "Permissions-Policy",
        ],
    )
    def test_owasp_headers_present(self, client: TestClient, header: str) -> None:
        assert header in client.get("/").headers

    @pytest.mark.unit
    def test_no_sniff(self, client: TestClient) -> None:
        assert client.get("/").headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.unit
    def test_frame_options_deny(self, client: TestClient) -> None:
        assert client.get("/").headers["X-Frame-Options"] == "DENY"

    @pytest.mark.unit
    def test_hsts_not_added_on_http(self, client: TestClient) -> None:
        """Plain HTTP responses must NOT carry HSTS (per the dispatch logic)."""
        assert "Strict-Transport-Security" not in client.get("/").headers


class TestAddSecurityMiddleware:
    """The add_security_middleware helper wires up the stack idempotently."""

    @pytest.mark.unit
    def test_default_config_runs(self) -> None:
        app = FastAPI()
        add_security_middleware(app)

        @app.get("/")
        async def root() -> dict[str, str]:
            return {"status": "ok"}

        # The app should still accept requests after the middleware stack
        # is wired up with defaults.
        assert TestClient(app).get("/").status_code == 200

    @pytest.mark.unit
    def test_custom_config_with_allowed_hosts(self) -> None:
        app = FastAPI()
        config = SecurityConfig(
            allowed_hosts=["testserver", "example.com"],
            allowed_origins=["https://example.com"],
            rate_limit_rpm=120,
        )
        add_security_middleware(app, config)

        @app.get("/")
        async def root() -> dict[str, str]:
            return {"status": "ok"}

        assert TestClient(app).get("/").status_code == 200

    @pytest.mark.unit
    def test_security_config_defaults(self) -> None:
        config = SecurityConfig()
        assert config.enable_rate_limiting is True
        assert config.enable_ssrf_prevention is True
        assert config.enable_https_redirect is False
        assert config.rate_limit_rpm == 60
        assert config.allowed_origins == []
        assert config.allowed_hosts == []

    @pytest.mark.unit
    def test_disable_optional_middleware(self) -> None:
        app = FastAPI()
        config = SecurityConfig(
            enable_rate_limiting=False, enable_ssrf_prevention=False
        )
        add_security_middleware(app, config)

        @app.get("/")
        async def root() -> dict[str, str]:
            return {"status": "ok"}

        assert TestClient(app).get("/").status_code == 200
