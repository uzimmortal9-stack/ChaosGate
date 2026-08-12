#!/usr/bin/env python3
"""CLI wrapper around ChaosGate stack detection. Usable in GitHub Actions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_parser import parse_config  # noqa: E402
from core.detector import detect_app  # noqa: E402


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    cfg, errors = parse_config(target)
    if errors:
        print("config errors:", *errors, sep="\n  ")
        return 2
    detected = detect_app(target, cfg)
    print(json.dumps(detected, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
