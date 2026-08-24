"""Post-merge detection and recovery.

The pre-merge gate only protects changes that arrive through a pull request.
It does nothing about code that is *already* on the default branch — merged
before the gate existed, pushed directly by an admin, or merged with the check
bypassed.

This module closes that hole:

* ``last_good_commit``  — the newest commit on main that the gate passed
* ``build_revert_plan`` — what it would take to get back there
* ``open_incident``     — file a GitHub issue naming the stage and the fix
* ``execute_revert``    — create a revert branch + PR (never force-push)

Reverting is deliberately proposed as a pull request rather than pushed
straight to main. Automatically rewriting a shared branch is how a recovery
tool becomes the outage.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from core import github_client
from core.github_client import GitHubError
from core.models import PipelineRun, Repository

INCIDENT_LABEL = "chaosgate-incident"


# ------------------------------------------------------------- known-good
def last_good_commit(session, repo: Repository, before_run: PipelineRun | None = None) -> dict[str, Any] | None:
    """The most recent commit on the default branch that passed the gate."""
    query = (
        session.query(PipelineRun)
        .filter(
            PipelineRun.repo_id == repo.id,
            PipelineRun.conclusion == "PASS",
            PipelineRun.branch == repo.default_branch,
            PipelineRun.commit_sha.isnot(None),
        )
    )
    if before_run is not None and before_run.created_at:
        query = query.filter(PipelineRun.created_at < before_run.created_at)

    run = query.order_by(PipelineRun.created_at.desc()).first()
    if not run:
        return None
    return {
        "run_id": run.id,
        "sha": run.commit_sha,
        "short_sha": (run.commit_sha or "")[:7],
        "score": run.score,
        "at": run.finished_at.isoformat() + "Z" if run.finished_at else None,
        "message": run.commit_message,
    }


def failing_stages(run: PipelineRun) -> list[dict[str, str]]:
    out = []
    for stage in sorted(run.stages, key=lambda s: s.index):
        if stage.status == "failed":
            out.append({"key": stage.key, "name": stage.name, "summary": stage.summary or ""})
    return out


# ------------------------------------------------------------- revert plan
def build_revert_plan(session, repo: Repository, run: PipelineRun) -> dict[str, Any]:
    """Describe how to recover, without performing anything."""
    good = last_good_commit(session, repo, before_run=run)
    stages = failing_stages(run)
    bad_sha = run.commit_sha
    short = (bad_sha or "")[:7]

    plan: dict[str, Any] = {
        "repo": repo.full_name,
        "branch": run.branch,
        "bad_commit": bad_sha,
        "bad_commit_short": short,
        "run_id": run.id,
        "failing_stages": stages,
        "last_good": good,
        "recoverable": bool(bad_sha),
    }

    if not bad_sha:
        plan["strategy"] = "manual"
        plan["reason"] = "This run has no commit SHA, so there is nothing to revert."
        plan["commands"] = []
        return plan

    if good and good["sha"] != bad_sha:
        plan["strategy"] = "revert"
        plan["summary"] = (
            f"Revert {short} on {run.branch}. Last known-good commit is "
            f"{good['short_sha']} (gate score {good['score']})."
        )
        plan["commands"] = [
            f"git fetch origin {run.branch}",
            f"git checkout -b chaosgate/revert-{short} origin/{run.branch}",
            f"git revert --no-edit {bad_sha}",
            f"git push origin chaosgate/revert-{short}",
            "# then open a PR from that branch",
        ]
    else:
        plan["strategy"] = "roll-forward"
        plan["summary"] = (
            f"No earlier passing run is recorded for {run.branch}, so there is no verified "
            f"good commit to return to. Fix forward: address the failing stage(s) and push."
        )
        plan["commands"] = [
            f"git checkout -b chaosgate/fix-{short} {run.branch}",
            "# fix the failing stage(s) listed above",
            f"git push origin chaosgate/fix-{short}",
        ]
    return plan


# ---------------------------------------------------------------- incident
def incident_body(repo: Repository, run: PipelineRun, plan: dict[str, Any], report: dict[str, Any] | None) -> str:
    stages = plan["failing_stages"]
    lines = [
        f"## ChaosGate detected a failing gate on `{run.branch}`",
        "",
        f"Commit **`{plan['bad_commit_short']}`** is on the default branch and does not pass "
        f"the release gate. It is live in whatever consumes this branch.",
        "",
        f"- **Run:** `{run.id}`",
        f"- **Score:** {run.score if run.score is not None else 'n/a'}/100",
        f"- **Trigger:** {run.trigger}",
    ]
    if run.commit_message:
        lines.append(f"- **Commit message:** {run.commit_message}")
    lines += ["", "### Failing stages", ""]
    if stages:
        lines += ["| Stage | Why |", "| --- | --- |"]
        for stage in stages:
            lines.append(f"| {stage['name']} | {stage['summary'].replace('|', chr(92) + '|')} |")
    else:
        lines.append("_No individual stage failed; the verdict was sealed by policy._")

    if report and report.get("reasons"):
        lines += ["", "### Blocking reasons", ""]
        lines += [f"- {r}" for r in report["reasons"]]

    critical = [f for f in (report or {}).get("findings", []) if f.get("severity") == "critical"]
    if critical:
        lines += ["", "### Critical findings", ""]
        for finding in critical[:10]:
            lines.append(f"- **{finding.get('title')}** — {(finding.get('detail') or '')[:200]}")
            if finding.get("remediation"):
                lines.append(f"  - Fix: `{finding['remediation']}`")

    lines += ["", "### Recovery", "", plan.get("summary", "")]
    if plan.get("last_good"):
        good = plan["last_good"]
        lines.append(
            f"\nLast known-good commit: **`{good['short_sha']}`** "
            f"(score {good['score']}, passed {good['at']})."
        )
    if plan.get("commands"):
        lines += ["", "```bash", *plan["commands"], "```"]

    lines += [
        "",
        "---",
        "",
        "**To stop this recurring:** protect this branch and mark "
        "`ChaosGate / release-gate` as a required status check, so changes like this "
        "are blocked at the pull request instead of being found afterwards.",
        "",
        "<sub>Filed automatically by ChaosGate.</sub>",
    ]
    return "\n".join(lines)


def open_incident(token: str, repo: Repository, run: PipelineRun, plan: dict[str, Any], report: dict[str, Any] | None) -> dict[str, Any]:
    """File a GitHub issue for a failing default-branch run (deduplicated)."""
    if not token:
        return {"created": False, "reason": "no GitHub token"}

    title = f"ChaosGate: {run.branch} is failing at {plan['bad_commit_short']}"
    try:
        existing = find_open_incident(token, repo.full_name, plan["bad_commit_short"])
        if existing:
            return {"created": False, "existed": True, **existing}

        body = incident_body(repo, run, plan, report)
        res = github_client._request(
            "POST", f"/repos/{repo.full_name}/issues", token,
            operation="create_issue",
            json={"title": title, "body": body, "labels": [INCIDENT_LABEL]},
        )
        if res.status_code >= 400:
            # Labels fail on repos where the label does not exist; retry bare.
            res = github_client._request(
                "POST", f"/repos/{repo.full_name}/issues", token,
                operation="create_issue", json={"title": title, "body": body},
            )
        if res.status_code >= 400:
            return {"created": False, "reason": f"GitHub returned {res.status_code}"}
        issue = res.json()
        return {
            "created": True,
            "number": issue.get("number"),
            "url": issue.get("html_url"),
            "title": title,
        }
    except GitHubError as exc:
        return {"created": False, "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"created": False, "reason": f"{type(exc).__name__}: {exc}"}


def find_open_incident(token: str, full_name: str, short_sha: str) -> dict[str, Any] | None:
    try:
        res = github_client._request(
            "GET", f"/repos/{full_name}/issues", token, operation="list_issues",
            params={"state": "open", "labels": INCIDENT_LABEL, "per_page": 50},
        )
        if res.status_code >= 400:
            return None
        for issue in res.json() or []:
            if short_sha in (issue.get("title") or ""):
                return {"number": issue.get("number"), "url": issue.get("html_url")}
    except Exception:  # noqa: BLE001
        return None
    return None


# ------------------------------------------------------------------ revert
def execute_revert(repo_id: str, full_name: str, token: str, bad_sha: str, base_branch: str) -> dict[str, Any]:
    """Create a revert branch and open a PR. Never force-pushes, never touches main."""
    from core import workspace

    if not token:
        return {"ok": False, "reason": "a GitHub token is required to push a revert"}

    root = workspace.workspace_path(repo_id)
    if not (root / ".git").is_dir():
        try:
            workspace.clone(repo_id, full_name, base_branch, token)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "reason": f"could not clone the repository: {exc}"}

    short = bad_sha[:7]
    branch = f"chaosgate/revert-{short}"
    url = workspace.remote_url(full_name, token)

    def git(*args: str, timeout: int = 120) -> tuple[bool, str]:
        proc = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True, timeout=timeout,
            env={**_git_env(), "GIT_TERMINAL_PROMPT": "0"},
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode == 0, out.replace(token, "***") if token else out

    ok, out = git("fetch", url, base_branch, timeout=180)
    if not ok:
        return {"ok": False, "reason": f"fetch failed: {out[-300:]}"}

    git("checkout", "-B", branch, "FETCH_HEAD")

    ok, out = git("revert", "--no-edit", "--no-commit", bad_sha)
    if not ok:
        git("revert", "--abort")
        return {
            "ok": False,
            "reason": f"the revert does not apply cleanly: {out[-300:]}",
            "hint": "Later commits touch the same lines. This needs a manual fix-forward.",
        }

    ok, out = git(
        "-c", "user.name=ChaosGate", "-c", "user.email=gate@chaosgate.local",
        "commit", "-m",
        f"Revert \"{short}\"\n\nReverted by ChaosGate: this commit failed the release gate "
        f"on {base_branch}.",
    )
    if not ok and "nothing to commit" in out.lower():
        return {"ok": False, "reason": "the revert produced no changes"}

    ok, out = git("push", url, f"HEAD:refs/heads/{branch}", timeout=300)
    if not ok:
        return {"ok": False, "reason": f"push failed: {out[-300:]}"}

    try:
        pull = github_client.create_pull_request(
            token, full_name, branch, base_branch,
            f"Revert {short} — failed the ChaosGate release gate",
            f"Automated revert of `{bad_sha}`.\n\n"
            f"That commit is on `{base_branch}` and fails the release gate. This PR restores "
            f"the previous state.\n\n"
            f"Review before merging — if later commits depend on this change, fix forward "
            f"instead.\n\n<sub>Opened by ChaosGate.</sub>",
        )
    except GitHubError as exc:
        return {"ok": True, "branch": branch, "pull_request": None, "pr_error": str(exc)}

    return {"ok": True, "branch": branch, "pull_request": pull, "reverted": bad_sha}


def _git_env() -> dict[str, str]:
    import os

    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "ChaosGate",
        "GIT_AUTHOR_EMAIL": "gate@chaosgate.local",
        "GIT_COMMITTER_NAME": "ChaosGate",
        "GIT_COMMITTER_EMAIL": "gate@chaosgate.local",
        "LC_ALL": "C",
    })
    return env
