from app import app


def test_health():
    assert app.test_client().get("/health").status_code == 200


def test_invoices():
    body = app.test_client().get("/api/invoices").get_json()
    assert len(body["invoices"]) == 2
