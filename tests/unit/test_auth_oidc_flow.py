"""Tests for /auth/login, /auth/callback and /auth/logout with a fake provider."""

import base64
import hashlib
import json
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from llc_manager.auth.oidc import (
    build_oidc_client,
    discovery_url,
    issuer_claims_options,
    redirect_uri,
)
from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.main import create_app
from tests.auth_helpers import (
    TEST_CSRF_TOKEN,
    decode_session_cookie,
    session_cookie_value,
    user_session,
)
from tests.oidc_fake import CLIENT_ID, ISSUER, REDIRECT_URI, FakeProvider

if TYPE_CHECKING:
    from fastapi import FastAPI

pytestmark = [pytest.mark.unit, pytest.mark.security]

BASE_URL = "https://llc.example.test"


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


def _configure(monkeypatch: pytest.MonkeyPatch, base_url: str) -> None:
    monkeypatch.setattr(settings, "public_base_url", base_url)
    monkeypatch.setattr(settings, "authentik_issuer", ISSUER)
    monkeypatch.setattr(settings, "authentik_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "authentik_client_secret", SecretStr("s"))


@pytest.fixture
def client(
    provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    _configure(monkeypatch, BASE_URL)
    app = create_app()
    app.state.oidc_client = provider.client
    with TestClient(app, base_url=BASE_URL, follow_redirects=False) as test_client:
        yield test_client


def _start_login(client: TestClient, provider: FakeProvider, next_: str | None = None):
    url = "/auth/login" if next_ is None else f"/auth/login?next={next_}"
    response = client.get(url)
    assert response.status_code == 302
    params = provider.remember_authorization(response.headers["location"])
    return response, params


def _finish_login(
    client: TestClient, provider: FakeProvider, params: dict[str, str], **claims: Any
):
    provider.next_claims = provider.claims(**claims)
    return client.get("/auth/callback", params={"code": "c", "state": params["state"]})


class TestLogin:
    def test_redirects_to_provider_with_state_nonce_and_pkce(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        response, params = _start_login(client, provider)

        assert response.headers["location"].startswith(
            "https://auth.example.test/authorize/?"
        )
        assert params["client_id"] == CLIENT_ID
        assert params["redirect_uri"] == REDIRECT_URI
        assert params["response_type"] == "code"
        assert params["scope"] == "openid profile email"
        assert params["code_challenge_method"] == "S256"
        assert params["state"]
        assert params["nonce"]

    def test_redirect_uri_ignores_the_request_host(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        response = client.get("/auth/login", headers={"Host": "evil.example"})
        params = provider.remember_authorization(response.headers["location"])

        assert params["redirect_uri"] == REDIRECT_URI

    def test_session_cookie_is_hardened(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        response, _ = _start_login(client, provider)

        cookie = response.headers["set-cookie"].lower()
        assert f"{SESSION_COOKIE}=" in cookie
        assert "httponly" in cookie
        assert "secure" in cookie
        assert "samesite=lax" in cookie
        assert "max-age=28800" in cookie

    def test_session_cookie_is_secure_for_a_plain_http_url_outside_development(
        self, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, "http://localhost:8000")
        monkeypatch.setattr(settings, "environment", None)
        app = create_app()
        app.state.oidc_client = provider.client
        with TestClient(app, follow_redirects=False) as local_client:
            response = local_client.get("/auth/login")

        assert "secure" in response.headers["set-cookie"].lower()

    def test_session_cookie_is_not_secure_for_a_plain_http_public_url(
        self, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, "http://localhost:8000")
        monkeypatch.setattr(settings, "environment", "development")
        app = create_app()
        app.state.oidc_client = provider.client
        with TestClient(app, follow_redirects=False) as local_client:
            response = local_client.get("/auth/login")

        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "secure" not in cookie

    def test_not_configured_shows_unavailable_page(self, client: TestClient) -> None:
        cast("FastAPI", client.app).state.oidc_client = None

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert "not configured" in response.text
        assert "set-cookie" not in response.headers

    def test_provider_outage_during_discovery_shows_retry_page(
        self, client: TestClient
    ) -> None:
        class _Unreachable:
            async def authorize_redirect(self, *_args: Any, **_kwargs: Any) -> None:
                raise httpx.ConnectError("discovery failed")

        cast("FastAPI", client.app).state.oidc_client = _Unreachable()

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert "temporarily unavailable" in response.text

    def test_garbled_discovery_document_shows_retry_page(
        self, client: TestClient
    ) -> None:
        class _Garbled:
            async def authorize_redirect(self, *_args: Any, **_kwargs: Any) -> None:
                raise json.JSONDecodeError("not json", "<html>", 0)

        cast("FastAPI", client.app).state.oidc_client = _Garbled()

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert "temporarily unavailable" in response.text

    def test_already_signed_in_goes_straight_to_next(self, client: TestClient) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("viewer")),
        )

        response = client.get("/auth/login?next=/entities/1")

        assert response.status_code == 303
        assert response.headers["location"] == "/entities/1"

    def test_already_signed_in_with_hostile_next_goes_to_default(
        self, client: TestClient
    ) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("viewer")),
        )

        response = client.get("/auth/login?next=//evil.example")

        assert response.status_code == 303
        assert response.headers["location"] == "/entities"


class TestCallback:
    def test_admin_login_creates_session_and_returns_to_next(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider, next_="/entities/9?tab=a")

        response = _finish_login(client, provider, params)

        assert response.status_code == 303
        assert response.headers["location"] == "/entities/9?tab=a"
        assert f"{SESSION_COOKIE}=" in response.headers["set-cookie"]

    def test_code_exchange_carries_the_pkce_verifier_and_fixed_redirect_uri(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)

        _finish_login(client, provider, params)

        exchange = provider.last_exchange
        assert exchange["code"] == "c"
        assert exchange["redirect_uri"] == REDIRECT_URI
        digest = hashlib.sha256(exchange["code_verifier"].encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        assert challenge == params["code_challenge"]

    def test_session_after_login_has_role_and_csrf_token(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        _finish_login(client, provider, params, groups=["llc-manager-viewers"])

        session = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )

        assert session["user"]["role"] == "viewer"
        assert session["user"]["email"] == "ada@example.test"
        assert session["user"]["auth_method"] == "oidc"
        assert session["csrf"]
        # Login state (state, nonce, PKCE verifier) must not outlive the login.
        assert sorted(session) == ["csrf", "user"]

    def test_session_is_rebuilt_not_reused_on_callback(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        before = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )

        _finish_login(client, provider, params)
        after = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )

        assert "login_next" in before
        assert "login_next" not in after
        assert not [key for key in after if key.startswith("_state_")]

    def test_non_text_identity_claims_are_not_stored(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)

        response = _finish_login(client, provider, params, email=5, name=["x"])

        assert response.status_code == 303
        session = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )
        assert session["user"]["email"] is None
        assert session["user"]["name"] is None

    def test_unsafe_next_is_replaced_by_default(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider, next_="//evil.example")

        response = _finish_login(client, provider, params)

        assert response.headers["location"] == "/entities"

    def test_unsafe_next_planted_in_the_session_is_replaced_at_callback(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        session = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )
        session["login_next"] = "https://evil.example/"
        client.cookies.set(
            SESSION_COOKIE, session_cookie_value(settings.secret_key, session)
        )

        response = _finish_login(client, provider, params)

        assert response.status_code == 303
        assert response.headers["location"] == "/entities"

    def test_user_without_a_known_group_gets_403_page(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)

        response = _finish_login(client, provider, params, groups=["other"])

        assert response.status_code == 403
        assert "Access denied" in response.text
        session_cookie = response.headers.get("set-cookie", "").lower()
        assert "expires=thu, 01 jan 1970" in session_cookie

    def test_user_without_a_groups_claim_gets_403_page(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)

        response = _finish_login(client, provider, params, groups=None)

        assert response.status_code == 403

    def test_admin_outranks_viewer_in_the_session(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        _finish_login(
            client,
            provider,
            params,
            groups=["llc-manager-viewers", "llc-manager-admins"],
        )

        session = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )

        assert session["user"]["role"] == "admin"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"iss": "https://evil.example/"},
            {"aud": "another-client"},
            {"nonce": "not-the-nonce"},
            {"exp": 1},
            {"exp": None},
            {"sub": None},
        ],
        ids=["issuer", "audience", "nonce", "expired", "no-exp", "no-sub"],
    )
    def test_invalid_id_token_is_rejected_without_a_session(
        self, client: TestClient, provider: FakeProvider, overrides: dict[str, Any]
    ) -> None:
        _, params = _start_login(client, provider)

        response = _finish_login(client, provider, params, **overrides)

        assert response.status_code == 400
        assert "Sign-in failed" in response.text
        assert "user" not in response.headers.get("set-cookie", "")

    def test_state_mismatch_is_rejected(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _start_login(client, provider)
        provider.next_claims = provider.claims()

        response = client.get("/auth/callback", params={"code": "c", "state": "forged"})

        assert response.status_code == 400

    def test_callback_without_a_login_attempt_is_rejected(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        provider.next_claims = provider.claims()

        response = client.get("/auth/callback", params={"code": "c", "state": "x"})

        assert response.status_code == 400

    def test_callback_without_state_is_rejected(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _start_login(client, provider)
        provider.next_claims = provider.claims()

        response = client.get("/auth/callback", params={"code": "c"})

        assert response.status_code == 400

    def test_provider_error_response_is_rejected(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)

        response = client.get(
            "/auth/callback",
            params={"error": "access_denied", "state": params["state"]},
        )

        assert response.status_code == 400

    def test_provider_outage_shows_retry_page(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        provider.fail_with = httpx.ConnectError("boom")

        response = _finish_login(client, provider, params)

        assert response.status_code == 503
        assert "temporarily unavailable" in response.text
        assert 'href="/auth/login"' in response.text

    def test_callback_is_not_blocked_by_the_ssrf_filter(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        provider.next_claims = provider.claims()

        response = client.get(
            "/auth/callback",
            params={"code": "c", "state": params["state"], "iss": ISSUER},
        )

        assert response.status_code == 303

    def test_replayed_state_cannot_log_in_twice(
        self, client: TestClient, provider: FakeProvider
    ) -> None:
        _, params = _start_login(client, provider)
        assert _finish_login(client, provider, params).status_code == 303

        replay = _finish_login(client, provider, params)

        assert replay.status_code == 400


class TestConfiguredIssuerIsEnforced:
    """The ID token issuer is checked against the configured issuer."""

    def _client(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider: FakeProvider,
        configured_issuer: str,
    ) -> TestClient:
        _configure(monkeypatch, BASE_URL)
        monkeypatch.setattr(settings, "authentik_issuer", configured_issuer)
        app = create_app()
        app.state.oidc_client = provider.client
        return TestClient(app, base_url=BASE_URL, follow_redirects=False)

    def test_issuer_from_a_substituted_discovery_document_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        other = "https://other-idp.example.test/application/o/llc-manager/"
        provider = FakeProvider(metadata_issuer=other)
        with self._client(monkeypatch, provider, ISSUER) as client:
            _, params = _start_login(client, provider)

            response = _finish_login(client, provider, params, iss=other)

        assert response.status_code == 400
        assert "user" not in response.headers.get("set-cookie", "")

    @pytest.mark.parametrize(
        "configured", [ISSUER, ISSUER.rstrip("/")], ids=["slash", "no-slash"]
    )
    def test_matching_issuer_is_accepted_whatever_the_trailing_slash(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider: FakeProvider,
        configured: str,
    ) -> None:
        with self._client(monkeypatch, provider, configured) as client:
            _, params = _start_login(client, provider)

            response = _finish_login(client, provider, params)

        assert response.status_code == 303

    @pytest.mark.parametrize(
        "configured", [ISSUER, ISSUER.rstrip("/")], ids=["slash", "no-slash"]
    )
    def test_mismatching_issuer_is_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        provider: FakeProvider,
        configured: str,
    ) -> None:
        with self._client(monkeypatch, provider, configured) as client:
            _, params = _start_login(client, provider)

            response = _finish_login(
                client, provider, params, iss="https://evil.example/"
            )

        assert response.status_code == 400


def test_issuer_claims_options_cover_both_slash_forms() -> None:
    assert issuer_claims_options("https://a.test/o/x/") == {
        "iss": {
            "essential": True,
            "values": ["https://a.test/o/x", "https://a.test/o/x/"],
        }
    }
    assert issuer_claims_options("https://a.test/o/x") == issuer_claims_options(
        "https://a.test/o/x/"
    )


class TestBrokenDiscoveryDocument:
    """A malformed provider document must give the retry page, not a 500."""

    def _client(
        self, monkeypatch: pytest.MonkeyPatch, provider: FakeProvider
    ) -> TestClient:
        _configure(monkeypatch, BASE_URL)
        app = create_app()
        app.state.oidc_client = provider.client
        return TestClient(app, base_url=BASE_URL, follow_redirects=False)

    def test_login_without_an_authorization_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = FakeProvider(with_authorization_endpoint=False)
        with self._client(monkeypatch, provider) as client:
            response = client.get("/auth/login")

        assert response.status_code == 503
        assert "temporarily unavailable" in response.text

    def test_callback_without_a_jwks_uri(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = FakeProvider(with_jwks=False)
        with self._client(monkeypatch, provider) as client:
            _, params = _start_login(client, provider)

            response = _finish_login(client, provider, params)

        assert response.status_code == 503
        assert "temporarily unavailable" in response.text
        assert "user" not in response.headers.get("set-cookie", "")

    @pytest.mark.parametrize("error", [RuntimeError("x"), KeyError("token_endpoint")])
    def test_stub_failures_on_both_routes(
        self, client: TestClient, error: Exception
    ) -> None:
        class _Broken:
            async def authorize_redirect(self, *_args: Any, **_kwargs: Any) -> None:
                raise error

            async def authorize_access_token(self, *_args: Any, **_kwargs: Any) -> None:
                raise error

        cast("FastAPI", client.app).state.oidc_client = _Broken()

        login = client.get("/auth/login")
        callback = client.get("/auth/callback", params={"code": "c", "state": "s"})

        assert login.status_code == 503
        assert callback.status_code == 503


class TestLogout:
    def test_logout_requires_csrf_token(self, client: TestClient) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("admin")),
        )

        assert client.post("/auth/logout").status_code == 403

    def test_logout_clears_the_session(self, client: TestClient) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("admin")),
        )

        response = client.post("/auth/logout", data={"csrf_token": TEST_CSRF_TOKEN})

        assert response.status_code == 200
        assert "Signed out" in response.text
        # An emptied session makes Starlette expire the cookie in the browser.
        assert "expires=thu, 01 jan 1970" in response.headers["set-cookie"].lower()

    def test_get_logout_is_not_allowed(self, client: TestClient) -> None:
        assert client.get("/auth/logout").status_code == 405


class TestClientConstruction:
    def test_discovery_url_handles_trailing_slash(self) -> None:
        assert (
            discovery_url("https://a.test/o/x/")
            == "https://a.test/o/x/.well-known/openid-configuration"
        )
        assert (
            discovery_url("https://a.test/o/x")
            == "https://a.test/o/x/.well-known/openid-configuration"
        )

    def test_redirect_uri_is_under_the_public_origin(self) -> None:
        assert redirect_uri("https://llc.example.test") == REDIRECT_URI

    def test_no_client_when_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "authentik_issuer", None)

        assert build_oidc_client(settings) is None

    def test_client_is_built_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure(monkeypatch, BASE_URL)

        assert build_oidc_client(settings) is not None
