from __future__ import annotations

from typing import Any

# What each stage is worth, and what it means when it fails.
STAGE_WEIGHTS: dict[str, tuple[int, str, str]] = {
    # key:      (penalty, policy flag, human reason)
    "validate": (25, "require_config", "Repository is missing a valid chaosgate.yml"),
    "unit": (30, "fail_on_unit", "Unit tests failed"),
    "build": (20, "fail_on_build", "Build failed"),
    "security": (15, None, "Security scan failed"),
    "docker": (20, "fail_on_docker", "Container image build failed"),
    "k8s": (15, "fail_on_k8s", "Kubernetes manifests were rejected"),
    "smoke": (20, None, "Smoke test did not get a healthy response"),
    "load": (25, "fail_on_load", "Load test exceeded gate thresholds"),
    "chaos": (15, "fail_on_chaos", "Service did not recover from the chaos experiment"),
    "prometheus": (5, None, "Metrics endpoint did not validate"),
    "grafana": (0, None, "Dashboard publication failed"),
}


def decide(
    stages: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Turn stage outcomes into an auditable PASS/FAIL with a score."""
    reasons: list[str] = []
    warnings: list[str] = []
    degraded: list[str] = []
    score = 100

    by_key = {s["key"]: s for s in stages}

    def state(key: str) -> str:
        return (by_key.get(key) or {}).get("status") or "pending"

    def is_degraded(key: str) -> bool:
        stage = by_key.get(key) or {}
        return bool(stage.get("degraded") or (stage.get("metrics") or {}).get("degraded"))

    fail_on_degraded = bool(policy.get("fail_on_degraded"))

    for key, (penalty, flag, reason) in STAGE_WEIGHTS.items():
        status = state(key)

        if status == "degraded" or (status in {"passed", "skipped"} and is_degraded(key)):
            stage = by_key.get(key) or {}
            note = stage.get("summary") or reason
            degraded.append(f"{stage.get('name', key)}: {note}")
            score -= 3
            if fail_on_degraded and status == "degraded":
                reasons.append(f"{stage.get('name', key)} ran in degraded mode and policy requires it")
            continue

        if status != "failed":
            if status == "skipped" and key in {"smoke", "load", "chaos", "docker", "k8s"}:
                score -= 2
            continue

        # The stage genuinely failed.
        stage = by_key.get(key) or {}
        detail = stage.get("summary") or reason
        enforced = flag is None or bool(policy.get(flag, True))

        if key == "security":
            # Handled below so the message names the actual findings.
            continue

        if enforced:
            reasons.append(detail)
            score -= penalty
        else:
            warnings.append(f"{detail} (not enforced by policy)")
            score -= max(2, penalty // 4)

    # ---- security is special: critical findings seal the gate outright.
    critical = [
        f for f in findings
        if f.get("severity") == "critical" and f.get("category") in (None, "security", "container", "k8s")
    ]
    secrets = [f for f in critical if f.get("category") in (None, "security")]
    if secrets and policy.get("fail_on_secret", True):
        reasons.append(
            f"{len(secrets)} critical security finding(s) in source — "
            + "; ".join(f.get("title", "finding") for f in secrets[:3])
        )
        score -= 35
    elif secrets:
        warnings.append(f"{len(secrets)} critical security finding(s) (fail_on_secret is off)")
        score -= 10

    infra_critical = [f for f in critical if f.get("category") in ("container", "k8s")]
    if infra_critical:
        titles = "; ".join(f.get("title") or f.get("rule", "issue") for f in infra_critical[:3])
        if policy.get("fail_on_docker", True) or policy.get("fail_on_k8s", True):
            reasons.append(f"{len(infra_critical)} critical infrastructure finding(s) — {titles}")
            score -= 20
        else:
            warnings.append(f"Infrastructure findings: {titles}")
            score -= 5

    if state("security") == "failed" and not secrets:
        reasons.append((by_key.get("security") or {}).get("summary") or "Security scan failed")
        score -= 15

    soft = [f for f in findings if f.get("severity") == "warning"]
    warnings.extend(f.get("title", "warning") for f in soft)
    score -= min(15, 3 * len(soft))

    score = max(0, min(100, score))
    conclusion = "PASS" if not reasons else "FAIL"

    if conclusion == "PASS":
        if degraded:
            summary = (
                f"Gate open. {len(degraded)} stage(s) ran degraded because a tool is "
                "unavailable on this host."
            )
        else:
            summary = "All required gates passed. Merge is allowed."
    else:
        summary = reasons[0]

    return {
        "verdict": conclusion,
        "score": score,
        "summary": summary,
        "reasons": reasons,
        "warnings": warnings,
        "degraded": degraded,
        "block_merge": conclusion == "FAIL",
        "github_state": "success" if conclusion == "PASS" else "failure",
        "counts": {
            "passed": sum(1 for s in stages if s.get("status") == "passed"),
            "failed": sum(1 for s in stages if s.get("status") == "failed"),
            "skipped": sum(1 for s in stages if s.get("status") == "skipped"),
            "degraded": len(degraded),
        },
    }
