"""Grafana integration.

Builds a real, importable Grafana dashboard (schema v39) from ChaosGate's
Prometheus metric names, and publishes it through the HTTP API when
GRAFANA_URL and GRAFANA_API_KEY are configured.

With no Grafana reachable the dashboard JSON is still produced and offered as
a download plus a provisioning bundle — the stage reports *degraded*, never a
false success.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from core.settings import GRAFANA_API_KEY, GRAFANA_FOLDER, GRAFANA_URL, PROMETHEUS_URL

DATASOURCE = {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}


def _target(expr: str, legend: str = "", instant: bool = False) -> dict[str, Any]:
    return {
        "datasource": DATASOURCE,
        "editorMode": "code",
        "expr": expr,
        "legendFormat": legend or "__auto",
        "range": not instant,
        "instant": instant,
        "refId": "A",
    }


def _grid(x: int, y: int, w: int, h: int) -> dict[str, int]:
    return {"h": h, "w": w, "x": x, "y": y}


def _stat(title: str, expr: str, unit: str, grid: dict[str, int], pid: int, thresholds: list[dict] | None = None, decimals: int | None = None) -> dict[str, Any]:
    return {
        "id": pid,
        "type": "stat",
        "title": title,
        "datasource": DATASOURCE,
        "gridPos": grid,
        "targets": [_target(expr, instant=True)],
        "options": {
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "auto",
            "textMode": "auto",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "decimals": decimals,
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": thresholds or [{"color": "blue", "value": None}],
                },
            },
            "overrides": [],
        },
    }


def _timeseries(title: str, targets: list[dict[str, Any]], unit: str, grid: dict[str, int], pid: int, desc: str = "") -> dict[str, Any]:
    return {
        "id": pid,
        "type": "timeseries",
        "title": title,
        "description": desc,
        "datasource": DATASOURCE,
        "gridPos": grid,
        "targets": targets,
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": {
                    "drawStyle": "line",
                    "lineWidth": 2,
                    "fillOpacity": 12,
                    "showPoints": "never",
                    "spanNulls": True,
                    "axisSoftMin": 0,
                },
                "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
            },
            "overrides": [],
        },
    }


def build_dashboard(title: str = "ChaosGate — Release Gate", uid: str = "chaosgate-main") -> dict[str, Any]:
    """The main operational dashboard for the gate itself."""
    panels: list[dict[str, Any]] = []
    pid = 1

    panels.append({
        "id": pid, "type": "row", "title": "Gate verdicts",
        "gridPos": _grid(0, 0, 24, 1), "collapsed": False, "panels": [],
    })
    pid += 1

    panels.append(_stat(
        "Runs (5m rate)", "sum(rate(chaosgate_pipeline_runs_total[5m])) * 300",
        "short", _grid(0, 1, 4, 4), pid, decimals=2,
    )); pid += 1
    panels.append(_stat(
        "Pass rate",
        'sum(chaosgate_pipeline_runs_total{verdict="PASS"}) / clamp_min(sum(chaosgate_pipeline_runs_total), 1) * 100',
        "percent", _grid(4, 1, 4, 4), pid,
        thresholds=[
            {"color": "red", "value": None},
            {"color": "orange", "value": 60},
            {"color": "green", "value": 85},
        ],
        decimals=1,
    )); pid += 1
    panels.append(_stat(
        "Active runs", "sum(chaosgate_pipeline_runs_active)", "short", _grid(8, 1, 4, 4), pid,
    )); pid += 1
    panels.append(_stat(
        "Blocked merges", "sum(chaosgate_gate_blocked_total)", "short", _grid(12, 1, 4, 4), pid,
        thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}],
    )); pid += 1
    panels.append(_stat(
        "Lowest gate score", "min(chaosgate_gate_score)", "short", _grid(16, 1, 4, 4), pid,
        thresholds=[
            {"color": "red", "value": None},
            {"color": "orange", "value": 60},
            {"color": "green", "value": 80},
        ],
    )); pid += 1
    panels.append(_stat(
        "Critical findings",
        'sum(chaosgate_security_findings_total{severity="critical"})',
        "short", _grid(20, 1, 4, 4), pid,
        thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}],
    )); pid += 1

    panels.append({
        "id": pid, "type": "row", "title": "Pipeline throughput",
        "gridPos": _grid(0, 5, 24, 1), "collapsed": False, "panels": [],
    }); pid += 1

    panels.append(_timeseries(
        "Verdicts over time",
        [
            _target('sum by (verdict) (rate(chaosgate_pipeline_runs_total[5m]))', "{{verdict}}"),
        ],
        "reqps", _grid(0, 6, 12, 8), pid,
        "Rate of PASS vs FAIL verdicts across every connected repository.",
    )); pid += 1

    panels.append(_timeseries(
        "Gate score by repository",
        [_target("chaosgate_gate_score", "{{repo}}")],
        "short", _grid(12, 6, 12, 8), pid,
        "Most recent composite score. Below 70 means the gate is barely holding.",
    )); pid += 1

    panels.append(_timeseries(
        "Stage duration p95",
        [_target(
            "histogram_quantile(0.95, sum by (le, stage) (rate(chaosgate_stage_duration_seconds_bucket[5m])))",
            "{{stage}}",
        )],
        "s", _grid(0, 14, 12, 8), pid,
        "Which stage is the bottleneck.",
    )); pid += 1

    panels.append(_timeseries(
        "Stage outcomes",
        [_target("sum by (stage, status) (rate(chaosgate_stage_results_total[5m]))", "{{stage}} · {{status}}")],
        "reqps", _grid(12, 14, 12, 8), pid,
    )); pid += 1

    panels.append({
        "id": pid, "type": "row", "title": "Load testing (k6)",
        "gridPos": _grid(0, 22, 24, 1), "collapsed": False, "panels": [],
    }); pid += 1

    panels.append(_timeseries(
        "Load p95 latency",
        [_target("chaosgate_load_p95_milliseconds", "{{repo}} ({{engine}})")],
        "ms", _grid(0, 23, 8, 8), pid,
        "p95 reported by the most recent load stage per repository.",
    )); pid += 1

    panels.append(_timeseries(
        "Load error rate",
        [_target("chaosgate_load_error_rate * 100", "{{repo}} ({{engine}})")],
        "percent", _grid(8, 23, 8, 8), pid,
    )); pid += 1

    panels.append(_timeseries(
        "Throughput",
        [_target("chaosgate_load_requests_per_second", "{{repo}} ({{engine}})")],
        "reqps", _grid(16, 23, 8, 8), pid,
    )); pid += 1

    panels.append(_timeseries(
        "Synthetic request latency distribution",
        [
            _target(
                "histogram_quantile(0.50, sum by (le) (rate(chaosgate_load_request_duration_seconds_bucket[5m])))",
                "p50",
            ),
            _target(
                "histogram_quantile(0.95, sum by (le) (rate(chaosgate_load_request_duration_seconds_bucket[5m])))",
                "p95",
            ),
            _target(
                "histogram_quantile(0.99, sum by (le) (rate(chaosgate_load_request_duration_seconds_bucket[5m])))",
                "p99",
            ),
        ],
        "s", _grid(0, 31, 12, 8), pid,
    )); pid += 1

    panels.append(_timeseries(
        "Chaos recovery time",
        [_target("chaosgate_chaos_recovery_seconds", "{{repo}} · {{experiment}}")],
        "s", _grid(12, 31, 12, 8), pid,
        "How long the target took to serve healthy traffic after being killed.",
    )); pid += 1

    panels.append({
        "id": pid, "type": "row", "title": "Infrastructure",
        "gridPos": _grid(0, 39, 24, 1), "collapsed": False, "panels": [],
    }); pid += 1

    panels.append(_timeseries(
        "Docker build duration p95",
        [_target(
            "histogram_quantile(0.95, sum by (le, repo) (rate(chaosgate_docker_build_duration_seconds_bucket[15m])))",
            "{{repo}}",
        )],
        "s", _grid(0, 40, 8, 7), pid,
    )); pid += 1

    panels.append(_timeseries(
        "Image size",
        [_target("chaosgate_docker_image_size_bytes", "{{repo}}")],
        "bytes", _grid(8, 40, 8, 7), pid,
    )); pid += 1

    panels.append({
        "id": pid,
        "type": "bargauge",
        "title": "Toolchain availability",
        "datasource": DATASOURCE,
        "gridPos": _grid(16, 40, 8, 7),
        "targets": [_target("chaosgate_toolchain_available", "{{tool}}", instant=True)],
        "options": {
            "displayMode": "lcd",
            "orientation": "horizontal",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
        },
        "fieldConfig": {
            "defaults": {
                "max": 1, "min": 0, "unit": "short", "decimals": 0,
                "mappings": [
                    {"type": "value", "options": {"0": {"text": "DEGRADED", "color": "orange", "index": 0}}},
                    {"type": "value", "options": {"1": {"text": "READY", "color": "green", "index": 1}}},
                ],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": "orange", "value": None}, {"color": "green", "value": 1}],
                },
            },
            "overrides": [],
        },
    }); pid += 1

    panels.append(_timeseries(
        "Control-plane request latency p95",
        [_target(
            "histogram_quantile(0.95, sum by (le, endpoint) (rate(chaosgate_http_request_duration_seconds_bucket[5m])))",
            "{{endpoint}}",
        )],
        "s", _grid(0, 47, 12, 7), pid,
    )); pid += 1

    panels.append(_timeseries(
        "GitHub API calls",
        [_target("sum by (operation, result) (rate(chaosgate_github_api_calls_total[5m]))", "{{operation}} · {{result}}")],
        "reqps", _grid(12, 47, 12, 7), pid,
    )); pid += 1

    return {
        "__inputs": [
            {
                "name": "DS_PROMETHEUS",
                "label": "Prometheus",
                "description": "Prometheus instance scraping ChaosGate /metrics",
                "type": "datasource",
                "pluginId": "prometheus",
                "pluginName": "Prometheus",
            }
        ],
        "uid": uid,
        "title": title,
        "tags": ["chaosgate", "ci", "release-gate"],
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "editable": True,
        "graphTooltip": 1,
        "refresh": "10s",
        "time": {"from": "now-3h", "to": "now"},
        "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m"]},
        "templating": {
            "list": [
                {
                    "name": "repo",
                    "type": "query",
                    "label": "Repository",
                    "datasource": DATASOURCE,
                    "query": {"query": "label_values(chaosgate_gate_score, repo)", "refId": "A"},
                    "refresh": 2,
                    "includeAll": True,
                    "multi": True,
                    "current": {"selected": False, "text": "All", "value": "$__all"},
                }
            ]
        },
        "annotations": {
            "list": [
                {
                    "name": "Blocked merges",
                    "datasource": DATASOURCE,
                    "enable": True,
                    "iconColor": "red",
                    "expr": "changes(chaosgate_gate_blocked_total[1m]) > 0",
                    "titleFormat": "Gate sealed",
                }
            ]
        },
        "panels": panels,
    }


def build_run_dashboard(run_id: str, repo: str) -> dict[str, Any]:
    """A focused dashboard scoped to one repository."""
    safe_repo = repo.replace("\\", "")
    panels = [
        _stat("Gate score", f'chaosgate_gate_score{{repo="{safe_repo}"}}', "short", _grid(0, 0, 6, 4), 1,
              thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 60}, {"color": "green", "value": 80}]),
        _stat("Load p95", f'chaosgate_load_p95_milliseconds{{repo="{safe_repo}"}}', "ms", _grid(6, 0, 6, 4), 2, decimals=1),
        _stat("Error rate", f'chaosgate_load_error_rate{{repo="{safe_repo}"}} * 100', "percent", _grid(12, 0, 6, 4), 3, decimals=2),
        _stat("Throughput", f'chaosgate_load_requests_per_second{{repo="{safe_repo}"}}', "reqps", _grid(18, 0, 6, 4), 4, decimals=1),
        _timeseries(
            "Stage durations",
            [_target(
                f'histogram_quantile(0.95, sum by (le, stage) (rate(chaosgate_stage_duration_seconds_bucket[5m])))',
                "{{stage}}",
            )],
            "s", _grid(0, 4, 24, 8), 5,
        ),
    ]
    return {
        "uid": f"cg-{run_id[:30]}",
        "title": f"ChaosGate — {repo}",
        "tags": ["chaosgate", "run"],
        "schemaVersion": 39,
        "version": 1,
        "refresh": "10s",
        "time": {"from": "now-1h", "to": "now"},
        "panels": panels,
    }


def datasource_provisioning(prom_url: str | None = None) -> dict[str, Any]:
    url = prom_url or PROMETHEUS_URL or "http://prometheus:9090"
    return {
        "apiVersion": 1,
        "datasources": [
            {
                "name": "Prometheus",
                "uid": "prometheus",
                "type": "prometheus",
                "access": "proxy",
                "url": url,
                "isDefault": True,
                "editable": True,
                "jsonData": {"httpMethod": "POST", "timeInterval": "10s"},
            }
        ],
    }


def dashboard_provisioning() -> dict[str, Any]:
    return {
        "apiVersion": 1,
        "providers": [
            {
                "name": "chaosgate",
                "orgId": 1,
                "folder": GRAFANA_FOLDER,
                "type": "file",
                "disableDeletion": False,
                "updateIntervalSeconds": 20,
                "allowUiUpdates": True,
                "options": {"path": "/etc/grafana/provisioning/dashboards/chaosgate", "foldersFromFilesStructure": False},
            }
        ],
    }


def _resolve_datasource_uid(client: httpx.Client, headers: dict[str, str]) -> str:
    try:
        res = client.get(f"{GRAFANA_URL}/api/datasources", headers=headers, timeout=8)
        if res.status_code == 200:
            for ds in res.json():
                if ds.get("type") == "prometheus":
                    return ds.get("uid") or "prometheus"
    except Exception:  # noqa: BLE001
        pass
    return "prometheus"


def publish(dashboard: dict[str, Any], folder: str | None = None) -> dict[str, Any]:
    """Push a dashboard to a live Grafana. Returns a result dict, never raises."""
    if not GRAFANA_URL:
        return {"published": False, "reason": "GRAFANA_URL is not configured", "degraded": True}
    if not GRAFANA_API_KEY:
        return {"published": False, "reason": "GRAFANA_API_KEY is not configured", "degraded": True}

    headers = {
        "Authorization": f"Bearer {GRAFANA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = json.loads(json.dumps(dashboard))
    payload.pop("__inputs", None)
    payload.pop("id", None)

    try:
        with httpx.Client(timeout=15) as client:
            uid = _resolve_datasource_uid(client, headers)
            # Bind the dashboard to the real datasource uid.
            payload = json.loads(
                json.dumps(payload).replace("${DS_PROMETHEUS}", uid)
            )
            folder_id = None
            target_folder = folder or GRAFANA_FOLDER
            if target_folder:
                fres = client.get(f"{GRAFANA_URL}/api/folders", headers=headers)
                if fres.status_code == 200:
                    for item in fres.json():
                        if item.get("title") == target_folder:
                            folder_id = item.get("id")
                            break
                if folder_id is None:
                    cres = client.post(
                        f"{GRAFANA_URL}/api/folders",
                        headers=headers,
                        json={"title": target_folder},
                    )
                    if cres.status_code in (200, 201):
                        folder_id = cres.json().get("id")

            body = {"dashboard": payload, "overwrite": True, "message": "Updated by ChaosGate"}
            if folder_id is not None:
                body["folderId"] = folder_id

            res = client.post(f"{GRAFANA_URL}/api/dashboards/db", headers=headers, json=body)
            if res.status_code in (200, 201):
                data = res.json()
                return {
                    "published": True,
                    "uid": data.get("uid"),
                    "url": f"{GRAFANA_URL}{data.get('url', '')}",
                    "version": data.get("version"),
                    "folder": target_folder,
                }
            return {
                "published": False,
                "reason": f"Grafana returned HTTP {res.status_code}: {res.text[:200]}",
            }
    except Exception as exc:  # noqa: BLE001
        return {"published": False, "reason": f"{type(exc).__name__}: {exc}"}


def health() -> dict[str, Any]:
    if not GRAFANA_URL:
        return {"reachable": False, "reason": "GRAFANA_URL unset"}
    try:
        res = httpx.get(f"{GRAFANA_URL}/api/health", timeout=5)
        return {"reachable": res.status_code < 500, "status": res.status_code, "body": res.json()}
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "reason": str(exc)}
