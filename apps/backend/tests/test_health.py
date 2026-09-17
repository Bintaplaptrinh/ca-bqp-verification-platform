from fastapi.testclient import TestClient

from cabqp.main import app


def test_health():
    r=TestClient(app).get('/health')
    assert r.status_code==200 and r.json()['status']=='ok'
