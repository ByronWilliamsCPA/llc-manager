"""Tests for SSRFPreventionMiddleware body inspection.

Covers the body-scanning branch added to satisfy ADR-001's commitment that
SSRF protection covers user-supplied URL fields in request bodies (not only
querystring parameters).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc_manager.middleware.security import SSRFPreventionMiddleware


@pytest.fixture
def app_with_ssrf() -> FastAPI:
    """Build a tiny FastAPI app guarded by SSRFPreventionMiddleware.

    The echo route reads the JSON body and returns it. If the middleware
    consumes the body without replaying it, this route receives an empty
    payload and the test detects the regression.
    """
    app = FastAPI()
    app.add_middleware(SSRFPreventionMiddleware)

    @app.post("/echo")
    async def echo(payload: dict) -> dict:  # type: ignore[type-arg]
        return {"received": payload}

    @app.post("/form-echo")
    async def form_echo(field: str) -> dict:
        return {"ok": True}

    return app


class TestCollectUrlStrings:
    @pytest.mark.unit
    def test_extracts_top_level_url(self) -> None:
        assert SSRFPreventionMiddleware._collect_url_strings(
            {"website": "https://example.com"}
        ) == ["https://example.com"]

    @pytest.mark.unit
    def test_recurses_into_nested_dict(self) -> None:
        data = {"entity": {"contact": {"website": "https://example.com"}}}
        assert SSRFPreventionMiddleware._collect_url_strings(data) == [
            "https://example.com"
        ]

    @pytest.mark.unit
    def test_recurses_into_lists(self) -> None:
        data = {"links": ["https://a.com", "not-a-url", "https://b.com"]}
        result = SSRFPreventionMiddleware._collect_url_strings(data)
        assert set(result) == {"https://a.com", "https://b.com"}

    @pytest.mark.unit
    def test_ignores_non_url_strings(self) -> None:
        assert (
            SSRFPreventionMiddleware._collect_url_strings(
                {"name": "Acme Co", "id": "abc-123"}
            )
            == []
        )

    @pytest.mark.unit
    def test_ignores_non_string_leaves(self) -> None:
        assert (
            SSRFPreventionMiddleware._collect_url_strings(
                {"count": 5, "active": True, "ratio": 3.14, "missing": None}
            )
            == []
        )


class TestBodyInspection:
    @pytest.mark.unit
    @pytest.mark.security
    def test_blocks_localhost_in_json_body(self, app_with_ssrf: FastAPI) -> None:
        client = TestClient(app_with_ssrf)
        response = client.post("/echo", json={"website": "http://localhost:8080/admin"})
        assert response.status_code == 400
        assert "SSRF" in response.json()["message"]

    @pytest.mark.unit
    @pytest.mark.security
    def test_blocks_aws_metadata_endpoint_in_nested_field(
        self, app_with_ssrf: FastAPI
    ) -> None:
        client = TestClient(app_with_ssrf)
        response = client.post(
            "/echo",
            json={"entity": {"links": ["http://169.254.169.254/latest/meta-data/"]}},
        )
        assert response.status_code == 400

    @pytest.mark.unit
    def test_allows_external_https_url(self, app_with_ssrf: FastAPI) -> None:
        """A legitimate external URL must pass through and reach the handler."""
        client = TestClient(app_with_ssrf)
        response = client.post("/echo", json={"website": "https://example.com/contact"})
        assert response.status_code == 200
        # Body must be replayed: the handler must see the original payload.
        assert response.json() == {
            "received": {"website": "https://example.com/contact"}
        }

    @pytest.mark.unit
    def test_malformed_json_passes_through_to_handler(
        self, app_with_ssrf: FastAPI
    ) -> None:
        """Malformed JSON is FastAPI's problem to surface (422), not SSRF's."""
        client = TestClient(app_with_ssrf)
        response = client.post(
            "/echo",
            content=b"{not valid json",
            headers={"content-type": "application/json"},
        )
        # FastAPI returns 422 for malformed JSON; the key assertion is that
        # the SSRF middleware did NOT short-circuit with its own 400.
        assert response.status_code != 400 or "SSRF" not in response.text

    @pytest.mark.unit
    def test_query_param_block_still_works(self, app_with_ssrf: FastAPI) -> None:
        """Body-inspection must not regress the original query-param scan."""
        client = TestClient(app_with_ssrf)
        response = client.post(
            "/echo?callback=http://127.0.0.1:9999", json={"website": "https://ok.com"}
        )
        assert response.status_code == 400
        assert "callback" in response.json()["detail"]
