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

from core.config_parser import parse_config, summarize_config
from core.db import SessionLocal
from core.detector import detect_app
from core.ids import nid
from core.models import PipelineRun, Repository, RunEvent, Stage, utcnow
from core.scanners import scan_dependencies, scan_secrets
from core.settings import DEFAULT_POLICY
from core.verdict import decide

STAGE_SPEC = [
    ("validate", "Repo validation"),
    ("detect", "Stack detect"),
    ("unit", "Unit tests"),
    ("build", "Build"),
    ("security", "Security scan"),
    ("smoke", "Smoke test"),
    ("load", "Load / traffic"),
    ("chaos", "Resilience"),
    ("verdict", "Verdict"),
]


def create_run(session, repo: Repository, trigger: str = "manual", engine: str = "local") -> PipelineRun:
    run = PipelineRun(
        id=nid("run"),
        repo_id=repo.id,
        status="queued",
        trigger=trigger,
        engine=engine,
        branch=repo.default_branch or "main",
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
    thread = threading.Thread(target=_execute_run, args=(run_id, token), daemon=True)
    thread.start()


def _execute_run(run_id: str, token: str | None) -> None:
    session = SessionLocal()
    cleanup: Path | None = None
    try:
        run = session.get(PipelineRun, run_id)
        if not run:
            return
        repo = session.get(Repository, run.repo_id)
        if not repo:
            _fail_run(session, run, "Repository record disappeared")
            return

        run.status = "running"
        run.started_at = utcnow()
        repo.last_status = "running"
        session.commit()
        _emit(session, run.id, "run", {"status": "running"})

        policy = DEFAULT_POLICY.copy()
        if repo.workspace and repo.workspace.policy_json:
            try:
                policy.update(json.loads(repo.workspace.policy_json))
            except json.JSONDecodeError:
                pass

        root, cleanup, sha = _materialize(session, run, repo, token)
        run.commit_sha = sha
        session.commit()

        findings: list[dict[str, Any]] = []
        cfg, cfg_errors = parse_config(root)
        detected: dict[str, Any] = {}
        runtime: dict[str, Any] = {}

        _stage_validate(session, run, root, cfg, cfg_errors, policy)
        detected = _stage_detect(session, run, root, cfg)
        _stage_unit(session, run, root, detected, cfg)
        _stage_build(session, run, root, detected, cfg)
        findings.extend(_stage_security(session, run, root, cfg))
        runtime = _stage_smoke(session, run, root, detected, cfg)
        try:
            _stage_load(session, run, runtime, cfg, policy)
            _stage_chaos(session, run, runtime, cfg)
            report = _stage_verdict(session, run, findings, policy, detected, cfg)
        finally:
            stop = (runtime or {}).get("stop")
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass

        conclusion = report["verdict"]
        run.status = "passed" if conclusion == "PASS" else "failed"
        run.conclusion = conclusion
        run.summary = report["summary"]
        run.report_json = json.dumps(report)
        run.finished_at = utcnow()
        repo.last_status = run.status
        repo.last_run_at = run.finished_at
        repo.last_run_id = run.id
        session.commit()
        _emit(session, run.id, "done", {"status": run.status, "conclusion": conclusion, "report": report})
    except Exception as exc:  # noqa: BLE001 — gate must always close
        try:
            run = session.get(PipelineRun, run_id)
            if run:
                _fail_run(session, run, f"Engine error: {exc}")
        except Exception:
            pass
    finally:
        if cleanup and cleanup.exists():
            shutil.rmtree(cleanup, ignore_errors=True)
        session.close()


def _fail_run(session, run: PipelineRun, message: str) -> None:
    run.status = "error"
    run.conclusion = "FAIL"
    run.summary = message
    run.finished_at = utcnow()
    if run.repo:
        run.repo.last_status = "error"
        run.repo.last_run_at = run.finished_at
    session.commit()
    _emit(session, run.id, "done", {"status": "error", "conclusion": "FAIL", "summary": message})


def _materialize(
    session, run: PipelineRun, repo: Repository, token: str | None
) -> tuple[Path, Path | None, str | None]:
    if repo.local_path and Path(repo.local_path).is_dir():
        sha = _git_sha(Path(repo.local_path))
        _log(session, run, "validate", f"Using local workspace {repo.local_path}")
        return Path(repo.local_path), None, sha

    url = None
    if repo.html_url and "github.com" in repo.html_url:
        slug = repo.full_name
        if token:
            url = f"https://x-access-token:{token}@github.com/{slug}.git"
        else:
            url = f"https://github.com/{slug}.git"
    if not url:
        raise RuntimeError("No local path or GitHub URL available to materialize the repository")

    dest = Path(tempfile.mkdtemp(prefix="cg_repo_"))
    _log(session, run, "validate", f"Cloning {repo.full_name}@{run.branch} …")
    cmd = ["git", "clone", "--depth", "1", "--branch", run.branch, url, str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"git clone failed: {exc}") from exc
    if proc.returncode != 0:
        # retry default branch / HEAD
        cmd = ["git", "clone", "--depth", "1", url, str(dest)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if proc.returncode != 0:
            shutil.rmtree(dest, ignore_errors=True)
            raise RuntimeError((proc.stderr or proc.stdout or "clone failed")[-400:])
    sha = _git_sha(dest)
    _log(session, run, "validate", f"Clone complete ({sha or 'unknown sha'})")
    return dest, dest, sha


def _git_sha(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        return None
    return None


def _stage(session, run: PipelineRun, key: str) -> Stage:
    stage = next(s for s in run.stages if s.key == key)
    return stage


def _begin(session, run: PipelineRun, key: str) -> Stage:
    stage = _stage(session, run, key)
    stage.status = "running"
    stage.started_at = utcnow()
    session.commit()
    _emit(session, run.id, "stage", {"key": key, "status": "running"})
    _log(session, run, key, f"── {stage.name} ──")
    return stage


def _end(session, run: PipelineRun, stage: Stage, status: str, summary: str, metrics: dict | None = None) -> None:
    stage.status = status
    stage.summary = summary
    stage.finished_at = utcnow()
    if metrics:
        stage.metrics_json = json.dumps(metrics)
    session.commit()
    _emit(
        session,
        run.id,
        "stage",
        {"key": stage.key, "status": status, "summary": summary, "metrics": metrics or {}},
    )


def _log(session, run: PipelineRun, key: str, line: str) -> None:
    stage = _stage(session, run, key)
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    formatted = f"[{stamp}] {line}"
    stage.logs = (stage.logs or "") + formatted + "\n"
    session.commit()
    _emit(session, run.id, "log", {"key": key, "line": formatted})


def _emit(session, run_id: str, kind: str, payload: dict[str, Any]) -> None:
    session.add(RunEvent(run_id=run_id, kind=kind, payload_json=json.dumps(payload)))
    session.commit()


def _stage_validate(session, run, root: Path, cfg, errors, policy) -> None:
    stage = _begin(session, run, "validate")
    _log(session, run, "validate", f"Inspecting {root}")
    required_any = [
        "chaosgate.yml",
        "chaosgate.yaml",
        "Dockerfile",
        "docker-compose.yml",
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "app.py",
        "main.py",
    ]
    found = [name for name in required_any if (root / name).exists()]
    for name in found:
        _log(session, run, "validate", f"found {name}")
    if errors:
        for err in errors:
            _log(session, run, "validate", f"CONFIG ERROR: {err}")
        _end(session, run, stage, "failed", errors[0])
        return
    if cfg:
        _log(session, run, "validate", "chaosgate.yml OK")
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


def _stage_detect(session, run, root: Path, cfg) -> dict[str, Any]:
    stage = _begin(session, run, "detect")
    detected = detect_app(root, cfg)
    _log(session, run, "detect", f"type={detected['type']} language={detected['language']}")
    if detected["frameworks"]:
        _log(session, run, "detect", "frameworks: " + ", ".join(detected["frameworks"]))
    for hint in detected.get("hints") or []:
        _log(session, run, "detect", hint)
    if detected.get("test_command"):
        _log(session, run, "detect", f"unit command → {detected['test_command']}")
    if detected.get("build_command"):
        _log(session, run, "detect", f"build command → {detected['build_command']}")
    _end(
        session,
        run,
        stage,
        "passed",
        f"Detected {detected['type']}",
        {k: detected[k] for k in ("type", "language", "frameworks", "test_command", "build_command")},
    )
    return detected


def _stage_unit(session, run, root: Path, detected, cfg) -> None:
    stage = _begin(session, run, "unit")
    cmd = detected.get("test_command")
    if cfg and isinstance((cfg.get("tests") or {}).get("unit"), dict):
        cmd = cfg["tests"]["unit"].get("command") or cmd
    if not cmd:
        _log(session, run, "unit", "No unit test command detected — skipping")
        _end(session, run, stage, "skipped", "No unit tests configured")
        return
    _log(session, run, "unit", f"$ {cmd}")
    code, out = _run_cmd(cmd, root, timeout=90)
    for line in out.splitlines()[-80:]:
        _log(session, run, "unit", line)
    if code == 0:
        _end(session, run, stage, "passed", "Unit tests passed")
    else:
        _end(session, run, stage, "failed", f"Unit tests failed (exit {code})")


def _stage_build(session, run, root: Path, detected, cfg) -> None:
    stage = _begin(session, run, "build")
    cmd = detected.get("build_command")
    if cfg and isinstance((cfg.get("tests") or {}).get("build"), dict):
        cmd = cfg["tests"]["build"].get("command") or cmd

    if cmd:
        _log(session, run, "build", f"$ {cmd}")
        code, out = _run_cmd(cmd, root, timeout=120)
        for line in out.splitlines()[-60:]:
            _log(session, run, "build", line)
        if code == 0:
            _end(session, run, stage, "passed", "Build succeeded")
        else:
            _end(session, run, stage, "failed", f"Build failed (exit {code})")
        return

    if (root / "Dockerfile").exists():
        _log(session, run, "build", "Dockerfile present — syntax / context check")
        text = (root / "Dockerfile").read_text(encoding="utf-8", errors="ignore")
        if "FROM " not in text:
            _end(session, run, stage, "failed", "Dockerfile is missing a FROM instruction")
            return
        _log(session, run, "build", "Dockerfile looks valid (image build skipped on control-plane host)")
        _end(session, run, stage, "passed", "Dockerfile validated")
        return

    if detected.get("language") == "python":
        _log(session, run, "build", "Python app — compileall")
        code, out = _run_cmd(f"{sys.executable} -m compileall -q .", root, timeout=40)
        for line in out.splitlines()[-40:]:
            _log(session, run, "build", line)
        if code == 0:
            _end(session, run, stage, "passed", "Python sources compiled")
        else:
            _end(session, run, stage, "failed", "Python compile failed")
        return

    _log(session, run, "build", "No build step required")
    _end(session, run, stage, "skipped", "No build command")


def _stage_security(session, run, root: Path, cfg) -> list[dict[str, Any]]:
    stage = _begin(session, run, "security")
    sec = (cfg or {}).get("security") or {}
    findings: list[dict[str, Any]] = []
    if sec.get("secret_scan", True):
        secrets = scan_secrets(root)
        findings.extend(secrets)
        _log(session, run, "security", f"Secret scan: {len(secrets)} finding(s)")
        for item in secrets:
            _log(session, run, "security", f"CRIT  {item['file']}:{item.get('line', '?')}  {item['title']}")
    if sec.get("dependency_scan", True):
        deps = scan_dependencies(root)
        findings.extend(deps)
        _log(session, run, "security", f"Dependency scan: {len(deps)} finding(s)")
        for item in deps:
            _log(session, run, "security", f"WARN  {item['title']} — {item['detail']}")
    critical = [f for f in findings if f.get("severity") == "critical"]
    if critical:
        _end(
            session,
            run,
            stage,
            "failed",
            f"{len(critical)} critical security finding(s)",
            {"findings": findings},
        )
    else:
        _end(
            session,
            run,
            stage,
            "passed",
            "No critical secrets; warnings recorded" if findings else "Clean security scan",
            {"findings": findings},
        )
    return findings


def _stage_smoke(session, run, root: Path, detected, cfg) -> dict[str, Any]:
    stage = _begin(session, run, "smoke")
    target = _start_target(root, detected, cfg, log=lambda m: _log(session, run, "smoke", m))
    if not target:
        _log(session, run, "smoke", "Could not boot a local process for this stack")
        _end(session, run, stage, "skipped", "No runnable local target")
        return {}
    url = target["health"]
    _log(session, run, "smoke", f"GET {url}")
    try:
        res = httpx.get(url, timeout=5.0)
        _log(session, run, "smoke", f"→ {res.status_code} ({res.elapsed.total_seconds()*1000:.0f}ms)")
        if res.status_code >= 400:
            target["stop"]()
            _end(session, run, stage, "failed", f"Health returned HTTP {res.status_code}")
            return {}
        _end(session, run, stage, "passed", f"Healthy {res.status_code} from {url}")
        return target
    except Exception as exc:
        target["stop"]()
        _log(session, run, "smoke", f"health check error: {exc}")
        _end(session, run, stage, "failed", "Target did not respond")
        return {}


def _stage_load(session, run, runtime: dict[str, Any], cfg, policy) -> None:
    stage = _begin(session, run, "load")
    if not runtime.get("base"):
        _log(session, run, "load", "No live target — load stage skipped")
        _end(session, run, stage, "skipped", "Requires a running target")
        return

    load_cfg = (cfg or {}).get("load") or {}
    endpoints = load_cfg.get("endpoints") or [{"method": "GET", "path": runtime.get("health_path") or "/health"}]
    vus = int(load_cfg.get("vus") or 8)
    duration = _parse_duration(load_cfg.get("duration") or "8s")
    # Keep demo runs snappy
    duration = min(duration, 6.0)
    max_p95 = int((load_cfg.get("thresholds") or {}).get("p95_ms") or policy.get("max_p95_ms") or 800)
    max_err = float((load_cfg.get("thresholds") or {}).get("error_rate") or policy.get("max_error_rate") or 0.05)
    base = runtime["base"]

    _log(session, run, "load", f"Traffic: {vus} VUs × {duration:.0f}s against {base}")
    for ep in endpoints:
        _log(session, run, "load", f"  {ep.get('method', 'GET')} {ep.get('path', '/')}")

    latencies: list[float] = []
    errors = 0
    total = 0
    stop_at = time.time() + duration

    def worker():
        nonlocal errors, total
        with httpx.Client(timeout=4.0) as client:
            while time.time() < stop_at:
                for ep in endpoints:
                    method = (ep.get("method") or "GET").upper()
                    path = ep.get("path") or "/"
                    url = base.rstrip("/") + path
                    t0 = time.perf_counter()
                    try:
                        res = client.request(method, url)
                        ms = (time.perf_counter() - t0) * 1000
                        latencies.append(ms)
                        total += 1
                        if res.status_code >= 400:
                            errors += 1
                    except Exception:
                        latencies.append((time.perf_counter() - t0) * 1000)
                        total += 1
                        errors += 1
                time.sleep(0.05)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(2, min(vus, 12)))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=duration + 4)

    if not latencies:
        _end(session, run, stage, "failed", "Load generator produced no samples")
        return

    latencies.sort()
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
    avg = statistics.mean(latencies)
    err_rate = errors / max(1, total)
    rps = total / max(0.1, duration)
    metrics = {
        "samples": total,
        "errors": errors,
        "error_rate": round(err_rate, 4),
        "p95_ms": round(p95, 1),
        "avg_ms": round(avg, 1),
        "rps": round(rps, 1),
        "threshold_p95_ms": max_p95,
        "threshold_error_rate": max_err,
        "histogram": _histogram(latencies),
    }
    _log(session, run, "load", f"samples={total} rps={rps:.1f} p95={p95:.0f}ms avg={avg:.0f}ms err={err_rate:.2%}")
    reasons = []
    if p95 > max_p95:
        reasons.append(f"p95 {p95:.0f}ms exceeds {max_p95}ms")
    if err_rate > max_err:
        reasons.append(f"error rate {err_rate:.1%} exceeds {max_err:.1%}")
    if reasons:
        _end(session, run, stage, "failed", "; ".join(reasons), metrics)
    else:
        _end(session, run, stage, "passed", f"p95 {p95:.0f}ms · {err_rate:.1%} errors", metrics)


def _stage_chaos(session, run, runtime: dict[str, Any], cfg) -> None:
    stage = _begin(session, run, "chaos")
    chaos = (cfg or {}).get("chaos") or {}
    if not chaos.get("enabled"):
        _log(session, run, "chaos", "Chaos disabled in contract — skip")
        _end(session, run, stage, "skipped", "Chaos not enabled")
        return
    if not runtime.get("restart"):
        _log(session, run, "chaos", "Target does not expose a restart hook")
        _end(session, run, stage, "skipped", "No restart hook")
        return

    experiments = chaos.get("experiments") or ["restart_api"]
    _log(session, run, "chaos", f"Experiments: {', '.join(experiments)}")
    _log(session, run, "chaos", "Killing in-process target…")
    t0 = time.perf_counter()
    runtime["stop"]()
    time.sleep(0.25)
    _log(session, run, "chaos", "Restarting target…")
    ok = runtime["restart"]()
    recovered = False
    if ok:
        for _ in range(20):
            try:
                res = httpx.get(runtime["health"], timeout=1.5)
                if res.status_code < 400:
                    recovered = True
                    break
            except Exception:
                time.sleep(0.15)
    elapsed = (time.perf_counter() - t0) * 1000
    if recovered:
        _log(session, run, "chaos", f"Recovered in {elapsed:.0f}ms")
        _end(session, run, stage, "passed", f"Recovered in {elapsed:.0f}ms", {"recovery_ms": round(elapsed, 1)})
    else:
        _log(session, run, "chaos", "Target did not come back healthy")
        _end(session, run, stage, "failed", "Failed to recover after kill", {"recovery_ms": None})


def _stage_verdict(session, run, findings, policy, detected, cfg) -> dict[str, Any]:
    stage = _begin(session, run, "verdict")
    session.refresh(run)
    stages = []
    for item in sorted(run.stages, key=lambda s: s.index):
        stages.append(
            {
                "key": item.key,
                "name": item.name,
                "status": item.status,
                "summary": item.summary,
                "metrics": json.loads(item.metrics_json) if item.metrics_json else {},
            }
        )
    decision = decide(stages, findings, policy)
    report = {
        **decision,
        "stages": stages,
        "findings": findings,
        "detected": detected,
        "config": summarize_config(cfg),
        "policy": policy,
        "generated_at": utcnow().isoformat(),
    }
    stamp = "PASS — gate open" if decision["verdict"] == "PASS" else "FAIL — gate sealed"
    _log(session, run, "verdict", stamp)
    _log(session, run, "verdict", f"score {decision['score']}/100")
    for reason in decision["reasons"]:
        _log(session, run, "verdict", f"block: {reason}")
    for warn in decision["warnings"]:
        _log(session, run, "verdict", f"warn: {warn}")
    _end(session, run, stage, "passed" if decision["verdict"] == "PASS" else "failed", decision["summary"], decision)
    return report


def _run_cmd(command: str, cwd: Path, timeout: int = 60) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["CI"] = "1"
    env["npm_config_yes"] = "true"
    bindir = str(Path(sys.executable).parent)
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    # Honour the interpreter that launched ChaosGate (venv-safe).
    if command.startswith("python ") or command.startswith("python3 "):
        command = sys.executable + command[command.index(" ") :]
    elif command in {"python", "python3"}:
        command = sys.executable
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return 124, f"command timed out after {timeout}s"
    except Exception as exc:
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
        return 8.0


def _histogram(values: list[float], buckets: int = 8) -> list[int]:
    if not values:
        return [0] * buckets
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [len(values)] + [0] * (buckets - 1)
    width = (hi - lo) / buckets
    counts = [0] * buckets
    for value in values:
        idx = min(buckets - 1, int((value - lo) / width))
        counts[idx] += 1
    return counts


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _start_target(root: Path, detected: dict[str, Any], cfg, log: Callable[[str], None]) -> dict[str, Any] | None:
    services = (cfg or {}).get("services") or {}
    api = services.get("api") or services.get("frontend") or {}
    health_path = api.get("health") or "/health"

    # Prefer an in-process Flask app we can import (samples + simple Python apps)
    for name in ("app.py", "main.py", "server.py"):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "Flask(" not in text:
            continue
        started = _start_flask_module(root, name[:-3], health_path, log)
        if started:
            return started

    # Static / built JS: serve the directory
    static_root = None
    for candidate in ("dist", "build", "public", "src"):
        if (root / candidate).is_dir() and any((root / candidate).glob("*.html")):
            static_root = root / candidate
            break
    if (root / "index.html").is_file():
        static_root = root
    if static_root:
        return _start_static(static_root, log)

    log("No Flask module or static index.html to boot on the control plane")
    return None


def _start_flask_module(root: Path, module: str, health_path: str, log) -> dict[str, Any] | None:
    port = _free_port()
    try:
        import importlib.util

        file_path = root / f"{module}.py"
        spec_name = f"cg_target_{root.name}_{module}_{port}"
        spec = importlib.util.spec_from_file_location(spec_name, file_path)
        if spec is None or spec.loader is None:
            return None
        imported = importlib.util.module_from_spec(spec)
        sys.modules[spec_name] = imported
        spec.loader.exec_module(imported)
        flask_app = getattr(imported, "app", None)
        if flask_app is None:
            return None

        flask_app.config["TESTING"] = False
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
            except Exception:
                time.sleep(0.1)
        log(f"Started Flask module {module}.py on :{port}")

        def stop():
            try:
                server.shutdown()
            except Exception:
                pass

        state = {
            "base": base,
            "health": health,
            "health_path": health_path,
            "stop": stop,
            "port": port,
        }

        def restart_inplace():
            nxt = _start_flask_module(root, module, health_path, lambda m: None)
            if not nxt:
                return False
            state.update(nxt)
            return True

        state["restart"] = restart_inplace
        return state
    except Exception as exc:
        log(f"Could not import {module}.py: {exc}")
        return None


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
            if self.path in ("/health", "/health/"):
                body = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return super().do_GET()

    httpd = socketserver.TCPServer(("127.0.0.1", port), Handler)
    httpd.allow_reuse_address = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    log(f"Serving {root.name}/ on :{port}")

    def stop():
        try:
            httpd.shutdown()
        except Exception:
            pass

    state = {"base": base, "health": base + "/health", "health_path": "/health", "stop": stop}

    def restart():
        nxt = _start_static(root, lambda m: None)
        state.update(nxt)
        return True

    state["restart"] = restart
    return state
