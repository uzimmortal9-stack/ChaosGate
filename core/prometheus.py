"""Prometheus query + pushgateway client.

Used by the `prometheus` pipeline stage to (a) confirm ChaosGate's own
exposition endpoint parses, (b) query a real Prometheus server for the
target's metrics when one is configured, and (c) push run-scoped metrics to a
Pushgateway so short-lived CI jobs are still scrapeable.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from core.settings import PROMETHEUS_PUSHGATEWAY, PROMETHEUS_URL

_SAMPLE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?"
    r"\s+(?P<value>[^\s]+)(?:\s+(?P<ts>\d+))?$"
)


def parse_exposition(text: str) -> dict[str, Any]:
    """Parse the Prometheus text exposition format. Validates our own output."""
    families: dict[str, dict[str, Any]] = {}
    samples: list[dict[str, Any]] = []
    errors: list[str] = []

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            parts = line.split(None, 3)
            if len(parts) >= 3 and parts[1] == "HELP":
                families.setdefault(parts[2], {})["help"] = parts[3] if len(parts) > 3 else ""
            elif len(parts) >= 4 and parts[1] == "TYPE":
                families.setdefault(parts[2], {})["type"] = parts[3]
            continue

        match = _SAMPLE.match(line)
        if not match:
            errors.append(f"line {lineno}: unparseable sample {line[:80]!r}")
            continue

        value_text = match.group("value")
        try:
            value = float(value_text)
        except ValueError:
            if value_text in {"+Inf", "-Inf", "NaN"}:
                value = float(value_text.replace("+", ""))
            else:
                errors.append(f"line {lineno}: bad value {value_text!r}")
                continue

        labels: dict[str, str] = {}
        raw_labels = match.group("labels")
        if raw_labels:
            for pair in re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', raw_labels):
                labels[pair[0]] = pair[1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")

        samples.append({"name": match.group("name"), "labels": labels, "value": value})

    return {
        "valid": not errors,
        "errors": errors,
        "families": families,
        "family_count": len(families),
        "sample_count": len(samples),
        "samples": samples,
    }


def summarize(text: str) -> dict[str, Any]:
    parsed = parse_exposition(text)
    by_type: dict[str, int] = {}
    for meta in parsed["families"].values():
        kind = meta.get("type", "untyped")
        by_type[kind] = by_type.get(kind, 0) + 1
    return {
        "valid": parsed["valid"],
        "errors": parsed["errors"][:10],
        "families": parsed["family_count"],
        "samples": parsed["sample_count"],
        "by_type": by_type,
        "names": sorted(parsed["families"].keys())[:80],
    }


def configured() -> bool:
    return bool(PROMETHEUS_URL)


def query(expr: str, timeout: float = 8.0) -> dict[str, Any]:
    if not PROMETHEUS_URL:
        return {"ok": False, "reason": "PROMETHEUS_URL is not configured", "degraded": True}
    try:
        res = httpx.get(
            f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr}, timeout=timeout
        )
        if res.status_code != 200:
            return {"ok": False, "reason": f"HTTP {res.status_code}", "body": res.text[:300]}
        doc = res.json()
        if doc.get("status") != "success":
            return {"ok": False, "reason": doc.get("error") or "query rejected"}
        result = (doc.get("data") or {}).get("result") or []
        return {
            "ok": True,
            "expr": expr,
            "result_type": (doc.get("data") or {}).get("resultType"),
            "series": len(result),
            "result": result[:50],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}


def query_range(expr: str, start: float, end: float, step: str = "15s") -> dict[str, Any]:
    if not PROMETHEUS_URL:
        return {"ok": False, "reason": "PROMETHEUS_URL is not configured", "degraded": True}
    try:
        res = httpx.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": expr, "start": start, "end": end, "step": step},
            timeout=15,
        )
        if res.status_code != 200:
            return {"ok": False, "reason": f"HTTP {res.status_code}"}
        doc = res.json()
        return {"ok": doc.get("status") == "success", "result": (doc.get("data") or {}).get("result") or []}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}


def targets() -> dict[str, Any]:
    if not PROMETHEUS_URL:
        return {"ok": False, "reason": "PROMETHEUS_URL is not configured", "degraded": True}
    try:
        res = httpx.get(f"{PROMETHEUS_URL}/api/v1/targets", timeout=8)
        if res.status_code != 200:
            return {"ok": False, "reason": f"HTTP {res.status_code}"}
        active = ((res.json().get("data") or {}).get("activeTargets")) or []
        return {
            "ok": True,
            "count": len(active),
            "up": sum(1 for t in active if t.get("health") == "up"),
            "targets": [
                {
                    "job": (t.get("labels") or {}).get("job"),
                    "instance": (t.get("labels") or {}).get("instance"),
                    "health": t.get("health"),
                    "last_error": t.get("lastError"),
                }
                for t in active[:40]
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}


def push_metrics(job: str, payload: str, grouping: dict[str, str] | None = None) -> dict[str, Any]:
    """Send metrics to a Pushgateway so ephemeral runs remain scrapeable."""
    if not PROMETHEUS_PUSHGATEWAY:
        return {"pushed": False, "reason": "PROMETHEUS_PUSHGATEWAY is not configured", "degraded": True}
    path = f"{PROMETHEUS_PUSHGATEWAY}/metrics/job/{job}"
    for key, value in (grouping or {}).items():
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))
        path += f"/{key}/{safe}"
    body = payload if payload.endswith("\n") else payload + "\n"
    try:
        res = httpx.post(
            path, content=body.encode("utf-8"),
            headers={"Content-Type": "text/plain; version=0.0.4"}, timeout=10,
        )
        return {
            "pushed": res.status_code in (200, 202),
            "status": res.status_code,
            "url": path,
            "reason": None if res.status_code in (200, 202) else res.text[:200],
        }
    except Exception as exc:  # noqa: BLE001
        return {"pushed": False, "reason": f"{type(exc).__name__}: {exc}"}


def scrape_config(job: str = "chaosgate", target: str = "chaosgate:5000") -> dict[str, Any]:
    return {
        "global": {"scrape_interval": "10s", "evaluation_interval": "10s"},
        "scrape_configs": [
            {
                "job_name": job,
                "metrics_path": "/metrics",
                "static_configs": [{"targets": [target], "labels": {"service": "chaosgate"}}],
            }
        ],
        "rule_files": ["/etc/prometheus/rules/*.yml"],
    }


ALERT_RULES = """groups:
  - name: chaosgate
    interval: 30s
    rules:
      - alert: ChaosGateBlockingMerges
        expr: increase(chaosgate_gate_blocked_total[15m]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "ChaosGate sealed a merge on {{ $labels.repo }}"
          description: "Reason: {{ $labels.reason }}."

      - alert: ChaosGateLoadRegression
        expr: chaosgate_load_p95_milliseconds > 800
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "p95 latency regression on {{ $labels.repo }}"
          description: "p95 is {{ $value | printf \\"%.0f\\" }}ms, above the 800ms gate threshold."

      - alert: ChaosGateHighErrorRate
        expr: chaosgate_load_error_rate > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Load error rate above 5% on {{ $labels.repo }}"

      - alert: ChaosGateSecretCommitted
        expr: increase(chaosgate_security_findings_total{severity="critical"}[10m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "Critical security finding on {{ $labels.repo }}"

      - alert: ChaosGateToolchainDegraded
        expr: chaosgate_toolchain_available == 0
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "{{ $labels.tool }} is unavailable on the ChaosGate host"
          description: "The corresponding pipeline stage runs in degraded mode."

      - alert: ChaosGateSlowPipeline
        expr: histogram_quantile(0.95, sum by (le) (rate(chaosgate_pipeline_duration_seconds_bucket[30m]))) > 300
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "Gate runs are taking over 5 minutes at p95"
"""
