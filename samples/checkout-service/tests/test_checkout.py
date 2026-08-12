from app import app


def test_health_ok():
    client = app.test_client()
    res = client.get("/health")
    assert res.status_code == 200
    # Intentional failure: service reports degraded, contract requires ok.
    assert res.get_json()["status"] == "ok"


def test_tax_applied_once():
    client = app.test_client()
    res = client.post("/api/charge", json={"amount": 100})
    body = res.get_json()
    assert res.status_code == 200
    assert body["total"] == 108.0
