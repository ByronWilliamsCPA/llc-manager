"""Tests for the break-glass login at /auth/local-login."""

from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

import httpx
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from pydantic import SecretStr

from llc_manager.auth import routes
from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.main import create_app
from tests.auth_helpers import decode_session_cookie, session_cookie_value

if TYPE_CHECKING:
    from fastapi import FastAPI

pytestmark = [pytest.mark.unit, pytest.mark.security]

PASSWORD = "correct horse battery staple"  # pragma: allowlist secret
# Cheap parameters keep the suite fast; verify() reads them from the hash.
_HASH = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
BASE_URL = "https://llc.example.test"
LOGGER_NAME = "llc_manager.auth.routes"


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", BASE_URL)
    monkeypatch.setattr(settings, "local_admin_enabled", True)
    monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(_HASH))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(
        create_app(), base_url=BASE_URL, follow_redirects=False
    ) as test_client:
        yield test_client


def _token(client: TestClient, path: str = "/auth/local-login") -> str:
    """Load the form (which seeds the session token) and read the hidden field."""
    html = client.get(path).text
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


def _submit(
    client: TestClient, password: str, token: str, next_: str = ""
) -> httpx.Response:
    data = {"password": password, "csrf_token": token}
    if next_:
        data["next"] = next_
    return client.post("/auth/local-login", data=data)


def _session(client: TestClient) -> dict[str, object]:
    return decode_session_cookie(settings.secret_key, client.cookies[SESSION_COOKIE])


class TestDisabled:
    def test_get_is_404_by_default(self, client: TestClient) -> None:
        assert client.get("/auth/local-login").status_code == 404

    def test_post_is_404_before_csrf_is_even_checked(self, client: TestClient) -> None:
        assert (
            client.post("/auth/local-login", data={"password": "x"}).status_code == 404
        )

    def test_enabled_without_a_hash_is_still_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "local_admin_enabled", True)
        monkeypatch.setattr(settings, "local_admin_password_hash", None)

        assert client.get("/auth/local-login").status_code == 404

    def test_hash_without_the_switch_is_still_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "local_admin_enabled", False)
        monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(_HASH))

        assert client.get("/auth/local-login").status_code == 404

    def test_a_correct_password_cannot_sign_in_while_disabled(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/auth/local-login", data={"password": PASSWORD, "csrf_token": "x"}
        )

        assert response.status_code == 404
        assert SESSION_COOKIE not in client.cookies


@pytest.mark.usefixtures("enabled")
class TestEnabled:
    def test_form_is_shown_with_a_csrf_token(self, client: TestClient) -> None:
        response = client.get("/auth/local-login")

        assert response.status_code == 200
        assert 'type="password"' in response.text
        assert _token(client)

    def test_correct_password_signs_in_as_admin(self, client: TestClient) -> None:
        token = _token(client)

        response = _submit(client, PASSWORD, token, next_="/entities/3")

        assert response.status_code == 303
        assert response.headers["location"] == "/entities/3"
        session = decode_session_cookie(
            settings.secret_key, client.cookies[SESSION_COOKIE]
        )
        assert session["user"]["role"] == "admin"
        assert session["user"]["auth_method"] == "local"
        assert session["csrf"] != token  # rotated on login

    def test_session_is_rebuilt_not_reused_on_success(self, client: TestClient) -> None:
        token = "planted-csrf-token"  # pragma: allowlist secret
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(
                settings.secret_key, {"csrf": token, "planted": "attacker-value"}
            ),
            domain="llc.example.test",
        )

        response = _submit(client, PASSWORD, token)

        assert response.status_code == 303
        session = _session(client)
        assert "planted" not in session
        assert session["csrf"] != token
        assert "user" in session

    def test_unsafe_next_is_replaced(self, client: TestClient) -> None:
        response = _submit(client, PASSWORD, _token(client), next_="//evil.example")

        assert response.headers["location"] == "/entities"

    def test_next_into_the_auth_prefix_is_replaced(self, client: TestClient) -> None:
        response = _submit(client, PASSWORD, _token(client), next_="/auth/logout")

        assert response.headers["location"] == "/entities"

    def test_wrong_password_is_rejected(self, client: TestClient) -> None:
        response = _submit(client, "wrong", _token(client))

        assert response.status_code == 401
        assert "not correct" in response.text
        assert "user" not in _session(client)

    def test_failed_form_keeps_a_safe_next_for_the_retry(
        self, client: TestClient
    ) -> None:
        response = _submit(client, "wrong", _token(client), next_="/entities/5")

        assert 'name="next" value="/entities/5"' in response.text

    def test_failed_form_does_not_echo_an_unsafe_next(self, client: TestClient) -> None:
        response = _submit(client, "wrong", _token(client), next_="//evil.example")

        assert "evil.example" not in response.text

    def test_missing_csrf_token_is_rejected(self, client: TestClient) -> None:
        _token(client)

        response = client.post("/auth/local-login", data={"password": PASSWORD})

        assert response.status_code == 403
        assert "user" not in _session(client)

    def test_wrong_csrf_token_is_rejected(self, client: TestClient) -> None:
        _token(client)

        response = _submit(client, PASSWORD, "not-the-session-token")

        assert response.status_code == 403
        assert "user" not in _session(client)

    def test_corrupt_stored_hash_fails_closed(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            settings, "local_admin_password_hash", SecretStr("not-an-argon2-hash")
        )

        response = _submit(client, PASSWORD, _token(client))

        assert response.status_code == 401

    def test_signed_in_user_is_sent_on(self, client: TestClient) -> None:
        _submit(client, PASSWORD, _token(client))

        response = client.get("/auth/local-login?next=/entities/9")

        assert response.status_code == 303
        assert response.headers["location"] == "/entities/9"


@pytest.mark.usefixtures("enabled")
class TestVerificationPath:
    @pytest.mark.parametrize("corrupt", ["not-an-argon2-hash", "$argon2id$corrupt"])
    def test_a_corrupt_hash_still_costs_a_real_verification(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, corrupt: str
    ) -> None:
        """The failure path must not return faster than a normal wrong password."""
        monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(corrupt))
        verified: list[str] = []
        real_verify = routes.PasswordHasher.verify

        def spy(self: PasswordHasher, hash_: str | bytes, password: str) -> bool:
            verified.append(hash_ if isinstance(hash_, str) else hash_.decode())
            return real_verify(self, hash_, password)

        monkeypatch.setattr(routes.PasswordHasher, "verify", spy)

        response = _submit(client, PASSWORD, _token(client))

        assert response.status_code == 401
        assert verified[0] == corrupt
        assert len(verified) == 2  # the dummy verification ran as well
        assert verified[1] != verified[0]

    def test_the_attempt_is_counted_before_the_hash_is_checked(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent guesses must not all pass the throttle check first."""
        throttle = cast("FastAPI", client.app).state.login_throttle
        seen: list[int] = []
        real_verify = routes.PasswordHasher.verify

        def spy(self: PasswordHasher, hash_: str | bytes, password: str) -> bool:
            seen.append(throttle.tracked_clients)
            return real_verify(self, hash_, password)

        monkeypatch.setattr(routes.PasswordHasher, "verify", spy)

        _submit(client, "wrong", _token(client))

        assert seen == [1]


@pytest.mark.usefixtures("enabled")
class TestRateLimit:
    def test_sixth_attempt_is_throttled_even_with_the_right_password(
        self, client: TestClient
    ) -> None:
        token = _token(client)
        for _ in range(5):
            assert _submit(client, "wrong", token).status_code == 401

        response = _submit(client, PASSWORD, token)

        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
        assert "user" not in _session(client)

    def test_the_fifth_attempt_is_still_allowed(self, client: TestClient) -> None:
        token = _token(client)
        for _ in range(4):
            assert _submit(client, "wrong", token).status_code == 401

        assert _submit(client, PASSWORD, token).status_code == 303

    def test_throttle_is_per_client_ip(self) -> None:
        app = create_app()
        with TestClient(
            app, base_url=BASE_URL, follow_redirects=False, client=("10.0.0.1", 1)
        ) as first:
            token = _token(first)
            for _ in range(5):
                _submit(first, "wrong", token)
            assert _submit(first, PASSWORD, token).status_code == 429
        with TestClient(
            app, base_url=BASE_URL, follow_redirects=False, client=("10.0.0.2", 1)
        ) as second:
            assert _submit(second, PASSWORD, _token(second)).status_code == 303

    def test_success_clears_earlier_failures(self, client: TestClient) -> None:
        # Kept under the app-wide burst limit (10 requests per second).
        token = _token(client)
        for _ in range(3):
            _submit(client, "wrong", token)
        assert _submit(client, PASSWORD, token).status_code == 303

        client.cookies.clear()
        token = _token(client)
        for _ in range(3):  # 3 + 3 > 5, so only a reset keeps these at 401
            assert _submit(client, "wrong", token).status_code == 401

    def test_success_clears_only_that_clients_failures(self) -> None:
        app = create_app()
        throttle = app.state.login_throttle
        with (
            TestClient(
                app, base_url=BASE_URL, follow_redirects=False, client=("10.0.0.1", 1)
            ) as first,
            TestClient(
                app, base_url=BASE_URL, follow_redirects=False, client=("10.0.0.2", 1)
            ) as second,
        ):
            token_first = _token(first)
            token_second = _token(second)
            for _ in range(3):
                _submit(first, "wrong", token_first)
                _submit(second, "wrong", token_second)

            assert _submit(second, PASSWORD, token_second).status_code == 303

            assert not throttle.is_blocked("10.0.0.1")
            for _ in range(2):  # the first client still has its 3 failures
                assert _submit(first, "wrong", token_first).status_code == 401
            assert throttle.is_blocked("10.0.0.1")
            assert _submit(first, PASSWORD, token_first).status_code == 429


@pytest.mark.usefixtures("enabled")
class TestLogging:
    def test_every_attempt_is_logged_at_warning(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        token = _token(client)
        caplog.set_level("WARNING")

        _submit(client, "wrong", token)
        _submit(client, PASSWORD, token)

        records = [r for r in caplog.records if r.name == LOGGER_NAME]
        text = " ".join(r.getMessage() for r in records)
        assert "local_login_failed" in text
        assert "local_login_succeeded" in text
        assert all(r.levelname == "WARNING" for r in records)

    def test_attempts_carry_the_correlation_id(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        token = _token(client)
        caplog.set_level("WARNING")

        client.post(
            "/auth/local-login",
            data={"password": "wrong", "csrf_token": token},  # pragma: allowlist secret
            headers={"X-Correlation-ID": "corr-failed-0001"},
        )
        client.post(
            "/auth/local-login",
            data={"password": PASSWORD, "csrf_token": token},
            headers={"X-Correlation-ID": "corr-succeeded-0002"},
        )

        assert "corr-failed-0001" in caplog.text
        assert "corr-succeeded-0002" in caplog.text

    def test_passwords_are_never_logged(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("DEBUG")

        _submit(client, "wrong-password-marker", _token(client))
        _submit(client, PASSWORD, _token(client))

        assert "wrong-password-marker" not in caplog.text
        assert PASSWORD not in caplog.text
        assert _HASH not in caplog.text

    def test_a_corrupt_hash_is_never_logged(
        self,
        client: TestClient,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        corrupt = "$argon2id$corrupt-hash-marker"  # pragma: allowlist secret
        monkeypatch.setattr(settings, "local_admin_password_hash", SecretStr(corrupt))
        caplog.set_level("DEBUG")

        _submit(client, PASSWORD, _token(client))

        assert "corrupt-hash-marker" not in caplog.text
        assert PASSWORD not in caplog.text

    def test_throttled_attempts_are_logged(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        token = _token(client)
        for _ in range(5):
            _submit(client, "wrong", token)
        caplog.set_level("WARNING")

        _submit(client, "wrong", token)

        assert "local_login_throttled" in caplog.text


class _Down:
    async def authorize_redirect(self, *_a: object, **_k: object) -> None:
        message = "down"
        raise httpx.ConnectError(message)


class TestOutagePageLink:
    def test_link_is_hidden_when_break_glass_is_off(self, client: TestClient) -> None:
        cast("FastAPI", client.app).state.oidc_client = _Down()

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert "/auth/local-login" not in response.text

    @pytest.mark.usefixtures("enabled")
    def test_link_is_shown_when_break_glass_is_on(self, client: TestClient) -> None:
        cast("FastAPI", client.app).state.oidc_client = _Down()

        response = client.get("/auth/login")

        assert response.status_code == 503
        assert 'href="/auth/local-login"' in response.text
