from __future__ import annotations

from typing import Any


def decide(stages: list[dict[str, Any]], findings: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    score = 100

    by_key = {s["key"]: s for s in stages}

    def failed(key: str) -> bool:
        return (by_key.get(key) or {}).get("status") == "failed"

    def skipped(key: str) -> bool:
        return (by_key.get(key) or {}).get("status") == "skipped"

    if policy.get("require_config") and failed("validate"):
        reasons.append("Repository is missing a valid chaosgate.yml")
        score -= 25

    if policy.get("fail_on_unit") and failed("unit"):
        reasons.append("Unit tests failed")
        score -= 30

    if policy.get("fail_on_build") and failed("build"):
        reasons.append("Build failed")
        score -= 20

    if failed("smoke"):
        reasons.append("Smoke test did not get a healthy response")
        score -= 20

    if failed("load"):
        reasons.append((by_key.get("load") or {}).get("summary") or "Load test exceeded gate thresholds")
        score -= 25

    secrets = [f for f in findings if f.get("category") == "security" and f.get("severity") == "critical"]
    if policy.get("fail_on_secret") and secrets:
        reasons.append(f"{len(secrets)} critical secret(s) found in source")
        score -= 35

    if policy.get("fail_on_chaos") and failed("chaos"):
        reasons.append("Service did not recover from chaos experiment")
        score -= 15

    if failed("security") and not secrets:
        reasons.append("Security scan failed")
        score -= 15

    warnings = [f for f in findings if f.get("severity") == "warning"]
    score -= min(15, 3 * len(warnings))

    # Skipped runtime stages are not automatic failures
    for key in ("smoke", "load", "chaos"):
        if skipped(key):
            score -= 2

    score = max(0, min(100, score))
    conclusion = "PASS" if not reasons else "FAIL"
    if conclusion == "PASS" and score < 70:
        conclusion = "PASS"
    summary = (
        "All required gates passed. Merge is allowed."
        if conclusion == "PASS"
        else reasons[0]
    )
    return {
        "verdict": conclusion,
        "score": score,
        "summary": summary,
        "reasons": reasons,
        "block_merge": conclusion == "FAIL",
        "warnings": [f["title"] for f in warnings],
    }
