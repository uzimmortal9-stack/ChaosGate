#!/usr/bin/env python3
"""Print the k6 command ChaosGate would run for a contract file."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_parser import parse_config  # noqa: E402


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    cfg, errors = parse_config(target)
    if errors:
        print(*errors, sep="\n")
        return 2
    load = (cfg or {}).get("load") or {}
    print("k6 run pipeline/k6/load.js")
    print("target:", load.get("target") or "(from services)")
    print("vus:", load.get("vus"))
    print("duration:", load.get("duration"))
    for ep in load.get("endpoints") or []:
        print(f"  {ep.get('method', 'GET')} {ep.get('path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
