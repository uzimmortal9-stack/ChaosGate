"""The verdict is the product. Degraded must never be confused with passing,
and it must never be confused with failing either."""

from core.verdict import decide

POLICY = {
    "fail_on_unit": True, "fail_on_build": True, "fail_on_secret": True,
    "fail_on_chaos": True, "fail_on_docker": True, "fail_on_k8s": True,
    "fail_on_load": True, "fail_on_degraded": False, "require_config": False,
}


def stages(**statuses):
    return [
        {"key": key, "name": key.title(), "status": status, "summary": "", "metrics": {}, "degraded": False}
        for key, status in statuses.items()
    ]


def test_all_green_passes():
    report = decide(stages(validate="passed", unit="passed", build="passed",
                           security="passed", load="passed"), [], POLICY)
    assert report["verdict"] == "PASS"
    assert report["block_merge"] is False
    assert report["github_state"] == "success"
    assert report["score"] == 100


def test_unit_failure_blocks():
    report = decide(stages(unit="failed", security="passed"), [], POLICY)
    assert report["verdict"] == "FAIL"
    assert report["block_merge"] is True
    assert report["github_state"] == "failure"
    assert "Unit" in report["reasons"][0] or "unit" in report["reasons"][0].lower()


def test_committed_secret_blocks():
    findings = [{"severity": "critical", "category": "security", "title": "AWS key committed"}]
    report = decide(stages(unit="passed", security="failed"), findings, POLICY)
    assert report["verdict"] == "FAIL"
    assert "AWS key committed" in report["reasons"][0]


def test_secret_allowed_when_policy_disabled():
    findings = [{"severity": "critical", "category": "security", "title": "key"}]
    policy = {**POLICY, "fail_on_secret": False}
    report = decide(stages(unit="passed", security="passed"), findings, policy)
    assert report["verdict"] == "PASS"
    assert any("fail_on_secret is off" in w for w in report["warnings"])


def test_docker_failure_blocks():
    report = decide(stages(unit="passed", docker="failed"), [], POLICY)
    assert report["verdict"] == "FAIL"


def test_docker_failure_ignored_when_policy_off():
    policy = {**POLICY, "fail_on_docker": False}
    report = decide(stages(unit="passed", docker="failed"), [], policy)
    assert report["verdict"] == "PASS"
    assert report["warnings"]


def test_k8s_failure_blocks():
    report = decide(stages(unit="passed", k8s="failed"), [], POLICY)
    assert report["verdict"] == "FAIL"


def test_degraded_does_not_block_by_default():
    """No Docker daemon must not be reported as a failed build."""
    items = stages(unit="passed", docker="degraded", k8s="degraded",
                   load="degraded", prometheus="degraded", grafana="degraded")
    report = decide(items, [], POLICY)
    assert report["verdict"] == "PASS"
    assert report["block_merge"] is False
    assert len(report["degraded"]) == 5
    assert report["score"] < 100  # honest: not a perfect score either
    assert report["counts"]["degraded"] == 5


def test_degraded_blocks_in_strict_mode():
    policy = {**POLICY, "fail_on_degraded": True}
    report = decide(stages(unit="passed", docker="degraded"), [], policy)
    assert report["verdict"] == "FAIL"
    assert "degraded" in report["reasons"][0].lower()


def test_degraded_summary_is_explicit():
    report = decide(stages(unit="passed", load="degraded"), [], POLICY)
    assert "degraded" in report["summary"].lower()


def test_infrastructure_findings_block():
    findings = [{"severity": "critical", "category": "k8s", "title": "Kubernetes: privileged",
                 "rule": "privileged"}]
    report = decide(stages(unit="passed", k8s="passed"), findings, POLICY)
    assert report["verdict"] == "FAIL"
    assert "infrastructure" in report["reasons"][0].lower()


def test_warnings_reduce_score_without_blocking():
    findings = [{"severity": "warning", "category": "security", "title": f"warn {i}"} for i in range(3)]
    report = decide(stages(unit="passed", build="passed"), findings, POLICY)
    assert report["verdict"] == "PASS"
    assert report["score"] < 100
    assert len(report["warnings"]) == 3


def test_load_threshold_breach_uses_stage_summary():
    items = stages(unit="passed")
    items.append({"key": "load", "name": "Load", "status": "failed",
                  "summary": "p95 1200ms exceeds 800ms", "metrics": {}, "degraded": False})
    report = decide(items, [], POLICY)
    assert report["verdict"] == "FAIL"
    assert "1200ms" in report["reasons"][0]


def test_skipped_runtime_stages_are_not_failures():
    report = decide(stages(unit="passed", build="passed", smoke="skipped",
                           load="skipped", chaos="skipped"), [], POLICY)
    assert report["verdict"] == "PASS"
    assert report["counts"]["skipped"] == 3


def test_counts_are_accurate():
    items = stages(unit="passed", build="passed", docker="failed", k8s="skipped", load="degraded")
    report = decide(items, [], POLICY)
    assert report["counts"]["passed"] == 2
    assert report["counts"]["failed"] == 1
    assert report["counts"]["skipped"] == 1
    assert report["counts"]["degraded"] == 1


def test_score_never_leaves_range():
    findings = [{"severity": "critical", "category": "security", "title": f"s{i}"} for i in range(10)]
    report = decide(stages(unit="failed", build="failed", docker="failed",
                           k8s="failed", load="failed", chaos="failed", smoke="failed"),
                    findings, POLICY)
    assert 0 <= report["score"] <= 100
    assert report["verdict"] == "FAIL"
