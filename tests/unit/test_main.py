"""Tests for the FastAPI application factory."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc_manager.main import app, create_app


class TestCreateApp:
    @pytest.mark.unit
    def test_returns_fastapi_instance(self) -> None:
        assert isinstance(create_app(), FastAPI)

    @pytest.mark.unit
    def test_has_non_empty_title(self) -> None:
        result = create_app()
        assert result.title
        assert len(result.title) > 0

    @pytest.mark.unit
    def test_has_version(self) -> None:
        assert create_app().version is not None

    @pytest.mark.unit
    def test_openapi_url(self) -> None:
        assert create_app().openapi_url == "/api/openapi.json"

    @pytest.mark.unit
    def test_docs_url(self) -> None:
        assert create_app().docs_url == "/api/docs"

    @pytest.mark.unit
    def test_redoc_url(self) -> None:
        assert create_app().redoc_url == "/api/redoc"


class TestModuleLevelApp:
    @pytest.mark.unit
    def test_app_is_fastapi(self) -> None:
        assert isinstance(app, FastAPI)

    @pytest.mark.unit
    def test_app_title_matches_create_app(self) -> None:
        assert app.title == create_app().title


class TestAppRouting:
    @pytest.fixture(scope="class")
    def client(self) -> TestClient:
        return TestClient(create_app())

    @pytest.mark.unit
    def test_health_live_route_responds(self, client: TestClient) -> None:
        assert client.get("/api/health/live").status_code == 200

    @pytest.mark.unit
    def test_openapi_schema_accessible(self, client: TestClient) -> None:
        response = client.get("/api/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema

    @pytest.mark.unit
    def test_docs_accessible(self, client: TestClient) -> None:
        assert client.get("/api/docs").status_code == 200

    @pytest.mark.unit
    def test_redoc_accessible(self, client: TestClient) -> None:
        assert client.get("/api/redoc").status_code == 200
