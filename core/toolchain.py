"""Honest capability detection for the host ChaosGate runs on.

Every infrastructure stage asks this module what is actually available.
Nothing is faked: if `docker` is not installed the Docker stage says so and
degrades to static analysis instead of reporting a build it never ran.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.settings import (
    DOCKER_BIN,
    GRAFANA_API_KEY,
    GRAFANA_URL,
    HELM_BIN,
    K6_BIN,
    KUBECTL_BIN,
    PROMETHEUS_URL,
)

_CACHE_TTL = 20.0
_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "value": None}


@dataclass
class Tool:
    name: str
    binary: str
    available: bool = False
    version: str | None = None
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(cmd: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except FileNotFoundError:
        return 127, "binary not found"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:160]
    return ""


def _probe_docker() -> Tool:
    tool = Tool(name="docker", binary=DOCKER_BIN)
    if not shutil.which(DOCKER_BIN):
        tool.detail = "docker CLI is not on PATH"
        return tool
    code, out = _run([DOCKER_BIN, "version", "--format", "{{.Server.Version}}"], timeout=10)
    if code == 0 and out and "error" not in out.lower():
        tool.available = True
        tool.version = _first_line(out)
        tool.detail = f"Docker daemon {tool.version} reachable"
    else:
        tool.detail = "docker CLI present but the daemon is not reachable"
        tool.extra["stderr"] = _first_line(out)
    code, out = _run([DOCKER_BIN, "compose", "version", "--short"], timeout=10)
    tool.extra["compose"] = code == 0
    tool.extra["compose_version"] = _first_line(out) if code == 0 else None
    code, out = _run([DOCKER_BIN, "buildx", "version"], timeout=10)
    tool.extra["buildx"] = code == 0
    return tool


def _probe_kubectl() -> Tool:
    tool = Tool(name="kubectl", binary=KUBECTL_BIN)
    if not shutil.which(KUBECTL_BIN):
        tool.detail = "kubectl is not on PATH"
        return tool
    code, out = _run([KUBECTL_BIN, "version", "--client=true", "-o", "yaml"], timeout=10)
    client_version = None
    for line in out.splitlines():
        if "gitVersion" in line:
            client_version = line.split(":", 1)[1].strip().strip('"')
            break
    tool.version = client_version or "unknown"
    code, out = _run([KUBECTL_BIN, "cluster-info", "--request-timeout=6s"], timeout=12)
    if code == 0:
        tool.available = True
        tool.detail = "cluster reachable"
        tool.extra["cluster_info"] = _first_line(out)
        ctx_code, ctx = _run([KUBECTL_BIN, "config", "current-context"], timeout=6)
        tool.extra["context"] = _first_line(ctx) if ctx_code == 0 else None
    else:
        tool.detail = "kubectl present but no cluster is reachable"
        tool.extra["stderr"] = _first_line(out)
    return tool


def _probe_k6() -> Tool:
    tool = Tool(name="k6", binary=K6_BIN)
    if not shutil.which(K6_BIN):
        tool.detail = "k6 binary is not installed — using the built-in generator"
        return tool
    code, out = _run([K6_BIN, "version"], timeout=10)
    if code == 0:
        tool.available = True
        tool.version = _first_line(out)
        tool.detail = f"{tool.version} ready"
    else:
        tool.detail = "k6 present but not runnable"
    return tool


def _probe_helm() -> Tool:
    tool = Tool(name="helm", binary=HELM_BIN)
    if not shutil.which(HELM_BIN):
        tool.detail = "helm is not on PATH (optional)"
        return tool
    code, out = _run([HELM_BIN, "version", "--short"], timeout=10)
    tool.available = code == 0
    tool.version = _first_line(out) if code == 0 else None
    tool.detail = "helm ready" if code == 0 else "helm not runnable"
    return tool


def _probe_git() -> Tool:
    tool = Tool(name="git", binary="git")
    code, out = _run(["git", "--version"], timeout=8)
    tool.available = code == 0
    tool.version = _first_line(out)
    tool.detail = tool.version if code == 0 else "git is required for repository operations"
    return tool


def _probe_http(name: str, url: str, path: str, note: str) -> Tool:
    tool = Tool(name=name, binary=url or "(unset)")
    if not url:
        tool.detail = note
        return tool
    try:
        import httpx

        res = httpx.get(url + path, timeout=4.0)
        tool.available = res.status_code < 500
        tool.detail = f"HTTP {res.status_code} from {url}"
        tool.extra["status"] = res.status_code
    except Exception as exc:  # noqa: BLE001
        tool.detail = f"{url} unreachable: {type(exc).__name__}"
    return tool


def _probe_prometheus() -> Tool:
    tool = _probe_http(
        "prometheus",
        PROMETHEUS_URL,
        "/-/healthy",
        "PROMETHEUS_URL is unset — ChaosGate still exposes /metrics for scraping",
    )
    tool.extra["exposition"] = "/metrics"
    return tool


def _probe_grafana() -> Tool:
    tool = _probe_http(
        "grafana",
        GRAFANA_URL,
        "/api/health",
        "GRAFANA_URL is unset — dashboards are generated as provisionable JSON",
    )
    tool.extra["api_key"] = bool(GRAFANA_API_KEY)
    if tool.available and not GRAFANA_API_KEY:
        tool.detail += " (no GRAFANA_API_KEY — cannot publish)"
    return tool


def probe(force: bool = False) -> dict[str, Any]:
    """Return the full capability map, cached briefly so stages stay fast."""
    with _lock:
        now = time.time()
        if not force and _cache["value"] is not None and now - _cache["at"] < _CACHE_TTL:
            return _cache["value"]

    tools = {
        "git": _probe_git(),
        "docker": _probe_docker(),
        "kubectl": _probe_kubectl(),
        "k6": _probe_k6(),
        "helm": _probe_helm(),
        "prometheus": _probe_prometheus(),
        "grafana": _probe_grafana(),
    }
    value = {
        "tools": {k: v.to_dict() for k, v in tools.items()},
        "checked_at": time.time(),
        "summary": {
            "container_builds": tools["docker"].available,
            "orchestration": tools["kubectl"].available,
            "real_k6": tools["k6"].available,
            "metrics_backend": tools["prometheus"].available,
            "dashboards": tools["grafana"].available and bool(GRAFANA_API_KEY),
        },
    }
    with _lock:
        _cache["value"] = value
        _cache["at"] = time.time()
    return value


def get(name: str, force: bool = False) -> dict[str, Any]:
    return probe(force=force)["tools"].get(name, {"name": name, "available": False, "detail": "unknown tool"})


def available(name: str) -> bool:
    return bool(get(name).get("available"))
