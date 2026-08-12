from app import app


def test_health():
    client = app.test_client()
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"


def test_catalog_not_empty():
    client = app.test_client()
    res = client.get("/api/items")
    body = res.get_json()
    assert res.status_code == 200
    assert body["count"] >= 1


def test_known_sku():
    client = app.test_client()
    res = client.get("/api/items/sku-104")
    assert res.status_code == 200
    assert res.get_json()["name"] == "Field notebook"
