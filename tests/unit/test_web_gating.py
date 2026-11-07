"""Every web route must be gated; behavior of the gates on the real routes.

The enumeration test is modeled on ``test_every_v1_route_declares_the_key`` in
``tests/unit/test_api_key_auth.py``: a new route that forgets its dependencies
fails here instead of shipping open.
"""

from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from typing import Any, NamedTuple, cast

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import BaseRoute, Mount, Route

from llc_manager.auth.csrf import SAFE_METHODS, verify_csrf
from llc_manager.auth.dependencies import require_admin, require_user
from llc_manager.auth.session import SESSION_COOKIE
from llc_manager.core.config import settings
from llc_manager.db.session import get_async_session
from llc_manager.main import create_app
from tests.auth_helpers import (
    TEST_CSRF_TOKEN,
    session_cookie_value,
    user_session,
)
from tests.unit.test_web_entities import FIXTURE_ID, _make_entity, _StubSession

pytestmark = [pytest.mark.unit, pytest.mark.security]

# Path prefixes that are deliberately not behind the browser sign-in:
# /api/v1 uses the X-API-Key header, /api/health must stay open for probes,
# /api/docs, /api/redoc and /api/openapi.json are the API documentation, and
# /auth is the sign-in flow itself.
OPEN_PREFIXES = ("/api/", "/auth/")
ADMIN_ONLY = {
    ("GET", "/entities/{entity_id}/edit"),
    ("PATCH", "/entities/{entity_id}/edit"),
}


class RouteInfo(NamedTuple):
    """One concrete route: its methods, full path and every gate behind it."""

    methods: frozenset[str]
    path: str
    calls: frozenset[Callable[..., object]]


def _calls(dependant: Dependant) -> set[Callable[..., object]]:
    """Collect every dependency callable reachable from ``dependant``."""
    found: set[Callable[..., object]] = set()
    for sub in dependant.dependencies:
        if sub.call is not None:
            found.add(sub.call)
        found |= _calls(sub)
    return found


def _walk(
    routes: Sequence[BaseRoute],
    prefix: str,
    inherited: frozenset[Callable[..., object]],
) -> Iterator[BaseRoute | RouteInfo]:
    """Flatten nested routers across FastAPI versions.

    Older FastAPI copies included routes into the app; newer releases keep an
    ``_IncludedRouter`` wrapper that carries the include-time prefix and
    dependencies. Both shapes are flattened to ``RouteInfo`` here.

    Yields:
        ``RouteInfo`` for each API route, and any other route object as-is.
    """
    for route in routes:
        context = getattr(route, "include_context", None)
        if context is not None:
            extra = frozenset(
                dep.dependency
                for dep in context.dependencies
                if dep.dependency is not None
            )
            yield from _walk(
                cast("Any", route).original_router.routes,
                prefix + context.prefix,
                inherited | extra,
            )
        elif isinstance(route, APIRoute):
            yield RouteInfo(
                frozenset(route.methods),
                prefix + route.path,
                frozenset(_calls(route.dependant)) | inherited,
            )
        else:
            yield route


def web_routes(app: FastAPI) -> list[RouteInfo]:
    """Return every API route registered on ``app``, flattened."""
    return [
        item
        for item in _walk(app.routes, "", frozenset())
        if isinstance(item, RouteInfo)
    ]


def _unexpected_routes(app: FastAPI) -> list[str]:
    """Name every non-API route that is not a known framework or static route."""
    found: list[str] = []
    for item in _walk(app.routes, "", frozenset()):
        if isinstance(item, RouteInfo):
            continue
        path = getattr(item, "path", "")
        if isinstance(item, Mount):
            if path != "/static":
                found.append(f"unexpected mount {path}")
        elif not (
            isinstance(item, Route) and path.startswith((*OPEN_PREFIXES, "/docs/"))
        ):
            found.append(f"unexpected route {path}")
    return found


def _gate_findings(info: RouteInfo) -> list[str]:
    """List the gates a single route is missing."""
    findings: list[str] = []
    if info.path.startswith(OPEN_PREFIXES):
        return findings
    if require_user not in info.calls:
        findings.append(f"{info.path}: missing require_user")
    findings.extend(
        f"{method} {info.path}: missing verify_csrf"
        for method in sorted(info.methods - SAFE_METHODS)
        if verify_csrf not in info.calls
    )
    findings.extend(
        f"{method} {info.path}: missing require_admin"
        for method in sorted(info.methods)
        if (method, info.path) in ADMIN_ONLY and require_admin not in info.calls
    )
    return findings


def ungated_findings(app: FastAPI) -> list[str]:
    """List every route that is missing a gate it should have."""
    findings = _unexpected_routes(app)
    for info in web_routes(app):
        findings.extend(_gate_findings(info))
    return findings


def test_every_web_route_is_gated() -> None:
    assert ungated_findings(create_app()) == []


def test_enumeration_covers_the_known_web_routes() -> None:
    paths = {info.path for info in web_routes(create_app())}

    assert {"/", "/entities", "/entities/{entity_id}"} <= paths
    assert "/entities/{entity_id}/edit" in paths
    assert "/api/v1/entities" in paths


def test_enumeration_covers_the_dashboard_router_in_api_ui() -> None:
    # GET / is answered by api/ui.py (included before the web router), so the
    # gate on that router is what protects the dashboard.
    root = [info for info in web_routes(create_app()) if info.path == "/"]

    assert root
    assert all(require_user in info.calls for info in root)


def test_enumeration_detects_an_ungated_route() -> None:
    app = create_app()

    @app.get("/forgotten")
    async def forgotten() -> dict[str, bool]:
        return {"oops": True}

    @app.delete("/entities/{entity_id}/remove")
    async def remove(entity_id: str) -> dict[str, str]:
        return {"id": entity_id}

    findings = ungated_findings(app)

    assert "/forgotten: missing require_user" in findings
    assert "DELETE /entities/{entity_id}/remove: missing verify_csrf" in findings


def test_enumeration_detects_an_ungated_router_included_later() -> None:
    from fastapi import APIRouter

    app = create_app()
    router = APIRouter()

    @router.get("/sneaky")
    async def sneaky() -> dict[str, bool]:
        return {"oops": True}

    app.include_router(router)

    assert "/sneaky: missing require_user" in ungated_findings(app)


def test_enumeration_detects_an_unknown_mount() -> None:
    app = create_app()
    app.mount("/files", FastAPI())

    assert "unexpected mount /files" in ungated_findings(app)


def test_admin_only_routes_really_exist() -> None:
    routes = {
        (method, info.path)
        for info in web_routes(create_app())
        for method in info.methods
    }

    assert routes >= ADMIN_ONLY


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()

    async def _override() -> AsyncIterator[_StubSession]:
        yield _StubSession([_make_entity()])

    app.dependency_overrides[get_async_session] = _override
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def _sign_in(client: TestClient, role: str) -> None:
    client.cookies.set(
        SESSION_COOKIE,
        session_cookie_value(settings.secret_key, user_session(role)),
    )


EDIT_URL = f"/entities/{FIXTURE_ID}/edit"
GATED_GETS = [
    "/",
    "/entities",
    f"/entities/{FIXTURE_ID}",
    f"/entities/{FIXTURE_ID}/card",
    EDIT_URL,
]


class TestAnonymous:
    @pytest.mark.parametrize("path", GATED_GETS)
    def test_page_request_redirects_to_login_with_next(
        self, client: TestClient, path: str
    ) -> None:
        response = client.get(path)

        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("/auth/login?next=")

    @pytest.mark.parametrize("path", GATED_GETS)
    def test_htmx_request_gets_401_and_hx_redirect(
        self, client: TestClient, path: str
    ) -> None:
        response = client.get(
            path,
            headers={
                "HX-Request": "true",
                "HX-Current-URL": "http://testserver/entities",
            },
        )

        assert response.status_code == 401
        assert response.headers["hx-redirect"] == "/auth/login?next=%2Fentities"

    def test_patch_is_refused_without_changing_anything(
        self, client: TestClient
    ) -> None:
        response = client.patch(EDIT_URL, data={"legal_name": "Hacked"})

        assert response.status_code in {303, 403}
        assert "Hacked" not in response.text

    def test_api_key_and_health_routes_are_unaffected(self, client: TestClient) -> None:
        assert client.get("/api/health/live").status_code == 200
        assert client.get("/api/v1/entities").status_code == 401  # no X-API-Key

    def test_auth_routes_stay_reachable_without_a_session(
        self, client: TestClient
    ) -> None:
        # Unconfigured OIDC answers 503 itself; a gate would answer 303.
        assert client.get("/auth/login").status_code == 503
        assert client.get("/auth/local-login").status_code == 404

    def test_static_files_stay_open(self, client: TestClient) -> None:
        assert client.get("/static/css/does-not-exist.css").status_code == 404

    def test_dev_mode_opens_the_ui_as_admin(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "auth_dev_mode", True)

        assert client.get("/entities").status_code == 200
        assert client.get(EDIT_URL).status_code == 200


class TestViewer:
    def test_can_read_pages(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        assert client.get("/entities").status_code == 200
        assert client.get(f"/entities/{FIXTURE_ID}").status_code == 200
        assert client.get(f"/entities/{FIXTURE_ID}/card").status_code == 200
        assert client.get("/").status_code == 200

    def test_cannot_open_the_edit_form(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        assert client.get(EDIT_URL).status_code == 403

    def test_cannot_save_an_edit_even_with_a_valid_csrf_token(
        self, client: TestClient
    ) -> None:
        _sign_in(client, "viewer")

        response = client.patch(
            EDIT_URL,
            data={"legal_name": "Renamed"},
            headers={"X-CSRF-Token": TEST_CSRF_TOKEN},
        )

        assert response.status_code == 403

    def test_edit_button_is_hidden(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        for path in (f"/entities/{FIXTURE_ID}", f"/entities/{FIXTURE_ID}/card"):
            body = client.get(path).text
            assert f'hx-get="/entities/{FIXTURE_ID}/edit"' not in body
            assert "Acme Holdings LLC" in body


class TestAdmin:
    def test_edit_button_is_shown(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        body = client.get(f"/entities/{FIXTURE_ID}").text

        assert f'hx-get="/entities/{FIXTURE_ID}/edit"' in body

    def test_can_open_the_edit_form(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        assert client.get(EDIT_URL).status_code == 200

    def test_save_without_csrf_token_is_forbidden(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        response = client.patch(EDIT_URL, data={"legal_name": "Renamed"})

        assert response.status_code == 403

    def test_save_with_wrong_csrf_token_is_forbidden(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        response = client.patch(
            EDIT_URL,
            data={"legal_name": "Renamed"},
            headers={"X-CSRF-Token": "forged"},
        )

        assert response.status_code == 403

    def test_save_with_csrf_token_succeeds(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        response = client.patch(
            EDIT_URL,
            data={
                "legal_name": "Renamed LLC",
                "ein": "12-3456789",
                "entity_type": "llc",
            },
            headers={"X-CSRF-Token": TEST_CSRF_TOKEN},
        )

        assert response.status_code == 200
        assert "Renamed LLC" in response.text


class TestPageChrome:
    def test_body_carries_the_csrf_token_for_htmx(self, client: TestClient) -> None:
        _sign_in(client, "admin")

        body = client.get("/entities").text

        assert f'hx-headers=\'{{"X-CSRF-Token": "{TEST_CSRF_TOKEN}"}}\'' in body

    def test_signed_in_user_and_logout_form_are_shown(self, client: TestClient) -> None:
        _sign_in(client, "viewer")

        body = client.get("/entities").text

        assert "Test Viewer (viewer)" in body
        assert 'action="/auth/logout"' in body
        assert f'name="csrf_token" value="{TEST_CSRF_TOKEN}"' in body

    def test_logout_form_posts_work_with_the_page_token(
        self, client: TestClient
    ) -> None:
        _sign_in(client, "viewer")

        response = client.post("/auth/logout", data={"csrf_token": TEST_CSRF_TOKEN})

        assert response.status_code == 200
        assert "Signed out" in response.text

    def test_expired_session_is_treated_as_signed_out(self, client: TestClient) -> None:
        client.cookies.set(
            SESSION_COOKIE,
            session_cookie_value(settings.secret_key, user_session("admin", exp_in=-1)),
        )

        assert client.get("/entities").status_code == 303
