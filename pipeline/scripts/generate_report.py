#!/usr/bin/env python3
"""Turn stage records on stdin into a ChaosGate verdict JSON."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.settings import DEFAULT_POLICY  # noqa: E402
from core.verdict import decide  # noqa: E402


def main() -> int:
    payload = json.load(sys.stdin)
    report = decide(payload.get("stages") or [], payload.get("findings") or [], payload.get("policy") or DEFAULT_POLICY)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
