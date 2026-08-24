#!/usr/bin/env python3
"""Regenerate the provisioned Grafana dashboard and Prometheus rules.

The dashboard shipped in docker/ is generated from core/grafana.py so the
panels can never drift from the metric names the application actually emits.

    python scripts/generate_observability.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import grafana, prometheus  # noqa: E402

DASHBOARD = ROOT / "docker/grafana/provisioning/dashboards/chaosgate/chaosgate.json"
ALERTS = ROOT / "docker/prometheus/alerts.yml"
SCRAPE = ROOT / "docker/prometheus/prometheus.yml"


def main() -> int:
    dashboard = grafana.build_dashboard()
    dashboard.pop("__inputs", None)
    body = json.dumps(dashboard, indent=2).replace("${DS_PROMETHEUS}", "prometheus")

    DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD.write_text(body + "\n", encoding="utf-8")
    panels = len([p for p in dashboard["panels"] if p.get("type") != "row"])
    print(f"✓ {DASHBOARD.relative_to(ROOT)} — {panels} panels")

    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    ALERTS.write_text(prometheus.ALERT_RULES, encoding="utf-8")
    print(f"✓ {ALERTS.relative_to(ROOT)}")

    if not SCRAPE.is_file():
        import yaml

        SCRAPE.write_text(
            yaml.safe_dump(prometheus.scrape_config(), sort_keys=False), encoding="utf-8"
        )
        print(f"✓ {SCRAPE.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
