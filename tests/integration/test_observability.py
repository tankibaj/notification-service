"""
Integration tests for observability endpoints.

TS-001-062 — notification-service GET /health returns 200
TS-001-063 — notification-service GET /ready returns 200
TS-001-064 — notification-service GET /metrics returns Prometheus format
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ts_001_062_health_returns_200(client: AsyncClient) -> None:
    """TS-001-062: GET /health returns HTTP 200 with status: ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_ts_001_063_ready_returns_200_when_db_healthy(client: AsyncClient) -> None:
    """TS-001-063: GET /ready returns HTTP 200 with status: ready when DB is healthy."""
    response = await client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data.get("database") == "ok"


@pytest.mark.asyncio
async def test_ts_001_064_metrics_returns_prometheus_format(client: AsyncClient) -> None:
    """TS-001-064: GET /metrics returns HTTP 200 with Prometheus-formatted metrics."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type
    # Prometheus format: metric lines start with # HELP or # TYPE or a metric name
    body = response.text
    assert body.strip(), "Metrics body should not be empty"
    # Standard prometheus metrics should be present
    assert "#" in body or "=" in body or "_total" in body
