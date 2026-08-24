"""Post-merge recovery.

Answers "what if broken code is already merged?" — the pre-merge gate cannot
help, so the system must detect it, name the last good commit, and propose a
revert without unilaterally rewriting a shared branch.
"""

from datetime import datetime, timedelta

import pytest

from core import recovery
from core.models import PipelineRun, Repository, Stage, Workspace


@pytest.fixture()
def session(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core.db import Base

    engine = create_engine(f"sqlite:///{tmp_path}/rec.db")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


@pytest.fixture()
def repo(session):
    ws = Workspace(id=1, mode="demo")
    session.add(ws)
    r = Repository(
        id="repo_1", workspace_id=1, owner="acme", name="api",
        full_name="acme/api", default_branch="main",
        html_url="https://github.com/acme/api", is_sample=False,
    )
    session.add(r)
    session.commit()
    return r


def _run(session, repo, sha, conclusion, when, branch="main", score=100, pr=None):
    run = PipelineRun(
        id=f"run_{sha}", repo_id=repo.id, status="passed" if conclusion == "PASS" else "failed",
        conclusion=conclusion, branch=branch, commit_sha=sha, score=score,
        created_at=when, finished_at=when, pr_number=pr, trigger="push",
    )
    session.add(run)
    session.commit()
    return run


def test_last_good_commit_finds_most_recent_pass(session, repo):
    base = datetime(2026, 1, 1, 12, 0, 0)
    _run(session, repo, "aaa1111", "PASS", base, score=90)
    _run(session, repo, "bbb2222", "PASS", base + timedelta(hours=1), score=95)
    _run(session, repo, "ccc3333", "FAIL", base + timedelta(hours=2), score=10)

    good = recovery.last_good_commit(session, repo)
    assert good["sha"] == "bbb2222"
    assert good["score"] == 95


def test_last_good_ignores_runs_after_the_failure(session, repo):
    base = datetime(2026, 1, 1, 12, 0, 0)
    _run(session, repo, "aaa1111", "PASS", base, score=90)
    bad = _run(session, repo, "ccc3333", "FAIL", base + timedelta(hours=1))
    _run(session, repo, "ddd4444", "PASS", base + timedelta(hours=2))

    good = recovery.last_good_commit(session, repo, before_run=bad)
    assert good["sha"] == "aaa1111"


def test_last_good_ignores_other_branches(session, repo):
    base = datetime(2026, 1, 1, 12, 0, 0)
    _run(session, repo, "feat111", "PASS", base, branch="feature/x")
    assert recovery.last_good_commit(session, repo) is None


def test_no_good_commit_returns_none(session, repo):
    _run(session, repo, "ccc3333", "FAIL", datetime(2026, 1, 1))
    assert recovery.last_good_commit(session, repo) is None


def test_revert_plan_when_good_commit_exists(session, repo):
    base = datetime(2026, 1, 1, 12, 0, 0)
    _run(session, repo, "aaa1111", "PASS", base, score=92)
    bad = _run(session, repo, "ccc3333", "FAIL", base + timedelta(hours=1))

    plan = recovery.build_revert_plan(session, repo, bad)
    assert plan["strategy"] == "revert"
    assert plan["bad_commit"] == "ccc3333"
    assert plan["last_good"]["sha"] == "aaa1111"
    assert plan["recoverable"] is True
    assert any("git revert" in c for c in plan["commands"])
    assert "aaa1111" in plan["summary"]


def test_revert_plan_falls_back_to_roll_forward(session, repo):
    """With no verified good commit there is nowhere safe to go back to."""
    bad = _run(session, repo, "ccc3333", "FAIL", datetime(2026, 1, 1))
    plan = recovery.build_revert_plan(session, repo, bad)
    assert plan["strategy"] == "roll-forward"
    assert plan["last_good"] is None
    assert "fix forward" in plan["summary"].lower()


def test_revert_plan_without_commit_sha(session, repo):
    run = PipelineRun(
        id="run_x", repo_id=repo.id, status="failed", conclusion="FAIL",
        branch="main", commit_sha=None, created_at=datetime(2026, 1, 1),
    )
    session.add(run)
    session.commit()
    plan = recovery.build_revert_plan(session, repo, run)
    assert plan["recoverable"] is False
    assert plan["strategy"] == "manual"
    assert plan["commands"] == []


def test_failing_stages_extracted(session, repo):
    run = _run(session, repo, "ccc3333", "FAIL", datetime(2026, 1, 1))
    session.add_all([
        Stage(run_id=run.id, key="unit", name="Unit tests", index=2,
              status="failed", summary="2 failed"),
        Stage(run_id=run.id, key="build", name="Build", index=3, status="passed"),
        Stage(run_id=run.id, key="load", name="Load test", index=8,
              status="failed", summary="p95 too high"),
    ])
    session.commit()
    session.refresh(run)

    stages = recovery.failing_stages(run)
    assert [s["key"] for s in stages] == ["unit", "load"]
    assert stages[0]["summary"] == "2 failed"


def test_incident_body_names_stages_and_fix(session, repo):
    base = datetime(2026, 1, 1, 12, 0, 0)
    _run(session, repo, "aaa1111", "PASS", base, score=92)
    bad = _run(session, repo, "ccc3333", "FAIL", base + timedelta(hours=1), score=20)
    session.add(Stage(run_id=bad.id, key="unit", name="Unit tests", index=2,
                      status="failed", summary="2 tests failed"))
    session.commit()
    session.refresh(bad)

    plan = recovery.build_revert_plan(session, repo, bad)
    report = {
        "reasons": ["Unit tests failed"],
        "findings": [{
            "severity": "critical", "title": "Credential file committed: .env",
            "detail": "…", "remediation": "git rm --cached .env",
        }],
    }
    body = recovery.incident_body(repo, bad, plan, report)

    assert "ccc3333" in body
    assert "Unit tests" in body
    assert "2 tests failed" in body
    assert "Credential file committed" in body
    assert "git rm --cached .env" in body
    assert "aaa1111" in body
    assert "required status check" in body
    assert "git revert" in body


def test_incident_body_without_report(session, repo):
    bad = _run(session, repo, "ccc3333", "FAIL", datetime(2026, 1, 1))
    plan = recovery.build_revert_plan(session, repo, bad)
    body = recovery.incident_body(repo, bad, plan, None)
    assert "ChaosGate" in body
    assert "ccc3333" in body


def test_open_incident_requires_token(session, repo):
    bad = _run(session, repo, "ccc3333", "FAIL", datetime(2026, 1, 1))
    plan = recovery.build_revert_plan(session, repo, bad)
    result = recovery.open_incident("", repo, bad, plan, None)
    assert result["created"] is False
    assert "token" in result["reason"]


def test_execute_revert_requires_token():
    result = recovery.execute_revert("repo_1", "acme/api", "", "abc123", "main")
    assert result["ok"] is False
    assert "token" in result["reason"]
