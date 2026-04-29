"""Tests for health check endpoints."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from llc_manager.api.health import ReadinessCheck, check_database
from llc_manager.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Fresh TestClient per test to avoid rate-limit state sharing."""
    return TestClient(create_app())


@pytest.fixture
def db_unavailable_client() -> Generator[TestClient, None, None]:
    """Client whose DB check always returns a failed ReadinessCheck."""
    mock_check = AsyncMock(
        return_value=ReadinessCheck(
            name="database",
            status=False,
            latency_ms=0.0,
            error="database_unavailable",
        )
    )
    with (
        patch("llc_manager.api.health.check_database", mock_check),
        TestClient(create_app()) as c,
    ):
        yield c


@pytest.fixture
def db_available_client() -> Generator[TestClient, None, None]:
    """Client whose DB check always returns a healthy ReadinessCheck."""
    mock_check = AsyncMock(
        return_value=ReadinessCheck(
            name="database",
            status=True,
            latency_ms=1.0,
        )
    )
    with (
        patch("llc_manager.api.health.check_database", mock_check),
        TestClient(create_app()) as c,
    ):
        yield c


class TestLivenessProbe:
    @pytest.mark.unit
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/health/live").status_code == 200

    @pytest.mark.unit
    def test_status_ok(self, client: TestClient) -> None:
        assert client.get("/api/health/live").json()["status"] == "ok"

    @pytest.mark.unit
    def test_uptime_non_negative(self, client: TestClient) -> None:
        assert client.get("/api/health/live").json()["uptime_seconds"] >= 0

    @pytest.mark.unit
    def test_python_version_present(self, client: TestClient) -> None:
        data = client.get("/api/health/live").json()
        assert "python_version" in data
        assert data["python_version"]

    @pytest.mark.unit
    def test_timestamp_present(self, client: TestClient) -> None:
        data = client.get("/api/health/live").json()
        assert data["timestamp"] > 0

    @pytest.mark.unit
    def test_version_field_present(self, client: TestClient) -> None:
        assert "version" in client.get("/api/health/live").json()


class TestStartupProbe:
    @pytest.mark.unit
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/health/startup").status_code == 200

    @pytest.mark.unit
    def test_status_started(self, client: TestClient) -> None:
        assert client.get("/api/health/startup").json()["status"] == "started"

    @pytest.mark.unit
    def test_uptime_non_negative(self, client: TestClient) -> None:
        assert client.get("/api/health/startup").json()["uptime_seconds"] >= 0


class TestHealthAlias:
    @pytest.mark.unit
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/api/health/").status_code == 200

    @pytest.mark.unit
    def test_status_ok(self, client: TestClient) -> None:
        assert client.get("/api/health/").json()["status"] == "ok"

    @pytest.mark.unit
    def test_matches_liveness_status(self, client: TestClient) -> None:
        assert client.get("/api/health/").json()["status"] == "ok"


class TestReadinessProbeUnavailable:
    """Tests for the 503 path via a mocked check_database."""

    @pytest.mark.unit
    def test_returns_503(self, db_unavailable_client: TestClient) -> None:
        """Readiness returns 503 when a dependency check fails."""
        assert db_unavailable_client.get("/api/health/ready").status_code == 503

    @pytest.mark.unit
    def test_error_detail_status_unavailable(
        self, db_unavailable_client: TestClient
    ) -> None:
        detail = db_unavailable_client.get("/api/health/ready").json()["detail"]
        assert detail["status"] == "unavailable"

    @pytest.mark.unit
    def test_error_detail_contains_database_check(
        self, db_unavailable_client: TestClient
    ) -> None:
        detail = db_unavailable_client.get("/api/health/ready").json()["detail"]
        assert "checks" in detail
        assert "database" in detail["checks"]

    @pytest.mark.unit
    def test_database_check_status_false(
        self, db_unavailable_client: TestClient
    ) -> None:
        db_check = db_unavailable_client.get("/api/health/ready").json()["detail"][
            "checks"
        ]["database"]
        assert db_check["status"] is False

    @pytest.mark.unit
    def test_database_error_is_opaque(self, db_unavailable_client: TestClient) -> None:
        """Error message must not leak DB connection topology."""
        db_check = db_unavailable_client.get("/api/health/ready").json()["detail"][
            "checks"
        ]["database"]
        assert db_check["error"] == "database_unavailable"


class TestReadinessProbeAvailable:
    """Tests for the 200 path via a mocked check_database."""

    @pytest.mark.unit
    def test_returns_200(self, db_available_client: TestClient) -> None:
        assert db_available_client.get("/api/health/ready").status_code == 200

    @pytest.mark.unit
    def test_status_ok(self, db_available_client: TestClient) -> None:
        assert db_available_client.get("/api/health/ready").json()["status"] == "ok"

    @pytest.mark.unit
    def test_checks_contain_database(self, db_available_client: TestClient) -> None:
        data = db_available_client.get("/api/health/ready").json()
        assert "checks" in data
        assert "database" in data["checks"]

    @pytest.mark.unit
    def test_database_check_status_true(self, db_available_client: TestClient) -> None:
        db_check = db_available_client.get("/api/health/ready").json()["checks"][
            "database"
        ]
        assert db_check["status"] is True


class TestCheckDatabaseDirect:
    """Tests for the check_database() helper -- covers the function body
    regardless of whether a live PostgreSQL instance is present."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_readiness_check(self) -> None:
        result = await check_database()
        assert isinstance(result, ReadinessCheck)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_name_is_database(self) -> None:
        result = await check_database()
        assert result.name == "database"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_latency_is_non_negative(self) -> None:
        result = await check_database()
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_status_is_bool(self) -> None:
        result = await check_database()
        assert isinstance(result.status, bool)
