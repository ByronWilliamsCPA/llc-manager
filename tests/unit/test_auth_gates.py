"""Tests for the gate dependencies, using a throwaway app.

The gates are defined here but not yet attached to the real web routes, so
they are exercised against a minimal FastAPI app with the same session
middleware settings as the real one.
"""

from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from llc_manager.auth.csrf import verify_csrf
from llc_manager.auth.dependencies import require_admin, require_user
from llc_manager.auth.session import SESSION_COOKIE, SessionUser
from llc_manager.core.config import settings
from tests.auth_helpers import (
    TEST_CSRF_TOKEN,
    session_cookie_value,
    user_session,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]

SECRET = "x" * 40  # pragma: allowlist secret


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware, secret_key=SECRET, session_cookie=SESSION_COOKIE
    )

    @app.get("/page")
    async def page(
        user: Annotated[SessionUser, Depends(require_user)],
    ) -> dict[str, str]:
        return {"sub": user.sub, "role": user.role.value}

    @app.get("/admin-page")
    async def admin_page(
        user: Annotated[SessionUser, Depends(require_admin)],
    ) -> dict[str, str]:
        return {"sub": user.sub}

    @app.get("/read", dependencies=[Depends(verify_csrf)])
    async def read() -> dict[str, bool]:
        return {"read": True}

    @app.post("/change", dependencies=[Depends(verify_csrf)])
    async def change() -> dict[str, bool]:
        return {"changed": True}

    @app.patch("/change", dependencies=[Depends(verify_csrf)])
    async def change_patch() -> dict[str, bool]:
        return {"changed": True}

    @app.post("/guarded", dependencies=[Depends(require_user)])
    async def guarded() -> dict[str, bool]:
        return {"ran": True}

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(_build_app(), follow_redirects=False) as test_client:
        yield test_client


def _sign_in(client: TestClient, role: str = "admin", **kwargs: float) -> None:
    client.cookies.set(
        SESSION_COOKIE, session_cookie_value(SECRET, user_session(role, **kwargs))
    )


class TestRequireUser:
    def test_page_request_without_session_redirects_to_login(
        self, client: TestClient
    ) -> None:
        response = client.get("/page?x=1")

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login?next=%2Fpage%3Fx%3D1"

    def test_htmx_request_gets_401_with_hx_redirect(self, client: TestClient) -> None:
        response = client.get(
            "/page",
            headers={
                "HX-Request": "true",
                "HX-Current-URL": "http://testserver/entities/42?tab=a",
            },
        )

        assert response.status_code == 401
        assert response.headers["hx-redirect"] == (
            "/auth/login?next=%2Fentities%2F42%3Ftab%3Da"
        )
        assert "location" not in response.headers

    def test_hostile_hx_current_url_falls_back_to_default(
        self, client: TestClient
    ) -> None:
        response = client.get(
            "/page",
            headers={"HX-Request": "true", "HX-Current-URL": "http://x//evil.example"},
        )

        assert response.headers["hx-redirect"] == "/auth/login?next=%2Fentities"

    @pytest.mark.parametrize(
        "current_url",
        ["http://[", "http://[::1", "http://[1/entities", "http://x:99999999"],
    )
    def test_malformed_hx_current_url_still_answers_401(
        self, client: TestClient, current_url: str
    ) -> None:
        response = client.get(
            "/page",
            headers={"HX-Request": "true", "HX-Current-URL": current_url},
        )

        assert response.status_code == 401
        assert response.headers["hx-redirect"] == "/auth/login?next=%2Fentities"

    def test_non_get_request_does_not_remember_its_path(
        self, client: TestClient
    ) -> None:
        response = client.post("/guarded?secret=1")

        assert response.status_code == 303
        assert response.headers["location"] == "/auth/login?next=%2Fentities"

    def test_valid_session_passes(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        response = client.get("/page")

        assert response.status_code == 200
        assert response.json() == {"sub": "test-viewer", "role": "viewer"}

    def test_expired_session_is_signed_out(self, client: TestClient) -> None:
        _sign_in(client, exp_in=-5)

        assert client.get("/page").status_code == 303

    def test_session_signed_with_another_key_is_rejected(
        self, client: TestClient
    ) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value("y" * 40, user_session("admin")),
        )

        assert client.get("/page").status_code == 303

    def test_dev_mode_acts_as_admin_without_a_session(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "auth_dev_mode", True)

        response = client.get("/admin-page")

        assert response.status_code == 200
        assert response.json() == {"sub": "dev-user"}


class TestRequireAdmin:
    def test_admin_passes(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        assert client.get("/admin-page").status_code == 200

    def test_viewer_is_forbidden(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        assert client.get("/admin-page").status_code == 403

    def test_anonymous_is_sent_to_login_not_403(self, client: TestClient) -> None:
        assert client.get("/admin-page").status_code == 303


class TestVerifyCsrf:
    def test_safe_methods_need_no_token(self, client: TestClient) -> None:
        assert client.get("/page").status_code == 303  # gate, not CSRF

    def test_get_is_exempt_even_without_a_session_or_token(
        self, client: TestClient
    ) -> None:
        response = client.get("/read")

        assert response.status_code == 200
        assert response.json() == {"read": True}

    def test_get_is_exempt_for_a_signed_in_user_without_a_token(
        self, client: TestClient
    ) -> None:
        _sign_in(client)

        assert client.get("/read").status_code == 200

    def test_header_token_is_accepted(self, client: TestClient) -> None:
        _sign_in(client)

        response = client.patch("/change", headers={"X-CSRF-Token": TEST_CSRF_TOKEN})

        assert response.status_code == 200

    def test_form_field_token_is_accepted(self, client: TestClient) -> None:
        _sign_in(client)

        response = client.post("/change", data={"csrf_token": TEST_CSRF_TOKEN})

        assert response.status_code == 200

    def test_anonymous_post_is_rejected(self, client: TestClient) -> None:
        assert client.post("/change").status_code == 403

    @pytest.mark.parametrize("token", [None, "", "wrong", TEST_CSRF_TOKEN + "x"])
    def test_missing_or_wrong_token_is_rejected(
        self, client: TestClient, token: str | None
    ) -> None:
        _sign_in(client)
        headers = {} if token is None else {"X-CSRF-Token": token}

        assert client.post("/change", headers=headers).status_code == 403

    def test_session_without_a_token_rejects_everything(
        self, client: TestClient
    ) -> None:
        payload = user_session()
        del payload["csrf"]
        client.cookies.set(SESSION_COOKIE, session_cookie_value(SECRET, payload))

        response = client.post("/change", headers={"X-CSRF-Token": "anything"})

        assert response.status_code == 403

    def test_json_body_does_not_satisfy_the_check(self, client: TestClient) -> None:
        _sign_in(client)

        response = client.post("/change", json={"csrf_token": TEST_CSRF_TOKEN})

        assert response.status_code == 403
