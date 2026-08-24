"""Docker, Kubernetes, k6 and Grafana logic — the parts that must be right
whether or not the underlying tool is installed."""

import json
from pathlib import Path

import yaml

from core import docker_runner, grafana, k6_runner, k8s_runner
from core.prometheus import parse_exposition


# ------------------------------------------------------------------- docker
def _write(tmp_path: Path, body: str, name: str = "Dockerfile") -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_dockerfile_missing_from_is_critical(tmp_path):
    findings = docker_runner.lint_dockerfile(_write(tmp_path, "RUN echo hi\n"))
    assert findings[0]["severity"] == "critical"
    assert findings[0]["rule"] == "no-from"


def test_dockerfile_flags_latest_and_root(tmp_path):
    findings = docker_runner.lint_dockerfile(
        _write(tmp_path, "FROM python:latest\nCMD [\"python\"]\n")
    )
    rules = {f["rule"] for f in findings}
    assert "latest-tag" in rules
    assert "runs-as-root" in rules


def test_dockerfile_flags_untagged_base(tmp_path):
    findings = docker_runner.lint_dockerfile(_write(tmp_path, "FROM ubuntu\nCMD [\"sh\"]\n"))
    assert "unpinned-base" in {f["rule"] for f in findings}


def test_dockerfile_flags_baked_secret(tmp_path):
    findings = docker_runner.lint_dockerfile(
        _write(tmp_path, 'FROM python:3.12-slim\nENV API_KEY=abc123def456\nCMD ["python"]\n')
    )
    critical = [f for f in findings if f["severity"] == "critical"]
    assert any(f["rule"] == "baked-secret" for f in critical)


def test_dockerfile_flags_cache_busting_copy(tmp_path):
    body = (
        "FROM python:3.12-slim\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "RUN pip install -r requirements.txt\n"
        "USER nobody\n"
        'CMD ["python", "app.py"]\n'
    )
    findings = docker_runner.lint_dockerfile(_write(tmp_path, body))
    assert "cache-busting-copy" in {f["rule"] for f in findings}


def test_good_dockerfile_has_no_blocking_findings(tmp_path):
    body = (
        "FROM python:3.12-slim@sha256:abc\n"
        "WORKDIR /app\n"
        "COPY requirements.txt .\n"
        "RUN pip install --no-cache-dir -r requirements.txt\n"
        "COPY . .\n"
        "USER 10001\n"
        "HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1\n"
        "EXPOSE 8000\n"
        'CMD ["python", "app.py"]\n'
    )
    findings = docker_runner.lint_dockerfile(_write(tmp_path, body))
    assert not [f for f in findings if f["severity"] in ("critical", "warning")]


def test_compose_parsed_without_docker(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  web:\n    image: nginx\n  api:\n    build: .\n"
    )
    result = docker_runner.compose_config(tmp_path / "docker-compose.yml", lambda m: None)
    assert result["valid"]
    assert set(result["services"]) == {"web", "api"}


def test_compose_flags_service_without_image_or_build(tmp_path):
    (tmp_path / "compose.yml").write_text("services:\n  broken:\n    ports: ['80:80']\n")
    result = docker_runner.compose_config(tmp_path / "compose.yml", lambda m: None)
    assert not result["valid"]
    assert result["issues"]


def test_find_dockerfile_and_compose(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    (tmp_path / "compose.yml").write_text("services: {}\n")
    assert docker_runner.find_dockerfile(tmp_path).name == "Dockerfile"
    assert docker_runner.find_compose(tmp_path).name == "compose.yml"


# --------------------------------------------------------------- kubernetes
def _deployment(**over):
    container = {
        "name": "app",
        "image": "app:1.0.0",
        "resources": {"requests": {"cpu": "100m"}, "limits": {"cpu": "500m"}},
        "livenessProbe": {"httpGet": {"path": "/health", "port": 80}},
        "readinessProbe": {"httpGet": {"path": "/health", "port": 80}},
        "securityContext": {"runAsNonRoot": True, "allowPrivilegeEscalation": False},
    }
    container.update(over)
    return {
        "kind": "Deployment",
        "metadata": {"name": "app"},
        "spec": {"replicas": 2, "template": {"spec": {"containers": [container]}}},
    }


def test_audit_clean_deployment():
    findings = k8s_runner.audit([_deployment(), {"kind": "Service", "metadata": {"name": "app"}}])
    assert not [f for f in findings if f["severity"] in ("critical", "warning")]


def test_audit_flags_mutable_tag():
    findings = k8s_runner.audit([_deployment(image="app:latest")])
    assert "mutable-image" in {f["rule"] for f in findings}


def test_audit_flags_missing_limits_and_probes():
    findings = k8s_runner.audit([_deployment(resources={}, livenessProbe=None, readinessProbe=None)])
    rules = {f["rule"] for f in findings}
    assert {"no-limits", "no-requests", "no-liveness", "no-readiness"} <= rules


def test_audit_flags_privileged_and_inline_secret():
    doc = _deployment(
        securityContext={"privileged": True},
        env=[{"name": "DB_PASSWORD", "value": "hunter2"}],
    )
    critical = [f for f in k8s_runner.audit([doc]) if f["severity"] == "critical"]
    rules = {f["rule"] for f in critical}
    assert "privileged" in rules
    assert "inline-secret" in rules


def test_audit_honours_pod_level_security_context():
    """runAsNonRoot at pod level applies to every container in the pod."""
    doc = _deployment()
    doc["spec"]["template"]["spec"]["securityContext"] = {"runAsNonRoot": True}
    doc["spec"]["template"]["spec"]["containers"][0]["securityContext"] = {
        "allowPrivilegeEscalation": False
    }
    assert "may-run-root" not in {f["rule"] for f in k8s_runner.audit([doc])}


def test_secret_ref_is_not_flagged():
    doc = _deployment(env=[{"name": "DB_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "s"}}}])
    assert "inline-secret" not in {f["rule"] for f in k8s_runner.audit([doc])}


def test_generated_manifests_pass_own_audit():
    rendered = k8s_runner.generate_manifests("demo", "demo:1.2.3", 8000)
    docs = [d for d in yaml.safe_load_all(rendered) if d]
    kinds = [d["kind"] for d in docs]
    assert kinds == ["Namespace", "Deployment", "Service", "HorizontalPodAutoscaler", "PodDisruptionBudget"]
    assert k8s_runner.audit(docs) == []


def test_shipped_manifests_pass_own_audit():
    path = Path("k8s/chaosgate.yaml")
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d]
    assert k8s_runner.audit(docs) == []


def test_discover_manifests(tmp_path):
    (tmp_path / "k8s").mkdir()
    (tmp_path / "k8s" / "deploy.yaml").write_text("apiVersion: apps/v1\nkind: Deployment\n")
    (tmp_path / "k8s" / "notes.txt").write_text("ignore me")
    (tmp_path / "chaosgate.yml").write_text("apiVersion: 1\nkind: nope\n")
    found = [p.name for p in k8s_runner.discover_manifests(tmp_path)]
    assert "deploy.yaml" in found
    assert "chaosgate.yml" not in found


# ----------------------------------------------------------------------- k6
def test_parse_k6_summary():
    summary = {
        "metrics": {
            "http_reqs": {"count": 1500, "rate": 150.0},
            "http_req_failed": {"rate": 0.02, "passes": 30, "fails": 1470},
            "http_req_duration": {"avg": 45.0, "min": 10.0, "med": 40.0, "p(95)": 120.0, "p(99)": 200.0, "max": 350.0},
            "checks": {"passes": 1470, "fails": 30},
        }
    }
    result = k6_runner.parse_k6_summary(summary, 10.0)
    assert result["engine"] == "k6"
    assert result["degraded"] is False
    assert result["samples"] == 1500
    assert result["errors"] == 30
    assert result["p95_ms"] == 120.0
    assert result["rps"] == 150.0


def test_parse_k6_summary_tolerates_missing_metrics():
    result = k6_runner.parse_k6_summary({"metrics": {}}, 5.0)
    assert result["samples"] == 0
    assert result["p95_ms"] == 0.0


def test_build_script_embeds_thresholds_and_endpoints():
    script = k6_runner.build_script(
        [{"method": "POST", "path": "/api/orders", "body": "{}"}], 25, "45s", 500, 0.01
    )
    assert "vus: 25" in script
    assert 'duration: "45s"' in script
    assert "p(95)<500" in script
    assert "rate<0.01" in script
    assert "/api/orders" in script
    assert json.loads(script[script.index("["): script.index("];") + 1])[0]["method"] == "POST"


def test_builtin_generator_shape_matches_k6():
    """Both engines must produce the same keys or the verdict logic breaks."""
    k6_keys = set(k6_runner.parse_k6_summary({"metrics": {}}, 1.0))
    empty = k6_runner._empty_result("builtin", "x")
    required = {"engine", "ok", "samples", "errors", "error_rate", "p95_ms", "avg_ms", "rps"}
    assert required <= k6_keys
    assert required <= set(empty)


# ------------------------------------------------------------------ grafana
def test_dashboard_is_valid_and_serializable():
    dashboard = grafana.build_dashboard()
    body = json.dumps(dashboard)
    assert dashboard["uid"] == "chaosgate-main"
    assert dashboard["schemaVersion"] >= 39
    panels = [p for p in dashboard["panels"] if p.get("type") != "row"]
    assert len(panels) >= 15
    for panel in panels:
        assert panel.get("title")
        assert panel.get("gridPos")
    assert "chaosgate_gate_score" in body


def test_dashboard_queries_reference_real_metrics():
    """Every PromQL expression must name a metric the app actually exports."""
    from core import metrics

    metrics.bootstrap("test")
    metrics.pipeline_runs_total.inc(repo="a/b", trigger="t", verdict="PASS")
    metrics.gate_score.set(90, repo="a/b")
    metrics.load_p95_milliseconds.set(1, repo="a/b", engine="k6")
    metrics.load_error_rate.set(0, repo="a/b", engine="k6")
    metrics.load_rps.set(1, repo="a/b", engine="k6")
    metrics.stage_duration_seconds.observe(1, stage="unit", status="passed")
    metrics.stage_results_total.inc(stage="unit", status="passed")
    metrics.security_findings_total.inc(repo="a/b", severity="critical")
    metrics.gate_blocked_total.inc(repo="a/b", reason="x")
    metrics.chaos_recovery_seconds.set(1, repo="a/b", experiment="kill")
    metrics.docker_build_duration_seconds.observe(1, repo="a/b")
    metrics.docker_image_size_bytes.set(1, repo="a/b")
    metrics.toolchain_available.set(1, tool="git")
    metrics.load_request_duration_seconds.observe(0.1, repo="a/b")
    metrics.http_request_duration_seconds.observe(0.1, method="GET", endpoint="x")
    metrics.github_api_calls_total.inc(operation="x", result="ok")
    metrics.pipeline_runs_active.set(0)

    exported = {s["name"] for s in parse_exposition(metrics.render())["samples"]}
    bases = {n.rsplit("_bucket", 1)[0].rsplit("_sum", 1)[0].rsplit("_count", 1)[0] for n in exported}

    import re

    referenced = set()
    for panel in grafana.build_dashboard()["panels"]:
        for target in panel.get("targets") or []:
            for name in re.findall(r"\bchaosgate_[a-z0-9_]+", target.get("expr", "")):
                referenced.add(name.rsplit("_bucket", 1)[0])

    missing = referenced - bases - exported
    assert not missing, f"dashboard references metrics that are never exported: {sorted(missing)}"


def test_datasource_and_dashboard_provisioning():
    ds = grafana.datasource_provisioning("http://prom:9090")
    assert ds["datasources"][0]["url"] == "http://prom:9090"
    assert grafana.dashboard_provisioning()["providers"][0]["name"] == "chaosgate"


def test_publish_degrades_without_config(monkeypatch):
    monkeypatch.setattr(grafana, "GRAFANA_URL", "")
    result = grafana.publish(grafana.build_dashboard())
    assert result["published"] is False
    assert result["degraded"] is True
