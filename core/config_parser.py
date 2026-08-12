from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "app": {
        "name": "unknown",
        "type": "auto",
        "compose_file": "docker-compose.yml",
    },
    "services": {},
    "tests": {},
    "load": {
        "duration": "20s",
        "vus": 10,
        "endpoints": [],
        "thresholds": {
            "p95_ms": 800,
            "error_rate": 0.05,
        },
    },
    "security": {
        "secret_scan": True,
        "dependency_scan": True,
        "image_scan": False,
    },
    "chaos": {
        "enabled": False,
        "experiments": [],
    },
}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def find_config_path(root: Path) -> Path | None:
    for name in ("chaosgate.yml", "chaosgate.yaml", ".chaosgate.yml"):
        path = root / name
        if path.is_file():
            return path
    return None


def parse_config(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (config, errors). config is None only when the file is invalid YAML."""
    path = find_config_path(root)
    if path is None:
        return None, []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return None, [f"{path.name} must be a YAML mapping"]
        return _deep_merge(DEFAULT_CONFIG, raw), []
    except yaml.YAMLError as exc:
        return None, [f"Invalid YAML in {path.name}: {exc}"]


def summarize_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    if not cfg:
        return {"present": False}
    app = cfg.get("app") or {}
    load = cfg.get("load") or {}
    return {
        "present": True,
        "name": app.get("name"),
        "type": app.get("type"),
        "has_load": bool(load.get("endpoints") or load.get("target")),
        "chaos": bool((cfg.get("chaos") or {}).get("enabled")),
        "services": list((cfg.get("services") or {}).keys()),
    }
