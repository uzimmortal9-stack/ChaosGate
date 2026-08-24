"""End-to-end HTTP behaviour of the control plane.

The `client` fixture comes from conftest.py — the app is constructed once per
session because reloading the SQLAlchemy models would re-register the tables.
"""

import json
from pathlib import Path


def test_health_endpoints(client):
    assert client.get("/api/health").get_json()["ok"] is True
    assert client.get("/healthz").get_json()["status"] == "ok"
    assert client.get("/readyz").get_json()["status"] == "ready"


def test_metrics_endpoint_is_prometheus_text(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    assert res.mimetype == "text/plain"
    body = res.get_data(as_text=True)
    assert "# TYPE chaosgate_build_info gauge" in body

    from core.prometheus import parse_exposition

    assert parse_exposition(body)["valid"]


def test_me_reports_capabilities(client):
    data = client.get("/api/me").get_json()
    assert "workspace" in data
    assert "capabilities" in data
    assert "toolchain" in data
    assert data["stats"]["repos"] >= 3  # samples are seeded


def test_capabilities_lists_every_tool(client):
    tools = client.get("/api/capabilities").get_json()["tools"]
    assert {"git", "docker", "kubectl", "k6", "prometheus", "grafana"} <= set(tools)
    for tool in tools.values():
        assert "available" in tool and "detail" in tool


def test_stage_catalog_has_thirteen_stages(client):
    stages = client.get("/api/stages").get_json()["stages"]
    keys = [s["key"] for s in stages]
    assert len(keys) == 13
    for expected in ("docker", "k8s", "load", "prometheus", "grafana", "chaos", "verdict"):
        assert expected in keys


def test_samples_are_seeded(client):
    repos = client.get("/api/repos").get_json()["repos"]
    names = {r["full_name"] for r in repos}
    assert "atlas-shop/atlas-api" in names
    assert all(r["is_sample"] for r in repos)


def test_add_repo_normalizes_urls(client, monkeypatch):
    from core import github_client

    monkeypatch.setattr(github_client, "get_repo", lambda t, n: {
        "full_name": n, "name": n.split("/")[1], "owner": n.split("/")[0],
        "html_url": f"https://github.com/{n}", "clone_url": f"https://github.com/{n}.git",
        "default_branch": "main", "language": "Python", "description": "x", "private": False,
    })
    for raw in ("https://github.com/psf/requests", "psf/requests.git", "/psf/requests"):
        res = client.post("/api/repos", json={"full_name": raw})
        assert res.status_code in (200, 201)
        assert res.get_json()["repo"]["full_name"] == "psf/requests"


def test_add_repo_rejects_garbage(client):
    assert client.post("/api/repos", json={"full_name": "notarepo"}).status_code == 400


def test_github_endpoints_require_auth(client):
    assert client.get("/api/github/repos").status_code == 401


def test_pat_auth_rejects_empty(client):
    assert client.post("/api/auth/github", json={"token": ""}).status_code == 400


def test_oauth_login_without_config_is_501(client):
    res = client.get("/api/auth/github/login?json=1")
    assert res.status_code == 501


def test_policy_roundtrip(client):
    original = client.get("/api/policy").get_json()["policy"]
    assert "fail_on_docker" in original and "fail_on_k8s" in original

    updated = client.put("/api/policy", json={"max_p95_ms": 250, "fail_on_chaos": False}).get_json()["policy"]
    assert updated["max_p95_ms"] == 250
    assert updated["fail_on_chaos"] is False
    assert client.get("/api/policy").get_json()["policy"]["max_p95_ms"] == 250


def test_observability_payload(client):
    data = client.get("/api/observability").get_json()
    assert data["prometheus"]["exposition"]["valid"]
    assert "scrape_config" in data["prometheus"]
    assert data["kubernetes"]["namespace"]


def test_dashboard_download(client):
    res = client.get("/api/observability/dashboard?download=1")
    assert res.status_code == 200
    assert "attachment" in res.headers["Content-Disposition"]
    assert json.loads(res.get_data(as_text=True))["uid"] == "chaosgate-main"


def test_workspace_editor_blocked_for_samples(client):
    repo = client.get("/api/repos").get_json()["repos"][0]
    res = client.post(f"/api/repos/{repo['id']}/workspace")
    assert res.status_code == 400
    assert "sample" in res.get_json()["error"].lower()


def test_push_requires_open_workspace(client):
    repo = client.get("/api/repos").get_json()["repos"][0]
    res = client.post(f"/api/repos/{repo['id']}/push", json={"message": "x"})
    assert res.status_code == 400


def test_push_requires_message(client):
    repo = client.get("/api/repos").get_json()["repos"][0]
    res = client.post(f"/api/repos/{repo['id']}/push", json={})
    assert res.status_code == 400
    assert "message" in res.get_json()["error"].lower()


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope").status_code == 404


def test_artifact_path_traversal_blocked(client):
    res = client.get("/api/runs/abc/artifacts/..%2f..%2f..%2fetc%2fpasswd")
    assert res.status_code in (400, 404)


def test_spa_fallback_serves_html(client):
    res = client.get("/console/repos")
    assert res.status_code == 200
    assert b"<div id=\"app\">" in res.data


def test_unknown_api_route_is_json_404(client):
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    assert res.get_json()["error"]


# ------------------------------------------------------------------ webhooks
def test_webhook_ping(client):
    res = client.post("/webhook/github", json={"zen": "hi"}, headers={"X-GitHub-Event": "ping"})
    assert res.get_json()["pong"] is True


def test_webhook_ignores_unknown_repo(client):
    body = {"ref": "refs/heads/main", "after": "a" * 40, "repository": {"full_name": "who/what"}}
    res = client.post("/webhook/github", json=body, headers={"X-GitHub-Event": "push"})
    data = res.get_json()
    assert data["ran"] is False
    assert "not connected" in data["reason"]


def test_webhook_ignores_branch_deletion(client):
    body = {"ref": "refs/heads/x", "after": "0" * 40, "repository": {"full_name": "a/b"}}
    res = client.post("/webhook/github", json=body, headers={"X-GitHub-Event": "push"})
    assert res.get_json()["ran"] is False


def test_webhook_ignores_closed_pr(client):
    body = {"action": "closed", "pull_request": {"number": 1, "head": {"ref": "x", "sha": "y"}},
            "repository": {"full_name": "a/b"}}
    res = client.post("/webhook/github", json=body, headers={"X-GitHub-Event": "pull_request"})
    assert res.get_json()["ran"] is False


def test_webhook_events_are_recorded(client):
    client.post("/webhook/github", json={"ref": "refs/heads/main", "after": "c" * 40,
                                         "repository": {"full_name": "x/y"}},
                headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": "d-1"})
    events = client.get("/api/webhooks").get_json()["events"]
    assert any(e["delivery_id"] == "d-1" for e in events)


def test_webhook_signature_rejected_when_secret_set(client, monkeypatch):
    import core.api as api_mod

    monkeypatch.setattr(api_mod, "GITHUB_WEBHOOK_SECRET", "topsecret")
    res = client.post("/webhook/github", json={"ref": "refs/heads/main"},
                      headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=bogus"})
    assert res.status_code == 401


def test_webhook_signature_accepted_when_valid(client, monkeypatch):
    import hashlib
    import hmac

    import core.api as api_mod
    from core import github_client

    secret = "topsecret"
    monkeypatch.setattr(api_mod, "GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(github_client, "GITHUB_WEBHOOK_SECRET", secret)

    payload = json.dumps({"zen": "x"}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    res = client.post("/webhook/github", data=payload,
                      headers={"X-GitHub-Event": "ping", "Content-Type": "application/json",
                               "X-Hub-Signature-256": sig})
    assert res.status_code == 200


# ------------------------------------------------------------ cache busting
def test_static_urls_are_versioned(client):
    """Without a version query the browser keeps running a cached app.js and
    UI changes appear not to have shipped."""
    html = client.get("/").get_data(as_text=True)
    assert 'src="/static/js/app.js?v=' in html
    assert 'href="/static/css/style.css?v=' in html


def test_asset_version_changes_with_content(client, tmp_path, monkeypatch):
    import re

    from flask import current_app

    first = client.get("/").get_data(as_text=True)
    token = re.search(r"app\.js\?v=([a-f0-9]+)", first).group(1)
    assert len(token) == 10

    path = Path(current_app.static_folder) / "js/app.js"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n// probe\n")
        changed = client.get("/").get_data(as_text=True)
        assert re.search(r"app\.js\?v=([a-f0-9]+)", changed).group(1) != token
    finally:
        path.write_bytes(original)

    restored = client.get("/").get_data(as_text=True)
    assert re.search(r"app\.js\?v=([a-f0-9]+)", restored).group(1) == token
