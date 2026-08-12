from core.verdict import decide


def _stages(**statuses):
    out = []
    for i, (key, status) in enumerate(statuses.items()):
        out.append({"key": key, "name": key, "status": status, "summary": "", "metrics": {}})
    return out


def test_pass_when_required_stages_green():
    stages = _stages(validate="passed", unit="passed", build="passed", security="passed", load="passed")
    report = decide(stages, [], {"fail_on_unit": True, "fail_on_secret": True, "fail_on_build": True})
    assert report["verdict"] == "PASS"
    assert report["block_merge"] is False


def test_fail_on_secret():
    stages = _stages(validate="passed", unit="passed", security="failed")
    findings = [{"severity": "critical", "category": "security", "title": "key"}]
    report = decide(stages, findings, {"fail_on_secret": True, "fail_on_unit": True})
    assert report["verdict"] == "FAIL"
    assert report["block_merge"] is True


def test_fail_on_unit():
    stages = _stages(unit="failed", security="passed")
    report = decide(stages, [], {"fail_on_unit": True, "fail_on_secret": True})
    assert report["verdict"] == "FAIL"
