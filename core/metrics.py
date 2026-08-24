"""Prometheus instrumentation for ChaosGate.

Implements the text exposition format directly so the control plane has no
hard dependency on `prometheus_client`. If that library is installed it is
NOT used — a single registry keeps the semantics predictable and testable.

Exposed at GET /metrics.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Any, Iterable

_LOCK = threading.Lock()

# Default latency buckets in seconds (Prometheus convention).
DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, math.inf,
)


def _escape_label(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _fmt(value: float) -> str:
    if value == math.inf:
        return "+Inf"
    if value == -math.inf:
        return "-Inf"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(float(value))


def _key(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _labels_str(key: tuple[tuple[str, str], ...], extra: tuple[str, str] | None = None) -> str:
    parts = [f'{k}="{_escape_label(v)}"' for k, v in key]
    if extra:
        parts.append(f'{extra[0]}="{_escape_label(extra[1])}"')
    return "{" + ",".join(parts) + "}" if parts else ""


class _Metric:
    kind = "untyped"

    def __init__(self, name: str, documentation: str, labelnames: Iterable[str] = ()):
        self.name = name
        self.documentation = documentation
        self.labelnames = tuple(labelnames)
        self._values: dict[tuple[tuple[str, str], ...], Any] = {}

    def _check(self, labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
        labels = labels or {}
        if set(labels) != set(self.labelnames):
            raise ValueError(
                f"{self.name} expects labels {sorted(self.labelnames)}, got {sorted(labels)}"
            )
        return _key(labels)

    def clear(self) -> None:
        with _LOCK:
            self._values.clear()

    def render(self) -> list[str]:  # pragma: no cover - overridden
        return []

    def _header(self) -> list[str]:
        return [
            f"# HELP {self.name} {self.documentation}",
            f"# TYPE {self.name} {self.kind}",
        ]


class Counter(_Metric):
    kind = "counter"

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        if amount < 0:
            raise ValueError("counters cannot decrease")
        key = self._check(labels)
        with _LOCK:
            self._values[key] = self._values.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        return self._values.get(self._check(labels), 0.0)

    def render(self) -> list[str]:
        if not self._values:
            return []
        out = self._header()
        for key, val in sorted(self._values.items()):
            out.append(f"{self.name}{_labels_str(key)} {_fmt(val)}")
        return out


class Gauge(_Metric):
    kind = "gauge"

    def set(self, value: float, **labels: str) -> None:
        key = self._check(labels)
        with _LOCK:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = self._check(labels)
        with _LOCK:
            self._values[key] = self._values.get(key, 0.0) + amount

    def dec(self, amount: float = 1.0, **labels: str) -> None:
        self.inc(-amount, **labels)

    def value(self, **labels: str) -> float:
        return self._values.get(self._check(labels), 0.0)

    def render(self) -> list[str]:
        if not self._values:
            return []
        out = self._header()
        for key, val in sorted(self._values.items()):
            out.append(f"{self.name}{_labels_str(key)} {_fmt(val)}")
        return out


class Histogram(_Metric):
    kind = "histogram"

    def __init__(self, name, documentation, labelnames=(), buckets=DEFAULT_BUCKETS):
        super().__init__(name, documentation, labelnames)
        bounds = sorted(float(b) for b in buckets)
        if not bounds or bounds[-1] != math.inf:
            bounds.append(math.inf)
        self.buckets = tuple(bounds)

    def observe(self, value: float, **labels: str) -> None:
        key = self._check(labels)
        with _LOCK:
            entry = self._values.get(key)
            if entry is None:
                entry = {"counts": [0] * len(self.buckets), "sum": 0.0, "count": 0}
                self._values[key] = entry
            entry["sum"] += float(value)
            entry["count"] += 1
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    entry["counts"][i] += 1

    def snapshot(self, **labels: str) -> dict[str, Any]:
        entry = self._values.get(self._check(labels))
        if not entry:
            return {"count": 0, "sum": 0.0}
        return {"count": entry["count"], "sum": entry["sum"]}

    def render(self) -> list[str]:
        if not self._values:
            return []
        out = self._header()
        for key, entry in sorted(self._values.items()):
            cumulative = 0
            for i, bound in enumerate(self.buckets):
                cumulative = entry["counts"][i]
                out.append(
                    f"{self.name}_bucket{_labels_str(key, ('le', _fmt(bound)))} {cumulative}"
                )
            out.append(f"{self.name}_sum{_labels_str(key)} {_fmt(entry['sum'])}")
            out.append(f"{self.name}_count{_labels_str(key)} {entry['count']}")
        return out


class Registry:
    def __init__(self) -> None:
        self._metrics: dict[str, _Metric] = {}

    def register(self, metric: _Metric) -> _Metric:
        if metric.name in self._metrics:
            return self._metrics[metric.name]
        self._metrics[metric.name] = metric
        return metric

    def counter(self, name, doc, labelnames=()) -> Counter:
        return self.register(Counter(name, doc, labelnames))  # type: ignore[return-value]

    def gauge(self, name, doc, labelnames=()) -> Gauge:
        return self.register(Gauge(name, doc, labelnames))  # type: ignore[return-value]

    def histogram(self, name, doc, labelnames=(), buckets=DEFAULT_BUCKETS) -> Histogram:
        return self.register(Histogram(name, doc, labelnames, buckets))  # type: ignore[return-value]

    def render(self) -> str:
        chunks: list[str] = []
        for name in sorted(self._metrics):
            lines = self._metrics[name].render()
            if lines:
                chunks.append("\n".join(lines))
        return "\n".join(chunks) + "\n" if chunks else "# no metrics recorded yet\n"

    def reset(self) -> None:
        for metric in self._metrics.values():
            metric.clear()


REGISTRY = Registry()

# ----------------------------------------------------------------- Control plane
http_requests_total = REGISTRY.counter(
    "chaosgate_http_requests_total",
    "Total HTTP requests served by the ChaosGate control plane.",
    ["method", "endpoint", "status"],
)
http_request_duration_seconds = REGISTRY.histogram(
    "chaosgate_http_request_duration_seconds",
    "Latency of ChaosGate control-plane HTTP requests.",
    ["method", "endpoint"],
)
build_info = REGISTRY.gauge(
    "chaosgate_build_info",
    "Static build information for the running control plane.",
    ["version", "python"],
)
process_start_time_seconds = REGISTRY.gauge(
    "chaosgate_process_start_time_seconds",
    "Unix timestamp at which the control plane started.",
)

# ------------------------------------------------------------------- Pipeline
pipeline_runs_total = REGISTRY.counter(
    "chaosgate_pipeline_runs_total",
    "Pipeline runs completed, by repository, trigger and verdict.",
    ["repo", "trigger", "verdict"],
)
pipeline_runs_active = REGISTRY.gauge(
    "chaosgate_pipeline_runs_active",
    "Pipeline runs currently executing.",
)
pipeline_duration_seconds = REGISTRY.histogram(
    "chaosgate_pipeline_duration_seconds",
    "Wall-clock duration of a full gate run.",
    ["repo"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, math.inf),
)
stage_duration_seconds = REGISTRY.histogram(
    "chaosgate_stage_duration_seconds",
    "Duration of an individual pipeline stage.",
    ["stage", "status"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 180, math.inf),
)
stage_results_total = REGISTRY.counter(
    "chaosgate_stage_results_total",
    "Stage outcomes across all runs.",
    ["stage", "status"],
)
gate_score = REGISTRY.gauge(
    "chaosgate_gate_score",
    "Most recent gate score (0-100) per repository.",
    ["repo"],
)
gate_blocked_total = REGISTRY.counter(
    "chaosgate_gate_blocked_total",
    "Number of times the gate sealed a merge.",
    ["repo", "reason"],
)

# ----------------------------------------------------------------- Load / k6
load_p95_milliseconds = REGISTRY.gauge(
    "chaosgate_load_p95_milliseconds",
    "p95 latency measured by the most recent load stage.",
    ["repo", "engine"],
)
load_error_rate = REGISTRY.gauge(
    "chaosgate_load_error_rate",
    "Error rate (0-1) measured by the most recent load stage.",
    ["repo", "engine"],
)
load_requests_total = REGISTRY.counter(
    "chaosgate_load_requests_total",
    "Total synthetic requests issued by load stages.",
    ["repo", "engine"],
)
load_request_duration_seconds = REGISTRY.histogram(
    "chaosgate_load_request_duration_seconds",
    "Latency distribution of synthetic load requests.",
    ["repo"],
)
load_rps = REGISTRY.gauge(
    "chaosgate_load_requests_per_second",
    "Throughput achieved by the most recent load stage.",
    ["repo", "engine"],
)

# ------------------------------------------------------------ Security / chaos
security_findings_total = REGISTRY.counter(
    "chaosgate_security_findings_total",
    "Security findings raised by scanners.",
    ["repo", "severity"],
)
chaos_recovery_seconds = REGISTRY.gauge(
    "chaosgate_chaos_recovery_seconds",
    "Time for the target to become healthy after a chaos experiment.",
    ["repo", "experiment"],
)
chaos_experiments_total = REGISTRY.counter(
    "chaosgate_chaos_experiments_total",
    "Chaos experiments executed.",
    ["repo", "experiment", "result"],
)

# ------------------------------------------------------------- Infrastructure
docker_builds_total = REGISTRY.counter(
    "chaosgate_docker_builds_total",
    "Container image builds attempted by the gate.",
    ["repo", "result"],
)
docker_build_duration_seconds = REGISTRY.histogram(
    "chaosgate_docker_build_duration_seconds",
    "Duration of container image builds.",
    ["repo"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, math.inf),
)
docker_image_size_bytes = REGISTRY.gauge(
    "chaosgate_docker_image_size_bytes",
    "Size of the image produced for a repository.",
    ["repo"],
)
k8s_manifests_validated = REGISTRY.gauge(
    "chaosgate_k8s_manifests_validated",
    "Kubernetes manifests validated in the most recent run.",
    ["repo"],
)
k8s_deploy_total = REGISTRY.counter(
    "chaosgate_k8s_deploy_total",
    "Kubernetes deployment attempts.",
    ["repo", "result"],
)
toolchain_available = REGISTRY.gauge(
    "chaosgate_toolchain_available",
    "1 when an external tool is usable on this host, 0 when degraded.",
    ["tool"],
)

# --------------------------------------------------------------- GitHub bridge
github_api_calls_total = REGISTRY.counter(
    "chaosgate_github_api_calls_total",
    "Calls made to the GitHub REST API.",
    ["operation", "result"],
)
github_pushes_total = REGISTRY.counter(
    "chaosgate_github_pushes_total",
    "Commits pushed to GitHub by the workspace editor.",
    ["repo", "result"],
)
webhook_events_total = REGISTRY.counter(
    "chaosgate_webhook_events_total",
    "Inbound GitHub webhook deliveries.",
    ["event", "result"],
)


def record_toolchain(probe_result: dict[str, Any]) -> None:
    for name, tool in (probe_result.get("tools") or {}).items():
        toolchain_available.set(1 if tool.get("available") else 0, tool=name)


def render() -> str:
    return REGISTRY.render()


def bootstrap(version: str = "2.0.0") -> None:
    import sys

    build_info.set(1, version=version, python=f"{sys.version_info.major}.{sys.version_info.minor}")
    process_start_time_seconds.set(time.time())
