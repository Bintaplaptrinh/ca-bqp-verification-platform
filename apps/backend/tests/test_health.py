"""Test backend healthcheck endpoint."""

from fastapi.testclient import TestClient

from cabqp.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    """Verify health endpoint responds with 200 and expected payload."""
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "ca-bqp-backend"
