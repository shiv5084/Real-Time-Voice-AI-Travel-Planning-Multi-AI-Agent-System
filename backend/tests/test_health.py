"""Health endpoint tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_env"] in ("local", "staging", "production")


def test_health_includes_trace_header():
    response = client.get("/health")
    assert "X-Trace-Id" in response.headers
    assert len(response.headers["X-Trace-Id"]) > 0
