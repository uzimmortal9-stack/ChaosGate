from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


DATA_DIR = ROOT / "data"
SAMPLES_DIR = ROOT / "samples"
WORKSPACES_DIR = Path(os.environ.get("WORKSPACES_DIR", str(DATA_DIR / "workspaces")))
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", str(DATA_DIR / "artifacts")))

SECRET_KEY = os.environ.get("SECRET_KEY", "chaosgate-dev-key-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'chaosgate.db'}")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")

# ---------------------------------------------------------------- GitHub OAuth
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "").strip()
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "").strip()
GITHUB_OAUTH_SCOPES = os.environ.get("GITHUB_OAUTH_SCOPES", "repo,workflow,read:org")
OAUTH_ENABLED = bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "").strip()

# ------------------------------------------------------------------- Gate push
PUSH_STRATEGY = os.environ.get("PUSH_STRATEGY", "branch_pr")  # branch_pr | direct
PUSH_BRANCH_PREFIX = os.environ.get("PUSH_BRANCH_PREFIX", "chaosgate")
GIT_AUTHOR_NAME = os.environ.get("GIT_AUTHOR_NAME", "ChaosGate")
GIT_AUTHOR_EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "gate@chaosgate.local")

# ------------------------------------------------------------------- Toolchain
DOCKER_BIN = os.environ.get("DOCKER_BIN", "docker")
KUBECTL_BIN = os.environ.get("KUBECTL_BIN", "kubectl")
K6_BIN = os.environ.get("K6_BIN", "k6")
HELM_BIN = os.environ.get("HELM_BIN", "helm")
K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "chaosgate")
K8S_APPLY = _flag("K8S_APPLY", "0")  # 0 = server/client dry-run only
DOCKER_BUILD = _flag("DOCKER_BUILD", "1")
DOCKER_BUILD_TIMEOUT = int(os.environ.get("DOCKER_BUILD_TIMEOUT", "600"))

# --------------------------------------------------------------- Observability
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "").rstrip("/")
PROMETHEUS_PUSHGATEWAY = os.environ.get("PROMETHEUS_PUSHGATEWAY", "").rstrip("/")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "").rstrip("/")
GRAFANA_API_KEY = os.environ.get("GRAFANA_API_KEY", "").strip()
GRAFANA_FOLDER = os.environ.get("GRAFANA_FOLDER", "ChaosGate")

# ---------------------------------------------------------------- Gate policy
GATE_REQUIRE_CONFIG = _flag("GATE_REQUIRE_CONFIG", "0")
GATE_MAX_P95_MS = int(os.environ.get("GATE_MAX_P95_MS", "800"))
GATE_MAX_ERROR_RATE = float(os.environ.get("GATE_MAX_ERROR_RATE", "0.05"))
GATE_FAIL_ON_SECRET = _flag("GATE_FAIL_ON_SECRET", "1")
GATE_MIN_AVAILABILITY = float(os.environ.get("GATE_MIN_AVAILABILITY", "0.95"))

DEFAULT_POLICY = {
    "require_config": GATE_REQUIRE_CONFIG,
    "max_p95_ms": GATE_MAX_P95_MS,
    "max_error_rate": GATE_MAX_ERROR_RATE,
    "min_availability": GATE_MIN_AVAILABILITY,
    "fail_on_secret": GATE_FAIL_ON_SECRET,
    "fail_on_unit": True,
    "fail_on_build": True,
    "fail_on_chaos": True,
    "fail_on_docker": True,
    "fail_on_k8s": True,
    "fail_on_load": True,
    "warn_unpinned_deps": True,
    # Degraded stages (tool missing on host) never seal the gate by default.
    "fail_on_degraded": False,
}

STAGE_KEYS = [
    "validate",
    "detect",
    "unit",
    "build",
    "security",
    "docker",
    "k8s",
    "smoke",
    "load",
    "prometheus",
    "chaos",
    "grafana",
    "verdict",
]

for _d in (DATA_DIR, WORKSPACES_DIR, ARTIFACTS_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
