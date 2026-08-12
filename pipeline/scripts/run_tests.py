#!/usr/bin/env python3
"""Run the detected unit-test command for a target repository."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_parser import parse_config  # noqa: E402
from core.detector import detect_app  # noqa: E402


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    cfg, _ = parse_config(target)
    detected = detect_app(target, cfg)
    cmd = detected.get("test_command")
    if not cmd:
        print("no unit test command detected")
        return 0
    print(f"$ {cmd}")
    proc = subprocess.run(cmd, cwd=target, shell=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
