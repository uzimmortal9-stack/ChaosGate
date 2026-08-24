"""The gate engine.

Thirteen stages, executed in order against a real checkout of the target
repository. Every stage reports one of:

  passed | failed | skipped | degraded

``degraded`` is the honest outcome when a stage's tool is not installed on
this host (no Docker daemon, no cluster, no k6). The work that *can* be done
statically still runs, and the report says exactly what was not executed.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from core import (
    docker_runner,
    grafana,
    k6_runner,
    k8s_runner,
    metrics,
    prometheus,
    supply_chain,
    workspace,
)
from core.config_parser import parse_config, summarize_config
from core.db import SessionLocal
from core.detector import detect_app
from core.ids import nid
from core.models import PipelineRun, Repository, RunEvent, Stage, utcnow
from core.scanners import scan_dependencies, scan_secrets
from core.settings import (
    ARTIFACTS_DIR,
    DEFAULT_POLICY,
    K8S_NAMESPACE,
    PUBLIC_URL,
)
from core.toolchain import get as tool_get
from core.toolchain import probe as tool_probe
from core.verdict import decide

STAGE_SPEC = [
    ("validate", "Repo validation"),
    ("detect", "Stack detect"),
    ("unit", "Unit tests"),
    ("build", "Build"),
    ("security", "Security scan"),
    ("docker", "Container image"),
    ("k8s", "Kubernetes"),
    ("smoke", "Smoke test"),
    ("load", "Load test (k6)"),
    ("prometheus", "Prometheus"),
    ("chaos", "Chaos / resilience"),
    ("grafana", "Grafana dashboard"),
    ("verdict", "Verdict"),
]

_ACTIVE: dict[str, bool] = {}
_ACTIVE_LOCK = threading.Lock()


# --------------------------------------------------------------------- run mgmt
def create_run(
    session,
    repo: Repository,
    trigger: str = "manual",
    engine: str = "local",
    branch: str | None = None,
    commit_sha: str | None = None,
    commit_message: str | None = None,
    pr_number: int | None = None,
) -> PipelineRun:
    run = PipelineRun(
        id=nid("run"),
        repo_id=repo.id,
        status="queued",
        trigger=trigger,
        engine=engine,
        branch=branch or repo.default_branch or "main",
        commit_sha=commit_sha,
        commit_message=commit_message,
        pr_number=pr_number,
    )
    session.add(run)
    session.flush()
    for index, (key, name) in enumerate(STAGE_SPEC):
        session.add(Stage(run_id=run.id, key=key, name=name, index=index, status="pending", logs=""))
    repo.last_status = "queued"
    repo.last_run_id = run.id
    session.commit()
    session.refresh(run)
    return run


def start_run_async(run_id: str, token: str | None = None) -> None:
    thread = threading.Thread(target=_execute_run, args=(run_id, token), daemon=True, name=f"gate-{run_id}")
    thread.start()


def active_count() -> int:
    with _ACTIVE_LOCK:
        return len(_ACTIVE)


def _execute_run(run_id: str, token: str | None) -> None:
    session = SessionLocal()
    cleanup: Path | None = None
    runtime: dict[str, Any] = {}
    started_wall = time.time()

    with _ACTIVE_LOCK:
        _ACTIVE[run_id] = True
    metrics.pipeline_runs_active.set(active_count())

    try:
        run = session.get(PipelineRun, run_id)
        if not run:
            return
        repo = session.get(Repository, run.repo_id)
        if not repo:
            _fail_run(session, run, "Repository record disappeared")
            return

        repo_label = repo.full_name
        run.status = "running"
        run.started_at = utcnow()
        repo.last_status = "running"
        session.commit()
        _emit(session, run.id, "run", {"status": "running"})

        caps = tool_probe(force=True)
        metrics.record_toolchain(caps)

        policy = dict(DEFAULT_POLICY)
        if repo.workspace and repo.workspace.policy_json:
            try:
                policy.update(json.loads(repo.workspace.policy_json))
            except json.JSONDecodeError:
                pass

        artifacts = ARTIFACTS_DIR / run.id
        artifacts.mkdir(parents=True, exist_ok=True)

        root, cleanup, sha = _materialize(session, run, repo, token)
        if sha and not run.commit_sha:
            run.commit_sha = sha
        session.commit()

        findings: list[dict[str, Any]] = []
        cfg, cfg_errors = parse_config(root)

        _stage_validate(session, run, root, cfg, cfg_errors, policy)
        detected = _stage_detect(session, run, root, cfg, caps)
        _stage_unit(session, run, root, detected, cfg)
        _stage_build(session, run, root, detected, cfg)
        findings.extend(_stage_security(session, run, root, cfg, repo_label))
        image = _stage_docker(session, run, root, detected, cfg, repo, findings, artifacts)
        _stage_k8s(session, run, root, detected, repo, image, findings, artifacts)

        runtime = _stage_smoke(session, run, root, detected, cfg, image)
        try:
            _stage_load(session, run, runtime, cfg, policy, repo_label, artifacts)
            _stage_prometheus(session, run, runtime, repo_label, artifacts)
            _stage_chaos(session, run, runtime, cfg, repo_label)
            _stage_grafana(session, run, repo_label, artifacts)
            report = _stage_verdict(session, run, findings, policy, detected, cfg, caps, artifacts)
        finally:
            _teardown(runtime)

        conclusion = report["verdict"]
        duration = time.time() - started_wall
        run.status = "passed" if conclusion == "PASS" else "failed"
        run.conclusion = conclusion
        run.score = report.get("score")
        run.summary = report["summary"]
        run.report_json = json.dumps(report)
        run.duration_s = round(duration, 2)
        run.finished_at = utcnow()
        repo.last_status = run.status
        repo.last_run_at = run.finished_at
        repo.last_run_id = run.id
        session.commit()

        metrics.pipeline_runs_total.inc(repo=repo_label, trigger=run.trigger, verdict=conclusion)
        metrics.pipeline_duration_seconds.observe(duration, repo=repo_label)
        metrics.gate_score.set(report.get("score") or 0, repo=repo_label)
        if conclusion == "FAIL":
            reason = (report.get("reasons") or ["unknown"])[0][:60]
            metrics.gate_blocked_total.inc(repo=repo_label, reason=reason)

        _publish_commit_status(session, run, repo, report, token)
        _handle_post_merge_failure(session, run, repo, report, token)

        _emit(session, run.id, "done", {"status": run.status, "conclusion": conclusion, "report": report})

    except Exception as exc:  # noqa: BLE001 — the gate must always close
        try:
            run = session.get(PipelineRun, run_id)
            if run:
                _fail_run(session, run, f"Engine error: {type(exc).__name__}: {exc}")
        except Exception:
            pass
    finally:
        _teardown(runtime)
        if cleanup and cleanup.exists():
            shutil.rmtree(cleanup, ignore_errors=True)
        with _ACTIVE_LOCK:
            _ACTIVE.pop(run_id, None)
        metrics.pipeline_runs_active.set(active_count())
        session.close()


def _teardown(runtime: dict[str, Any]) -> None:
    if not runtime:
        return
    stop = runtime.get("stop")
    if callable(stop):
        try:
            stop()
        except Exception:  # noqa: BLE001
            pass
    runtime["stop"] = None


def _rebind(state: dict[str, Any], nxt: dict[str, Any]) -> None:
    """Adopt a freshly started target into the *original* runtime dict.

    The restart closure must keep pointing at the dict the pipeline holds a
    reference to, otherwise a second chaos experiment polls the port of the
    previous incarnation and reports a false failure.
    """
    own_restart = state.get("restart")
    state.update(nxt)
    if own_restart is not None:
        state["restart"] = own_restart


def _fail_run(session, run: PipelineRun, message: str) -> None:
    run.status = "error"
    run.conclusion = "FAIL"
    run.summary = message
    run.finished_at = utcnow()
    if run.repo:
        run.repo.last_status = "error"
        run.repo.last_run_at = run.finished_at
    session.commit()
    for stage in run.stages:
        if stage.status in ("pending", "running"):
            stage.status = "skipped"
            stage.summary = "Not reached — the run aborted"
    session.commit()
    _emit(session, run.id, "done", {"status": "error", "conclusion": "FAIL", "summary": message})


def _publish_commit_status(session, run, repo, report, token) -> None:
    """Post the merge-blocking commit status back to GitHub."""
    if not token or not run.commit_sha or repo.is_sample or not repo.html_url:
        return
    try:
        from core import github_client

        target = f"{PUBLIC_URL}/console/runs/{run.id}" if PUBLIC_URL else None
        github_client.create_commit_status(
            token,
            repo.full_name,
            run.commit_sha,
            report.get("github_state", "failure"),
            report.get("summary", "")[:139],
            context="ChaosGate / release-gate",
            target_url=target,
        )
        _log(session, run, "verdict", f"Commit status '{report.get('github_state')}' posted to GitHub")
        if run.pr_number:
            body = _pr_comment(run, report)
            github_client.comment_on_pr(token, repo.full_name, run.pr_number, body)
            _log(session, run, "verdict", f"Commented on PR #{run.pr_number}")
    except Exception as exc:  # noqa: BLE001
        _log(session, run, "verdict", f"Could not publish commit status: {exc}")


def _handle_post_merge_failure(session, run, repo, report, token) -> None:
    """Bad code already on the default branch is an incident, not a review comment.

    The pre-merge gate cannot help here — the change is already merged. So the
    gate switches roles: work out the last known-good commit, file an issue
    naming the failing stage and the fix, and offer a revert.
    """
    if report.get("verdict") != "FAIL":
        return
    # A PR run is handled by the commit status; this is only for the branch itself.
    if run.pr_number or run.branch != (repo.default_branch or "main"):
        return

    from core import recovery

    plan = recovery.build_revert_plan(session, repo, run)
    run.recovery_json = json.dumps(plan, default=str)
    session.commit()

    _log(session, run, "verdict", "")
    _log(session, run, "verdict",
         f"POST-MERGE FAILURE — {run.branch} is broken at {plan['bad_commit_short'] or 'unknown'}")
    _log(session, run, "verdict", f"strategy: {plan['strategy']} — {plan.get('summary', '')}")
    if plan.get("last_good"):
        good = plan["last_good"]
        _log(session, run, "verdict",
             f"last known-good: {good['short_sha']} (score {good['score']})")
    else:
        _log(session, run, "verdict", "no earlier passing run recorded — fix forward")

    if repo.is_sample or not token:
        _log(session, run, "verdict",
             "Incident not filed (sample target or no GitHub token).")
        return

    incident = recovery.open_incident(token, repo, run, plan, report)
    if incident.get("created"):
        run.incident_url = incident.get("url")
        run.incident_number = incident.get("number")
        session.commit()
        _log(session, run, "verdict", f"Incident filed: {incident['url']}")
    elif incident.get("existed"):
        run.incident_url = incident.get("url")
        session.commit()
        _log(session, run, "verdict", f"Incident already open: {incident.get('url')}")
    else:
        _log(session, run, "verdict",
             f"Could not file an incident: {incident.get('reason')}")


def _pr_comment(run, report) -> str:
    icon = "✅" if report["verdict"] == "PASS" else "🚫"
    lines = [
        f"## {icon} ChaosGate — **{report['verdict']}** (score {report.get('score')}/100)",
        "",
        f"> {report.get('summary', '')}",
        "",
        "| Stage | Result | Detail |",
        "| --- | --- | --- |",
    ]
    marks = {"passed": "✅ pass", "failed": "❌ fail", "skipped": "⏭ skip", "degraded": "⚠️ degraded"}
    for stage in report.get("stages", []):
        detail = (stage.get("summary") or "").replace("|", "\\|")[:110]
        lines.append(f"| {stage['name']} | {marks.get(stage['status'], stage['status'])} | {detail} |")
    if report.get("reasons"):
        lines += ["", "### Blocking reasons", *[f"- {r}" for r in report["reasons"]]]
    if report.get("degraded"):
        lines += ["", "<details><summary>Degraded stages</summary>", ""]
        lines += [f"- {d}" for d in report["degraded"]]
        lines += ["", "</details>"]
    return "\n".join(lines)


# ---------------------------------------------------------------- materialize
def _materialize(session, run, repo, token) -> tuple[Path, Path | None, str | None]:
    """Get a real directory to test: the local workspace, a sample, or a clone."""
    ws_path = workspace.workspace_path(repo.id)
    if (ws_path / ".git").is_dir():
        sha = workspace.head_sha(repo.id, short=False)
        branch = workspace.current_branch(repo.id)
        _log(session, run, "validate", f"Using the local workspace at {ws_path} ({branch} @ {(sha or '')[:7]})")
        return ws_path, None, sha

    if repo.local_path and Path(repo.local_path).is_dir():
        _log(session, run, "validate", f"Using the bundled sample target at {repo.local_path}")
        return Path(repo.local_path), None, _git_sha(Path(repo.local_path))

    if not repo.full_name:
        raise RuntimeError("No local path or GitHub repository to materialize")

    url = workspace.remote_url(repo.full_name, token)
    dest = Path(tempfile.mkdtemp(prefix="cg_repo_"))
    _log(session, run, "validate", f"Cloning {repo.full_name}@{run.branch} …")
    cmd = ["git", "clone", "--depth", "1", "--branch", run.branch, url, str(dest)]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"git clone failed: {exc}") from exc
    if proc.returncode != 0:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True, text=True, timeout=180, env=env,
        )
        if proc.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            message = (proc.stderr or proc.stdout or "clone failed")
            if token:
                message = message.replace(token, "***")
            raise RuntimeError(message[-400:])
    sha = _git_sha(dest)
    _log(session, run, "validate", f"Clone complete ({sha or 'unknown sha'})")
    return dest, dest, sha


def _git_sha(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ stage io
def _stage(session, run: PipelineRun, key: str) -> Stage:
    return next(s for s in run.stages if s.key == key)


def _begin(session, run: PipelineRun, key: str) -> Stage:
    stage = _stage(session, run, key)
    stage.status = "running"
    stage.started_at = utcnow()
    session.commit()
    _emit(session, run.id, "stage", {"key": key, "status": "running"})
    _log(session, run, key, f"── {stage.name} ──")
    return stage


def _end(session, run, stage: Stage, status: str, summary: str, metrics_payload: dict | None = None, degraded: bool = False) -> None:
    stage.status = status
    stage.summary = summary
    stage.degraded = degraded or status == "degraded"
    stage.finished_at = utcnow()
    if metrics_payload:
        stage.metrics_json = json.dumps(metrics_payload, default=str)
    session.commit()

    if stage.started_at and stage.finished_at:
        elapsed = (stage.finished_at - stage.started_at).total_seconds()
        metrics.stage_duration_seconds.observe(elapsed, stage=stage.key, status=status)
    metrics.stage_results_total.inc(stage=stage.key, status=status)

    _emit(session, run.id, "stage", {
        "key": stage.key, "status": status, "summary": summary,
        "degraded": stage.degraded, "metrics": metrics_payload or {},
    })


def _log(session, run: PipelineRun, key: str, line: str) -> None:
    stage = _stage(session, run, key)
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    formatted = f"[{stamp}] {line}"
    stage.logs = (stage.logs or "") + formatted + "\n"
    session.commit()
    _emit(session, run.id, "log", {"key": key, "line": formatted})


def _logger(session, run, key) -> Callable[[str], None]:
    return lambda line: _log(session, run, key, line)


def _emit(session, run_id: str, kind: str, payload: dict[str, Any]) -> None:
    session.add(RunEvent(run_id=run_id, kind=kind, payload_json=json.dumps(payload, default=str)))
    session.commit()


# ------------------------------------------------------------------- stage 1
def _stage_validate(session, run, root: Path, cfg, errors, policy) -> None:
    stage = _begin(session, run, "validate")
    _log(session, run, "validate", f"Inspecting {root}")
    markers = [
        "chaosgate.yml", "chaosgate.yaml", "Dockerfile", "docker-compose.yml",
        "compose.yml", "package.json", "requirements.txt", "pyproject.toml",
        "go.mod", "Cargo.toml", "pom.xml", "app.py", "main.py", "index.js", "server.js",
    ]
    found = [name for name in markers if (root / name).exists()]
    for name in found:
        _log(session, run, "validate", f"found {name}")

    if errors:
        for err in errors:
            _log(session, run, "validate", f"CONFIG ERROR: {err}")
        _end(session, run, stage, "failed", errors[0])
        return
    if cfg:
        _log(session, run, "validate", "chaosgate.yml parsed and valid")
        _end(session, run, stage, "passed", "Contract file present and valid", summarize_config(cfg))
        return

    _log(session, run, "validate", "No chaosgate.yml — falling back to autodetect")
    if policy.get("require_config"):
        _end(session, run, stage, "failed", "chaosgate.yml is required by gate policy")
        return
    if not found:
        _end(session, run, stage, "failed", "No recognizable application files")
        return
    _end(session, run, stage, "passed", "Validated via autodetect", {"files": found})


# ------------------------------------------------------------------- stage 2
def _stage_detect(session, run, root: Path, cfg, caps) -> dict[str, Any]:
    stage = _begin(session, run, "detect")
    detected = detect_app(root, cfg)
    _log(session, run, "detect", f"type={detected['type']} language={detected['language']}")
    if detected["frameworks"]:
        _log(session, run, "detect", "frameworks: " + ", ".join(detected["frameworks"]))
    for hint in detected.get("hints") or []:
        _log(session, run, "detect", hint)
    if detected.get("test_command"):
        _log(session, run, "detect", f"unit → {detected['test_command']}")
    if detected.get("build_command"):
        _log(session, run, "detect", f"build → {detected['build_command']}")

    _log(session, run, "detect", "── host capabilities ──")
    for name, tool in (caps.get("tools") or {}).items():
        mark = "✓" if tool.get("available") else "·"
        _log(session, run, "detect", f"{mark} {name}: {tool.get('detail')}")

    payload = {k: detected[k] for k in ("type", "language", "frameworks", "test_command", "build_command")}
    payload["capabilities"] = caps.get("summary", {})
    _end(session, run, stage, "passed", f"Detected {detected['type']}", payload)
    return detected


# ------------------------------------------------------------------- stage 3
def _stage_unit(session, run, root: Path, detected, cfg) -> None:
    stage = _begin(session, run, "unit")
    cmd = detected.get("test_command")
    tests_cfg = (cfg or {}).get("tests") or {}
    if isinstance(tests_cfg.get("unit"), dict):
        cmd = tests_cfg["unit"].get("command") or cmd
    elif isinstance(tests_cfg.get("unit"), str):
        cmd = tests_cfg["unit"]

    if not cmd:
        _log(session, run, "unit", "No unit test command detected — skipping")
        _end(session, run, stage, "skipped", "No unit tests configured")
        return

    _log(session, run, "unit", f"$ {cmd}")
    code, out = _run_cmd(cmd, root, timeout=240)
    lines = out.splitlines()
    for line in lines[-100:]:
        _log(session, run, "unit", line)

    summary_line = next(
        (l for l in reversed(lines) if any(k in l for k in ("passed", "failed", "tests", "ok", "Tests:"))),
        "",
    )
    if code == 0:
        _end(session, run, stage, "passed", summary_line.strip()[:120] or "Unit tests passed")
    else:
        _end(session, run, stage, "failed", f"Unit tests failed (exit {code}) {summary_line.strip()[:80]}")


# ------------------------------------------------------------------- stage 4
def _stage_build(session, run, root: Path, detected, cfg) -> None:
    stage = _begin(session, run, "build")
    cmd = detected.get("build_command")
    tests_cfg = (cfg or {}).get("tests") or {}
    if isinstance(tests_cfg.get("build"), dict):
        cmd = tests_cfg["build"].get("command") or cmd
    elif isinstance(tests_cfg.get("build"), str):
        cmd = tests_cfg["build"]

    if cmd:
        _log(session, run, "build", f"$ {cmd}")
        code, out = _run_cmd(cmd, root, timeout=300)
        for line in out.splitlines()[-70:]:
            _log(session, run, "build", line)
        if code == 0:
            _end(session, run, stage, "passed", "Build succeeded")
        else:
            _end(session, run, stage, "failed", f"Build failed (exit {code})")
        return

    if detected.get("language") == "python":
        _log(session, run, "build", "Python sources — byte-compiling")
        code, out = _run_cmd("python -m compileall -q .", root, timeout=90)
        for line in out.splitlines()[-40:]:
            _log(session, run, "build", line)
        if code == 0:
            _end(session, run, stage, "passed", "Python sources compiled")
        else:
            _end(session, run, stage, "failed", "Python compile failed")
        return

    _log(session, run, "build", "No build step required for this stack")
    _end(session, run, stage, "skipped", "No build command")


# ------------------------------------------------------------------- stage 5
def _stage_security(session, run, root: Path, cfg, repo_label: str) -> list[dict[str, Any]]:
    stage = _begin(session, run, "security")
    sec = (cfg or {}).get("security") or {}
    findings: list[dict[str, Any]] = []

    if sec.get("secret_scan", True):
        secrets = scan_secrets(root)
        findings.extend(secrets)
        _log(session, run, "security", f"Secret scan: {len(secrets)} finding(s)")
        for item in secrets[:25]:
            _log(session, run, "security", f"CRIT  {item['file']}:{item.get('line', '?')}  {item['title']}")

    # Committed credential files — the case that matters when secrets live in
    # .env rather than in source. A committed .env IS the breach.
    if sec.get("env_scan", True):
        env_findings = supply_chain.scan_committed_env(root)
        env_findings.extend(supply_chain.check_gitignore(root))
        findings.extend(env_findings)
        _log(session, run, "security", f"Credential-file scan: {len(env_findings)} finding(s)")
        for item in env_findings:
            level = "CRIT" if item["severity"] == "critical" else "WARN"
            _log(session, run, "security", f"{level}  {item['title']}")
            if item.get("remediation"):
                _log(session, run, "security", f"      fix: {item['remediation']}")

    # Secrets that were deleted from HEAD but survive in git history.
    history_result: dict[str, Any] = {}
    if sec.get("history_scan", True):
        history_result = supply_chain.scan_git_history(root)
        if history_result.get("scanned"):
            hist = history_result["findings"]
            findings.extend(hist)
            _log(
                session, run, "security",
                f"Git history scan: {len(hist)} finding(s) across "
                f"{history_result.get('commits_scanned', 0)} commit(s)",
            )
            for item in hist[:15]:
                _log(session, run, "security",
                     f"CRIT  {item['title']} @ {item.get('commit')} in {item.get('file')}")
        else:
            _log(session, run, "security",
                 f"Git history scan skipped: {history_result.get('reason')}")

    if sec.get("dependency_scan", True):
        deps = scan_dependencies(root)
        findings.extend(deps)
        _log(session, run, "security", f"Dependency hygiene: {len(deps)} finding(s)")
        for item in deps[:25]:
            _log(session, run, "security", f"WARN  {item['title']} — {item['detail'][:120]}")

    # Known CVEs in pinned dependency versions (OSV.dev).
    cve_result: dict[str, Any] = {}
    cve_degraded = False
    if sec.get("cve_scan", True):
        _log(session, run, "security", "Querying OSV.dev for known vulnerabilities…")
        cve_result = supply_chain.scan_dependencies_cve(root)
        if cve_result.get("available"):
            cve_findings = cve_result["findings"]
            findings.extend(cve_findings)
            _log(
                session, run, "security",
                f"CVE scan: {cve_result.get('vulnerable', 0)} of "
                f"{cve_result.get('queried', 0)} package(s) vulnerable",
            )
            for item in cve_findings[:20]:
                level = "CRIT" if item["severity"] == "critical" else "WARN"
                _log(session, run, "security", f"{level}  {item['title']}")
                _log(session, run, "security", f"      {item['remediation']}")
        else:
            cve_degraded = True
            _log(session, run, "security",
                 f"CVE scan unavailable: {cve_result.get('reason')}")
            _log(session, run, "security",
                 "Dependencies were NOT checked against any advisory database.")

    for finding in findings:
        metrics.security_findings_total.inc(
            repo=repo_label, severity=finding.get("severity", "info")
        )

    critical = [f for f in findings if f.get("severity") == "critical"]
    payload = {
        "findings": findings,
        "critical": len(critical),
        "warnings": len(findings) - len(critical),
        "history": {k: v for k, v in history_result.items() if k != "findings"},
        "cve": {k: v for k, v in (cve_result or {}).items() if k != "findings"},
        "degraded": cve_degraded,
    }

    if critical:
        _end(session, run, stage, "failed",
             f"{len(critical)} critical security finding(s)", payload)
    elif cve_degraded:
        # No CVE data means we cannot claim the dependencies are clean.
        _end(session, run, stage, "degraded",
             f"{len(findings)} finding(s) · CVE database unreachable",
             payload, degraded=True)
    else:
        _end(
            session, run, stage, "passed",
            "No critical secrets; warnings recorded" if findings else "Clean security scan",
            payload,
        )
    return findings


# ------------------------------------------------------------------- stage 6
def _stage_docker(session, run, root: Path, detected, cfg, repo, findings, artifacts: Path) -> dict[str, Any]:
    """Build a real image when Docker is available; audit the Dockerfile always."""
    stage = _begin(session, run, "docker")
    log = _logger(session, run, "docker")
    repo_label = repo.full_name

    dockerfile = docker_runner.find_dockerfile(root)
    compose_file = docker_runner.find_compose(root)

    if not dockerfile and not compose_file:
        log("No Dockerfile or compose file in this repository")
        _end(session, run, stage, "skipped", "Repository is not containerized")
        return {}

    payload: dict[str, Any] = {}
    lint: list[dict[str, Any]] = []

    if dockerfile:
        log(f"Auditing {dockerfile.relative_to(root)}")
        lint = docker_runner.lint_dockerfile(dockerfile)
        for item in lint:
            level = {"critical": "CRIT", "warning": "WARN", "info": "INFO"}.get(item["severity"], "INFO")
            log(f"{level}  [{item['rule']}] {item['detail']}")
        if not lint:
            log("Dockerfile passes every best-practice rule")
        payload["lint"] = lint
        for item in lint:
            if item["severity"] in ("critical", "warning"):
                findings.append({
                    "severity": item["severity"],
                    "category": "container",
                    "title": f"Dockerfile: {item['rule']}",
                    "detail": item["detail"],
                    "file": dockerfile.name,
                })

    if compose_file:
        log(f"Validating {compose_file.name}")
        compose = docker_runner.compose_config(compose_file, log)
        payload["compose"] = compose
        if not compose.get("valid"):
            for issue in compose.get("issues") or [compose.get("error", "invalid compose file")]:
                log(f"CRIT  {issue}")

    docker_tool = tool_get("docker")
    critical_lint = [i for i in lint if i["severity"] == "critical"]

    if not docker_tool.get("available"):
        log(f"Docker is unavailable: {docker_tool.get('detail')}")
        log("Image build skipped. Static audit above is the whole result for this stage.")
        payload["degraded"] = True
        payload["reason"] = docker_tool.get("detail")
        if critical_lint:
            _end(session, run, stage, "failed",
                 f"{len(critical_lint)} critical Dockerfile issue(s): {critical_lint[0]['rule']}", payload)
        else:
            counts = f"{len(lint)} advisory finding(s)" if lint else "clean"
            _end(session, run, stage, "degraded",
                 f"No Docker daemon — audited only ({counts})", payload, degraded=True)
        return {}

    if critical_lint:
        log("Refusing to build an image with critical Dockerfile issues")
        _end(session, run, stage, "failed",
             f"Critical Dockerfile issue: {critical_lint[0]['rule']}", payload)
        return {}

    if not dockerfile:
        log("Compose-only repository — no single image to build here")
        _end(session, run, stage, "passed", "Compose configuration validated", payload)
        return {}

    tag = f"chaosgate/{repo.name.lower()}:{(run.commit_sha or run.id)[:12]}"
    build = docker_runner.build_image(root, tag, dockerfile, log)
    payload["build"] = build

    metrics.docker_builds_total.inc(repo=repo_label, result="ok" if build["built"] else "error")
    if build.get("duration_s"):
        metrics.docker_build_duration_seconds.observe(build["duration_s"], repo=repo_label)

    if not build["built"]:
        _end(session, run, stage, "failed", f"docker build failed (exit {build['exit_code']})", payload)
        return {}

    if build.get("size_bytes"):
        metrics.docker_image_size_bytes.set(build["size_bytes"], repo=repo_label)
    if build.get("user") in ("", "root", "0"):
        findings.append({
            "severity": "warning", "category": "container",
            "title": "Image runs as root",
            "detail": f"{tag} has no non-root USER — a container escape becomes host root.",
        })

    try:
        (artifacts / "docker-build.json").write_text(json.dumps(build, indent=2), encoding="utf-8")
    except OSError:
        pass

    summary = f"Built {tag}"
    if build.get("size_mb"):
        summary += f" · {build['size_mb']} MB · {build.get('layers', '?')} layers"
    _end(session, run, stage, "passed", summary, payload)
    return {"tag": tag, **build}


# ------------------------------------------------------------------- stage 7
def _stage_k8s(session, run, root: Path, detected, repo, image, findings, artifacts: Path) -> None:
    stage = _begin(session, run, "k8s")
    log = _logger(session, run, "k8s")

    manifests = k8s_runner.discover_manifests(root)
    payload: dict[str, Any] = {"manifest_files": [str(p.relative_to(root)) for p in manifests]}
    generated = False

    if not manifests:
        log("No Kubernetes manifests found in this repository")
        tag = (image or {}).get("tag") or f"chaosgate/{repo.name.lower()}:latest"
        rendered = k8s_runner.generate_manifests(repo.name, tag, namespace=K8S_NAMESPACE)
        target = artifacts / "k8s-generated.yaml"
        try:
            target.write_text(rendered, encoding="utf-8")
            log(f"Generated a hardened baseline manifest set → {target.name}")
            log("  Namespace, Deployment (probes + limits + non-root), Service, HPA, PodDisruptionBudget")
        except OSError as exc:
            log(f"could not write generated manifests: {exc}")
        manifests = [target] if target.is_file() else []
        generated = True
        payload["generated"] = True

    if not manifests:
        _end(session, run, stage, "skipped", "No manifests to validate")
        return

    docs, parse_errors = k8s_runner.load_documents(manifests)
    payload["documents"] = len(docs)
    payload["kinds"] = sorted({d.get("kind") for d in docs if d.get("kind")})
    log(f"Parsed {len(docs)} manifest document(s): {', '.join(payload['kinds']) or 'none'}")

    for err in parse_errors:
        log(f"CRIT  {err}")
    if parse_errors:
        payload["parse_errors"] = parse_errors
        _end(session, run, stage, "failed", f"{len(parse_errors)} manifest(s) failed to parse", payload)
        return

    audit = k8s_runner.audit(docs)
    payload["audit"] = audit
    if audit:
        log(f"Manifest audit: {len(audit)} finding(s)")
        for item in audit[:30]:
            level = {"critical": "CRIT", "warning": "WARN", "info": "INFO"}.get(item["severity"], "INFO")
            log(f"{level}  [{item['rule']}] {item['detail']}")
    else:
        log("Manifest audit clean — probes, limits and security context all present")

    if not generated:
        for item in audit:
            if item["severity"] in ("critical", "warning"):
                findings.append({
                    "severity": item["severity"], "category": "k8s",
                    "title": f"Kubernetes: {item['rule']}",
                    "detail": item["detail"], "file": item.get("source"),
                })

    metrics.k8s_manifests_validated.set(len(docs), repo=repo.full_name)

    kubectl = tool_get("kubectl")
    critical = [i for i in audit if i["severity"] == "critical"]

    if not kubectl.get("available"):
        log(f"Kubernetes is unavailable: {kubectl.get('detail')}")
        log("Server-side validation skipped — the audit above is a static analysis.")
        payload["degraded"] = True
        payload["reason"] = kubectl.get("detail")
        if critical and not generated:
            _end(session, run, stage, "failed",
                 f"{len(critical)} critical manifest issue(s): {critical[0]['rule']}", payload)
        else:
            noun = "generated" if generated else f"{len(docs)} document(s)"
            _end(session, run, stage, "degraded",
                 f"No cluster reachable — audited {noun} statically", payload, degraded=True)
        return

    log(f"Cluster: {kubectl.get('extra', {}).get('context') or 'current context'}")
    dry = k8s_runner.dry_run(manifests, K8S_NAMESPACE, log, server_side=True)
    payload["dry_run"] = dry

    if not dry["ok"]:
        metrics.k8s_deploy_total.inc(repo=repo.full_name, result="rejected")
        _end(session, run, stage, "failed", "The API server rejected one or more manifests", payload)
        return

    if k8s_runner.should_apply() and not generated:
        log(f"K8S_APPLY=1 — applying to namespace {K8S_NAMESPACE}")
        applied = k8s_runner.apply(manifests, K8S_NAMESPACE, log)
        payload["applied"] = applied
        if applied["ok"]:
            rollout = k8s_runner.rollout_status(applied["applied"], K8S_NAMESPACE, log)
            payload["rollout"] = rollout
            payload["cluster"] = k8s_runner.cluster_snapshot(K8S_NAMESPACE)
            metrics.k8s_deploy_total.inc(
                repo=repo.full_name, result="ok" if rollout["ok"] else "rollout-failed"
            )
            if not rollout["ok"]:
                _end(session, run, stage, "failed", "Rollout did not become ready", payload)
                return
            _end(session, run, stage, "passed",
                 f"Applied and rolled out {len(applied['applied'])} resource(s)", payload)
            return
        metrics.k8s_deploy_total.inc(repo=repo.full_name, result="apply-failed")
        _end(session, run, stage, "failed", "kubectl apply failed", payload)
        return

    metrics.k8s_deploy_total.inc(repo=repo.full_name, result="validated")
    suffix = " (generated baseline)" if generated else ""
    _end(session, run, stage, "passed",
         f"{len(docs)} manifest(s) accepted by the API server{suffix}", payload)


# ------------------------------------------------------------------- stage 8
def _stage_smoke(session, run, root: Path, detected, cfg, image) -> dict[str, Any]:
    stage = _begin(session, run, "smoke")
    log = _logger(session, run, "smoke")

    target = _start_target(root, detected, cfg, image, log)
    if not target:
        log("No process could be booted for this stack on the control plane")
        _end(session, run, stage, "skipped", "No runnable local target")
        return {}

    url = target["health"]
    log(f"GET {url}")
    deadline = time.time() + 20
    last_error = None
    while time.time() < deadline:
        try:
            res = httpx.get(url, timeout=5.0)
            ms = res.elapsed.total_seconds() * 1000
            log(f"→ {res.status_code} in {ms:.0f}ms")
            if res.status_code >= 400:
                _teardown(target)
                _end(session, run, stage, "failed", f"Health check returned HTTP {res.status_code}")
                return {}
            body = (res.text or "")[:200].replace("\n", " ")
            if body:
                log(f"   body: {body}")
            _end(session, run, stage, "passed", f"Healthy {res.status_code} from {url}",
                 {"url": url, "status": res.status_code, "latency_ms": round(ms, 1),
                  "engine": target.get("kind")})
            return target
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.5)

    log(f"health check never succeeded: {last_error}")
    _teardown(target)
    _end(session, run, stage, "failed", "Target did not respond to the health check")
    return {}


# ------------------------------------------------------------------- stage 9
def _stage_load(session, run, runtime: dict[str, Any], cfg, policy, repo_label: str, artifacts: Path) -> None:
    stage = _begin(session, run, "load")
    log = _logger(session, run, "load")

    if not runtime.get("base"):
        log("No live target — the load stage needs a running application")
        _end(session, run, stage, "skipped", "Requires a running target")
        return

    load_cfg = (cfg or {}).get("load") or {}
    endpoints = load_cfg.get("endpoints") or [
        {"method": "GET", "path": runtime.get("health_path") or "/health"}
    ]
    vus = int(load_cfg.get("vus") or 10)
    duration = min(_parse_duration(load_cfg.get("duration") or "10s"), 30.0)
    thresholds = load_cfg.get("thresholds") or {}
    max_p95 = int(thresholds.get("p95_ms") or policy.get("max_p95_ms") or 800)
    max_err = float(thresholds.get("error_rate") or policy.get("max_error_rate") or 0.05)

    log(f"Profile: {vus} VUs × {duration:.0f}s · thresholds p95<{max_p95}ms err<{max_err:.1%}")
    for ep in endpoints:
        log(f"  {ep.get('method', 'GET')} {ep.get('path', '/')}")

    result = k6_runner.run_load(
        runtime["base"], endpoints, vus, duration, max_p95, max_err, log, artifacts
    )

    if not result.get("ok"):
        _end(session, run, stage, "failed", result.get("reason") or "Load generation failed",
             {"engine": result.get("engine")})
        return

    engine = result["engine"]
    metrics.load_p95_milliseconds.set(result["p95_ms"], repo=repo_label, engine=engine)
    metrics.load_error_rate.set(result["error_rate"], repo=repo_label, engine=engine)
    metrics.load_rps.set(result["rps"], repo=repo_label, engine=engine)
    metrics.load_requests_total.inc(result["samples"], repo=repo_label, engine=engine)
    for latency in (result.get("latencies") or [])[:2000]:
        metrics.load_request_duration_seconds.observe(latency / 1000.0, repo=repo_label)

    payload = {k: v for k, v in result.items() if k not in ("latencies", "script")}
    payload["threshold_p95_ms"] = max_p95
    payload["threshold_error_rate"] = max_err

    log(
        f"samples={result['samples']} rps={result['rps']} "
        f"p95={result['p95_ms']}ms avg={result['avg_ms']}ms err={result['error_rate']:.2%}"
    )

    # Evaluate each service-level objective explicitly, so the report shows
    # *which* objective failed rather than a bare "load test failed".
    availability = 1.0 - result["error_rate"]
    min_availability = float(thresholds.get("availability") or policy.get("min_availability") or 0.95)

    objectives = [
        {
            "name": "p95 latency",
            "measured": round(result["p95_ms"], 1),
            "threshold": max_p95,
            "unit": "ms",
            "comparator": "<=",
            "passed": result["p95_ms"] <= max_p95,
        },
        {
            "name": "error rate",
            "measured": round(result["error_rate"] * 100, 2),
            "threshold": round(max_err * 100, 2),
            "unit": "%",
            "comparator": "<=",
            "passed": result["error_rate"] <= max_err,
        },
        {
            "name": "availability",
            "measured": round(availability * 100, 2),
            "threshold": round(min_availability * 100, 2),
            "unit": "%",
            "comparator": ">=",
            "passed": availability >= min_availability,
        },
        {
            "name": "throughput",
            "measured": round(result["rps"], 1),
            "threshold": float(thresholds.get("min_rps") or 0),
            "unit": "req/s",
            "comparator": ">=",
            "passed": result["rps"] >= float(thresholds.get("min_rps") or 0),
        },
    ]
    payload["objectives"] = objectives
    payload["availability"] = round(availability, 5)

    log("── service level objectives ──")
    for obj in objectives:
        mark = "PASS" if obj["passed"] else "FAIL"
        log(f"  {mark}  {obj['name']:<14} {obj['measured']}{obj['unit']} "
            f"{obj['comparator']} {obj['threshold']}{obj['unit']}")

    reasons = [
        f"{o['name']} {o['measured']}{o['unit']} violates {o['comparator']} "
        f"{o['threshold']}{o['unit']}"
        for o in objectives if not o["passed"]
    ]
    if result.get("thresholds_breached"):
        reasons.append("k6 reported a threshold breach")

    if reasons:
        _end(session, run, stage, "failed", "; ".join(reasons), payload)
        return

    summary = f"p95 {result['p95_ms']:.0f}ms · {result['error_rate']:.1%} errors · {result['rps']:.0f} rps"
    if result.get("degraded"):
        log(f"note: {result.get('reason')}")
        _end(session, run, stage, "degraded", f"{summary} (built-in generator)", payload, degraded=True)
    else:
        _end(session, run, stage, "passed", f"{summary} (k6)", payload)


# ------------------------------------------------------------------ stage 10
def _stage_prometheus(session, run, runtime, repo_label: str, artifacts: Path) -> None:
    stage = _begin(session, run, "prometheus")
    log = _logger(session, run, "prometheus")
    payload: dict[str, Any] = {}

    log("Validating the ChaosGate exposition endpoint")
    exposition = metrics.render()
    summary = prometheus.summarize(exposition)
    payload["exposition"] = summary
    log(f"  {summary['families']} metric families · {summary['samples']} samples")
    for kind, count in sorted((summary.get("by_type") or {}).items()):
        log(f"  {count} × {kind}")
    if not summary["valid"]:
        for err in summary["errors"]:
            log(f"CRIT  {err}")
        _end(session, run, stage, "failed", "ChaosGate produced invalid exposition format", payload)
        return

    try:
        (artifacts / "metrics.prom").write_text(exposition, encoding="utf-8")
        (artifacts / "prometheus.yml").write_text(
            json.dumps(prometheus.scrape_config(), indent=2), encoding="utf-8"
        )
        (artifacts / "alerts.yml").write_text(prometheus.ALERT_RULES, encoding="utf-8")
        log("Wrote metrics.prom, prometheus.yml and alerts.yml to the run artifacts")
    except OSError as exc:
        log(f"could not write artifacts: {exc}")

    if runtime.get("base"):
        target_metrics = runtime["base"].rstrip("/") + "/metrics"
        log(f"Probing the target for its own exporter: {target_metrics}")
        try:
            res = httpx.get(target_metrics, timeout=4)
            if res.status_code == 200 and "# TYPE" in res.text:
                target_summary = prometheus.summarize(res.text)
                payload["target_exporter"] = target_summary
                log(f"  target exposes {target_summary['families']} families")
            else:
                log(f"  target has no Prometheus exporter (HTTP {res.status_code})")
                payload["target_exporter"] = {"present": False}
        except Exception as exc:  # noqa: BLE001
            log(f"  no exporter on the target ({type(exc).__name__})")
            payload["target_exporter"] = {"present": False}

    prom = tool_get("prometheus")
    if prometheus.configured():
        log(f"Querying Prometheus at {prom.get('binary')}")
        targets = prometheus.targets()
        payload["targets"] = targets
        if targets.get("ok"):
            log(f"  {targets['up']}/{targets['count']} scrape targets healthy")
        probe = prometheus.query('chaosgate_gate_score')
        payload["query"] = probe
        if probe.get("ok"):
            log(f"  chaosgate_gate_score → {probe['series']} series")
        else:
            log(f"  query failed: {probe.get('reason')}")

        push = prometheus.push_metrics(
            "chaosgate", exposition, {"repo": repo_label, "run": run.id}
        )
        payload["pushgateway"] = push
        if push.get("pushed"):
            log(f"  pushed run metrics to the Pushgateway ({push['url']})")

        _end(session, run, stage, "passed",
             f"{summary['families']} families exported · Prometheus reachable", payload)
        return

    log("PROMETHEUS_URL is not set — no server to query.")
    log("ChaosGate still serves /metrics; point a Prometheus at it to close the loop.")
    payload["degraded"] = True
    _end(session, run, stage, "degraded",
         f"{summary['families']} metric families exported · no Prometheus configured",
         payload, degraded=True)


# ------------------------------------------------------------------ stage 11
def _stage_chaos(session, run, runtime: dict[str, Any], cfg, repo_label: str) -> None:
    stage = _begin(session, run, "chaos")
    log = _logger(session, run, "chaos")

    chaos = (cfg or {}).get("chaos") or {}
    if not chaos.get("enabled"):
        log("Chaos is disabled in the contract — skipping")
        _end(session, run, stage, "skipped", "Chaos not enabled")
        return
    if not runtime.get("restart"):
        log("The target does not expose a restart hook")
        _end(session, run, stage, "skipped", "No restart hook for this target")
        return

    experiments = chaos.get("experiments") or ["restart_api"]
    log(f"Experiments: {', '.join(experiments)}")
    results = []
    worst = 0.0
    failed = False

    for experiment in experiments[:4]:
        log(f"── {experiment} ──")
        log("Killing the target process…")
        t0 = time.perf_counter()
        try:
            # Re-read: restart() rebinds stop/health to the new incarnation.
            stop = runtime.get("stop")
            if callable(stop):
                stop()
        except Exception as exc:  # noqa: BLE001
            log(f"kill failed: {exc}")

        time.sleep(0.3)
        try:
            probe = httpx.get(runtime["health"], timeout=1.0)
            log(f"target still answering ({probe.status_code}) — kill was ineffective")
        except Exception:  # noqa: BLE001
            log("confirmed down")

        log("Restarting…")
        ok = False
        try:
            ok = bool(runtime["restart"]())
        except Exception as exc:  # noqa: BLE001
            log(f"restart raised: {exc}")

        recovered = False
        if ok:
            for _ in range(60):
                try:
                    res = httpx.get(runtime["health"], timeout=1.5)
                    if res.status_code < 400:
                        recovered = True
                        break
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(0.2)

        elapsed = time.perf_counter() - t0
        worst = max(worst, elapsed)
        results.append({"experiment": experiment, "recovered": recovered, "recovery_s": round(elapsed, 3)})
        metrics.chaos_experiments_total.inc(
            repo=repo_label, experiment=experiment, result="recovered" if recovered else "failed"
        )
        if recovered:
            metrics.chaos_recovery_seconds.set(elapsed, repo=repo_label, experiment=experiment)
            log(f"Recovered in {elapsed * 1000:.0f}ms")
        else:
            failed = True
            log("Target never came back healthy")
            break

    payload = {"experiments": results, "recovery_ms": round(worst * 1000, 1)}
    if failed:
        _end(session, run, stage, "failed", "Service did not recover after the kill", payload)
    else:
        _end(session, run, stage, "passed",
             f"Recovered from {len(results)} experiment(s) · worst {worst * 1000:.0f}ms", payload)


# ------------------------------------------------------------------ stage 12
def _stage_grafana(session, run, repo_label: str, artifacts: Path) -> None:
    stage = _begin(session, run, "grafana")
    log = _logger(session, run, "grafana")

    dashboard = grafana.build_dashboard()
    run_dashboard = grafana.build_run_dashboard(run.id, repo_label)
    panels = sum(1 for p in dashboard["panels"] if p.get("type") != "row")
    rows = sum(1 for p in dashboard["panels"] if p.get("type") == "row")
    log(f"Built the ChaosGate dashboard: {panels} panels across {rows} rows")

    payload: dict[str, Any] = {"panels": panels, "rows": rows, "uid": dashboard["uid"]}

    try:
        (artifacts / "grafana-dashboard.json").write_text(
            json.dumps(dashboard, indent=2), encoding="utf-8"
        )
        (artifacts / "grafana-run-dashboard.json").write_text(
            json.dumps(run_dashboard, indent=2), encoding="utf-8"
        )
        (artifacts / "grafana-datasource.yml").write_text(
            json.dumps(grafana.datasource_provisioning(), indent=2), encoding="utf-8"
        )
        log("Wrote dashboard + datasource provisioning to the run artifacts")
        payload["artifacts"] = [
            "grafana-dashboard.json", "grafana-run-dashboard.json", "grafana-datasource.yml"
        ]
    except OSError as exc:
        log(f"could not write dashboard artifacts: {exc}")

    published = grafana.publish(dashboard)
    payload["publish"] = published

    if published.get("published"):
        log(f"Published to Grafana → {published['url']} (v{published.get('version')})")
        grafana.publish(run_dashboard)
        _end(session, run, stage, "passed", f"Dashboard live at {published['url']}", payload)
        return

    reason = published.get("reason", "not configured")
    log(f"Not published: {reason}")
    log("Import grafana-dashboard.json manually, or set GRAFANA_URL and GRAFANA_API_KEY.")
    payload["degraded"] = True
    _end(session, run, stage, "degraded",
         f"{panels}-panel dashboard generated · {reason}", payload, degraded=True)


# ------------------------------------------------------------------ stage 13
def _stage_verdict(session, run, findings, policy, detected, cfg, caps, artifacts: Path) -> dict[str, Any]:
    stage = _begin(session, run, "verdict")
    session.refresh(run)

    stages = []
    for item in sorted(run.stages, key=lambda s: s.index):
        if item.key == "verdict":
            continue
        stages.append({
            "key": item.key,
            "name": item.name,
            "status": item.status,
            "degraded": bool(item.degraded),
            "summary": item.summary,
            "metrics": json.loads(item.metrics_json) if item.metrics_json else {},
            "duration_ms": int((item.finished_at - item.started_at).total_seconds() * 1000)
            if item.started_at and item.finished_at else None,
        })

    decision = decide(stages, findings, policy)
    report = {
        **decision,
        "run_id": run.id,
        "repo": run.repo.full_name if run.repo else None,
        "branch": run.branch,
        "commit": run.commit_sha,
        "trigger": run.trigger,
        "stages": stages,
        "findings": findings,
        "detected": detected,
        "config": summarize_config(cfg),
        "policy": policy,
        "capabilities": caps.get("summary", {}),
        "toolchain": {k: {"available": v.get("available"), "detail": v.get("detail"), "version": v.get("version")}
                      for k, v in (caps.get("tools") or {}).items()},
        "generated_at": utcnow().isoformat(),
    }

    _log(session, run, "verdict",
         "PASS — gate open" if decision["verdict"] == "PASS" else "FAIL — gate sealed")
    _log(session, run, "verdict", f"score {decision['score']}/100")
    counts = decision["counts"]
    _log(session, run, "verdict",
         f"{counts['passed']} passed · {counts['failed']} failed · "
         f"{counts['skipped']} skipped · {counts['degraded']} degraded")
    for reason in decision["reasons"]:
        _log(session, run, "verdict", f"block: {reason}")
    for warn in decision["warnings"][:12]:
        _log(session, run, "verdict", f"warn: {warn}")
    for note in decision["degraded"]:
        _log(session, run, "verdict", f"degraded: {note}")

    try:
        (artifacts / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        (artifacts / "report.md").write_text(_markdown_report(report), encoding="utf-8")
    except OSError:
        pass

    _end(session, run, stage,
         "passed" if decision["verdict"] == "PASS" else "failed",
         decision["summary"], decision)
    return report


def _markdown_report(report: dict[str, Any]) -> str:
    icon = "✅" if report["verdict"] == "PASS" else "🚫"
    lines = [
        f"# {icon} ChaosGate — {report['verdict']}",
        "",
        f"**Repository:** {report.get('repo')}  ",
        f"**Branch:** {report.get('branch')}  ",
        f"**Commit:** `{(report.get('commit') or 'n/a')[:12]}`  ",
        f"**Score:** {report.get('score')}/100  ",
        f"**Generated:** {report.get('generated_at')}",
        "",
        f"> {report.get('summary')}",
        "",
        "## Stages",
        "",
        "| Stage | Status | Duration | Summary |",
        "| --- | --- | --- | --- |",
    ]
    for stage in report.get("stages", []):
        dur = f"{stage['duration_ms']}ms" if stage.get("duration_ms") is not None else "—"
        detail = (stage.get("summary") or "").replace("|", "\\|")
        lines.append(f"| {stage['name']} | {stage['status']} | {dur} | {detail} |")

    if report.get("reasons"):
        lines += ["", "## Blocking reasons", ""] + [f"- {r}" for r in report["reasons"]]
    if report.get("degraded"):
        lines += ["", "## Degraded stages", ""] + [f"- {d}" for d in report["degraded"]]
    if report.get("findings"):
        lines += ["", "## Findings", "", "| Severity | Title | Detail |", "| --- | --- | --- |"]
        for f in report["findings"][:40]:
            lines.append(
                f"| {f.get('severity')} | {f.get('title')} | "
                f"{(f.get('detail') or '')[:140].replace('|', chr(92) + '|')} |"
            )
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ utilities
def _run_cmd(command: str, cwd: Path, timeout: int = 120) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["CI"] = "1"
    env["npm_config_yes"] = "true"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Redirect every __pycache__ write out of the repository. Without this a
    # gate run leaves .pyc files in the user's workspace, and the editor then
    # offers those build artifacts up as changes to commit.
    env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp(prefix="cg_pyc_")
    bindir = str(Path(sys.executable).parent)
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")

    python_executable = subprocess.list2cmdline([sys.executable])
    if command.startswith("python ") or command.startswith("python3 "):
        command = python_executable + command[command.index(" "):]
    elif command in {"python", "python3"}:
        command = python_executable

    try:
        proc = subprocess.run(
            command, cwd=cwd, shell=True, capture_output=True,
            text=True, timeout=timeout, env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return 124, f"command timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _parse_duration(value: str) -> float:
    text = str(value).strip().lower()
    try:
        if text.endswith("ms"):
            return max(0.5, float(text[:-2]) / 1000)
        if text.endswith("s"):
            return max(0.5, float(text[:-1]))
        if text.endswith("m"):
            return max(0.5, float(text[:-1]) * 60)
        return max(0.5, float(text))
    except ValueError:
        return 10.0


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# -------------------------------------------------------------- target boot
def _start_target(root: Path, detected, cfg, image, log) -> dict[str, Any] | None:
    """Boot the application under test, preferring the most realistic option."""
    services = (cfg or {}).get("services") or {}
    api = services.get("api") or services.get("frontend") or {}
    health_path = api.get("health") or "/health"

    # 1. A real container, if we built one and Docker works.
    if image and image.get("tag") and tool_get("docker").get("available"):
        container_port = int(api.get("port") or _guess_port(root, cfg) or 8000)
        started = _start_container(image["tag"], container_port, health_path, log)
        if started:
            return started
        log("Container did not become healthy — falling back to an in-process boot")

    # 2. An importable Flask app.
    for name in ("app.py", "main.py", "server.py", "wsgi.py"):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "Flask(" not in text:
            continue
        started = _start_flask_module(root, name[:-3], health_path, log)
        if started:
            return started

    # 3. Anything static.
    static_root = None
    for candidate in ("dist", "build", "public", "out", "src"):
        directory = root / candidate
        if directory.is_dir() and any(directory.glob("*.html")):
            static_root = directory
            break
    if (root / "index.html").is_file():
        static_root = root
    if static_root:
        return _start_static(static_root, log)

    log("No container, Flask module, or static index.html to boot")
    return None


def _guess_port(root: Path, cfg) -> int | None:
    compose = docker_runner.find_compose(root)
    if compose:
        try:
            import yaml

            doc = yaml.safe_load(compose.read_text(encoding="utf-8")) or {}
            for svc in (doc.get("services") or {}).values():
                for mapping in (svc.get("ports") or []):
                    text = str(mapping)
                    if ":" in text:
                        return int(text.split(":")[-1].split("/")[0])
        except Exception:  # noqa: BLE001
            pass
    dockerfile = docker_runner.find_dockerfile(root)
    if dockerfile:
        import re

        match = re.search(r"^\s*EXPOSE\s+(\d+)", dockerfile.read_text(encoding="utf-8", errors="ignore"), re.M | re.I)
        if match:
            return int(match.group(1))
    return None


def _start_container(tag: str, container_port: int, health_path: str, log) -> dict[str, Any] | None:
    port = _free_port()
    started = docker_runner.run_container(tag, port, container_port, log, env={"PORT": str(container_port)})
    if not started.get("running"):
        return None

    base = f"http://127.0.0.1:{port}"
    health = base + (health_path if health_path.startswith("/") else "/" + health_path)
    name = started["name"]

    healthy = False
    for _ in range(50):
        try:
            if httpx.get(health, timeout=1.0).status_code < 500:
                healthy = True
                break
        except Exception:  # noqa: BLE001
            time.sleep(0.4)
    if not healthy:
        tail = docker_runner.container_logs(name, 20)
        for line in tail.splitlines()[-12:]:
            log(f"  container: {line}")
        docker_runner.stop_container(name)
        return None

    log(f"Container {name} healthy on :{port}")
    state: dict[str, Any] = {
        "kind": "docker", "base": base, "health": health, "health_path": health_path,
        "port": port, "container": name, "tag": tag,
        "stop": lambda: docker_runner.stop_container(name),
    }

    def restart() -> bool:
        docker_runner.stop_container(state["container"])
        nxt = _start_container(tag, container_port, health_path, lambda m: None)
        if not nxt:
            return False
        _rebind(state, nxt)
        return True

    state["restart"] = restart
    return state


def _start_flask_module(root: Path, module: str, health_path: str, log) -> dict[str, Any] | None:
    port = _free_port()
    try:
        import importlib.util

        file_path = root / f"{module}.py"
        spec_name = f"cg_target_{abs(hash(str(root)))}_{module}_{port}"
        spec = importlib.util.spec_from_file_location(spec_name, file_path)
        if spec is None or spec.loader is None:
            return None

        original_cwd = os.getcwd()
        original_path = list(sys.path)
        sys.path.insert(0, str(root))
        try:
            os.chdir(root)
            imported = importlib.util.module_from_spec(spec)
            sys.modules[spec_name] = imported
            spec.loader.exec_module(imported)
        finally:
            os.chdir(original_cwd)
            sys.path[:] = original_path

        flask_app = getattr(imported, "app", None)
        if flask_app is None:
            factory = getattr(imported, "create_app", None)
            if callable(factory):
                flask_app = factory()
        if flask_app is None:
            return None

        from werkzeug.serving import make_server

        server = make_server("127.0.0.1", port, flask_app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        base = f"http://127.0.0.1:{port}"
        health = base + (health_path if health_path.startswith("/") else "/" + health_path)
        for _ in range(40):
            try:
                httpx.get(health, timeout=0.4)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.1)
        log(f"Booted Flask module {module}.py on :{port}")

        state: dict[str, Any] = {
            "kind": "flask", "base": base, "health": health,
            "health_path": health_path, "port": port,
            "stop": lambda: _shutdown(server),
        }

        def restart() -> bool:
            nxt = _start_flask_module(root, module, health_path, lambda m: None)
            if not nxt:
                return False
            _rebind(state, nxt)
            return True

        state["restart"] = restart
        return state
    except Exception as exc:  # noqa: BLE001
        log(f"Could not import {module}.py: {type(exc).__name__}: {exc}")
        return None


def _shutdown(server) -> None:
    try:
        server.shutdown()
    except Exception:  # noqa: BLE001
        pass


def _start_static(root: Path, log) -> dict[str, Any]:
    import http.server
    import socketserver

    port = _free_port()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            if self.path.rstrip("/") in ("/health", "/healthz", "/api/health"):
                body = b'{"status":"ok","served_by":"chaosgate-static"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return super().do_GET()

    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    log(f"Serving {root.name}/ statically on :{port}")

    state: dict[str, Any] = {
        "kind": "static", "base": base, "health": base + "/health",
        "health_path": "/health", "port": port,
        "stop": lambda: _shutdown(httpd),
    }

    def restart() -> bool:
        nxt = _start_static(root, lambda m: None)
        _rebind(state, nxt)
        return True

    state["restart"] = restart
    return state
