from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
SAMPLES_DIR = ROOT / "samples"

SECRET_KEY = os.environ.get("SECRET_KEY", "chaosgate-dev-key-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'chaosgate.db'}")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))

GATE_REQUIRE_CONFIG = os.environ.get("GATE_REQUIRE_CONFIG", "0") == "1"
GATE_MAX_P95_MS = int(os.environ.get("GATE_MAX_P95_MS", "800"))
GATE_MAX_ERROR_RATE = float(os.environ.get("GATE_MAX_ERROR_RATE", "0.05"))
GATE_FAIL_ON_SECRET = os.environ.get("GATE_FAIL_ON_SECRET", "1") == "1"

DEFAULT_POLICY = {
    "require_config": GATE_REQUIRE_CONFIG,
    "max_p95_ms": GATE_MAX_P95_MS,
    "max_error_rate": GATE_MAX_ERROR_RATE,
    "fail_on_secret": GATE_FAIL_ON_SECRET,
    "fail_on_unit": True,
    "fail_on_build": True,
    "fail_on_chaos": True,
    "warn_unpinned_deps": True,
}
