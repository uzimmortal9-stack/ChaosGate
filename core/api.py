from __future__ import annotations

import json
import time
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    request,
    send_file,
    session,
    stream_with_context,
)

from core import github_client, grafana, metrics, prometheus, toolchain, workspace
from core.db import SessionLocal
from core.github_client import GitHubError
from core.ids import nid
from core.models import PipelineRun, PushRecord, Repository, RunEvent, WebhookEvent, Workspace
from core.pipeline_service import STAGE_SPEC, create_run, start_run_async
from core.seed import ensure_workspace, seed_samples
from core.serialize import (
    push_dict,
    repo_dict,
    run_dict,
    webhook_dict,
    workspace_dict,
)
from core.settings import (
    ARTIFACTS_DIR,
    DEFAULT_POLICY,
    GITHUB_WEBHOOK_SECRET,
    K8S_NAMESPACE,
    PUBLIC_URL,
    PUSH_STRATEGY,
    ROOT,
)

api = Blueprint("api", __name__, url_prefix="/api")
hooks = Blueprint("hooks", __name__)


def _db():
    return SessionLocal()


def _ws(db) -> Workspace:
    return ensure_workspace(db)


def _token(db) -> str | None:
    return _ws(db).github_token


def _err(message: str, status: int = 400):
    return jsonify({"error": message}), status


# ============================================================== health / meta
@api.get("/health")
def health():
    return jsonify({"ok": True, "service": "chaosgate", "gate": "armed", "version": "2.0.0"})


@api.get("/capabilities")
def capabilities():
    force = request.args.get("refresh") == "1"
    caps = toolchain.probe(force=force)
    metrics.record_toolchain(caps)
    return jsonify(caps)


@api.get("/me")
def me():
    db = _db()
    try:
        seed_samples(db)
        ws = _ws(db)
        repos = db.query(Repository).filter_by(workspace_id=ws.id).all()
        runs = (
            db.query(PipelineRun).join(Repository)
            .filter(Repository.workspace_id == ws.id)
            .order_by(PipelineRun.created_at.desc()).limit(10).all()
        )
        pushes = (
            db.query(PushRecord).join(Repository)
            .filter(Repository.workspace_id == ws.id)
            .order_by(PushRecord.created_at.desc()).limit(8).all()
        )
        passed = sum(1 for r in runs if r.conclusion == "PASS")
        all_runs = db.query(PipelineRun).join(Repository).filter(Repository.workspace_id == ws.id)
        total_pass = all_runs.filter(PipelineRun.conclusion == "PASS").count()
        total_fail = all_runs.filter(PipelineRun.conclusion == "FAIL").count()
        total = total_pass + total_fail

        caps = toolchain.probe()
        return jsonify({
            "workspace": workspace_dict(ws),
            "oauth_enabled": github_client.oauth_enabled(),
            "push_strategy": PUSH_STRATEGY,
            "stats": {
                "repos": len(repos),
                "cloned": sum(1 for r in repos if r.workspace_cloned),
                "runs": total,
                "passed": total_pass,
                "failed": total_fail,
                "blocked": total_fail,
                "pushes": db.query(PushRecord).join(Repository)
                          .filter(Repository.workspace_id == ws.id).count(),
                "pass_rate": round(100 * total_pass / total, 1) if total else None,
            },
            "capabilities": caps.get("summary", {}),
            "toolchain": caps.get("tools", {}),
            "recent_runs": [run_dict(r) for r in runs],
            "recent_pushes": [push_dict(p) for p in pushes],
        })
    finally:
        db.close()


@api.get("/stages")
def stage_catalog():
    return jsonify({"stages": [{"key": k, "name": n, "index": i} for i, (k, n) in enumerate(STAGE_SPEC)]})


# ====================================================================== auth
@api.post("/auth/demo")
def auth_demo():
    db = _db()
    try:
        ws = _ws(db)
        ws.mode = "demo"
        db.commit()
        session["workspace"] = 1
        session["booted"] = True
        seed_samples(db)
        return jsonify({"ok": True, "workspace": workspace_dict(ws)})
    finally:
        db.close()


@api.get("/auth/github/status")
def auth_status():
    db = _db()
    try:
        ws = _ws(db)
        payload = {
            "oauth_enabled": github_client.oauth_enabled(),
            "connected": bool(ws.github_token),
            "workspace": workspace_dict(ws),
        }
        if ws.github_token:
            payload["rate_limit"] = github_client.rate_limit(ws.github_token)
        return jsonify(payload)
    finally:
        db.close()


def _redirect_uri() -> str:
    if PUBLIC_URL:
        return f"{PUBLIC_URL}/api/auth/github/callback"
    return request.url_root.rstrip("/") + "/api/auth/github/callback"


@api.get("/auth/github/login")
def auth_github_login():
    if not github_client.oauth_enabled():
        return _err("GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET, or use a token.", 501)
    try:
        url, state = github_client.oauth_authorize_url(_redirect_uri())
    except GitHubError as exc:
        return _err(str(exc), 501)
    session["oauth_state"] = state
    if request.args.get("json") == "1":
        return jsonify({"authorize_url": url, "state": state})
    return redirect(url)


@api.get("/auth/github/callback")
def auth_github_callback():
    error = request.args.get("error")
    if error:
        return redirect(f"/console/connect?error={error}")
    code = request.args.get("code")
    state = request.args.get("state")
    if not code:
        return redirect("/console/connect?error=missing_code")
    if state and session.get("oauth_state") and state != session.get("oauth_state"):
        return redirect("/console/connect?error=state_mismatch")

    try:
        exchanged = github_client.oauth_exchange(code, _redirect_uri())
        user = github_client.get_user(exchanged["token"])
    except GitHubError as exc:
        return redirect(f"/console/connect?error={str(exc)[:120]}")

    db = _db()
    try:
        ws = _ws(db)
        ws.mode = "github"
        ws.github_token = exchanged["token"]
        ws.github_login = user["login"]
        ws.github_avatar = user["avatar"]
        ws.github_name = user.get("name")
        ws.github_scopes = exchanged.get("scope") or ",".join(user.get("scopes") or [])
        ws.auth_method = "oauth"
        db.commit()
        session["workspace"] = 1
        session.pop("oauth_state", None)
        seed_samples(db)
    finally:
        db.close()
    return redirect("/console/connect?connected=1")


@api.post("/auth/github")
def auth_github_pat():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return _err("Paste a GitHub personal access token.")
    try:
        user = github_client.get_user(token)
    except GitHubError as exc:
        return _err(str(exc), 401)

    db = _db()
    try:
        ws = _ws(db)
        ws.mode = "github"
        ws.github_token = token
        ws.github_login = user["login"]
        ws.github_avatar = user["avatar"]
        ws.github_name = user.get("name")
        ws.github_scopes = ",".join(user.get("scopes") or [])
        ws.auth_method = "pat"
        db.commit()
        session["workspace"] = 1
        seed_samples(db)
        missing = [s for s in ("repo",) if s not in (user.get("scopes") or [])]
        return jsonify({
            "ok": True,
            "workspace": workspace_dict(ws),
            "user": user,
            "warning": f"Token is missing scope(s): {', '.join(missing)}" if missing else None,
        })
    finally:
        db.close()


@api.delete("/auth")
def auth_logout():
    db = _db()
    try:
        ws = _ws(db)
        ws.mode = "demo"
        ws.github_token = None
        ws.github_login = None
        ws.github_avatar = None
        ws.github_name = None
        ws.github_scopes = None
        ws.auth_method = None
        db.commit()
        session.clear()
        return jsonify({"ok": True})
    finally:
        db.close()


# ==================================================================== github
@api.get("/github/repos")
def github_repos():
    db = _db()
    try:
        token = _token(db)
        if not token:
            return _err("Connect GitHub first.", 401)
        try:
            repos = github_client.list_repos(
                token,
                limit=int(request.args.get("limit", 100)),
                page=int(request.args.get("page", 1)),
                query=request.args.get("q", "").strip(),
            )
        except GitHubError as exc:
            return _err(str(exc), exc.status or 400)
        connected = {
            r.full_name for r in db.query(Repository).filter_by(workspace_id=_ws(db).id).all()
        }
        for repo in repos:
            repo["connected"] = repo["full_name"] in connected
        return jsonify({"repos": repos, "count": len(repos)})
    finally:
        db.close()


@api.get("/github/orgs")
def github_orgs():
    db = _db()
    try:
        token = _token(db)
        if not token:
            return _err("Connect GitHub first.", 401)
        return jsonify({"orgs": github_client.list_orgs(token)})
    finally:
        db.close()


@api.get("/github/<path:full_name>/branches")
def github_branches(full_name: str):
    db = _db()
    try:
        return jsonify({"branches": github_client.list_branches(_token(db), full_name)})
    finally:
        db.close()


# ===================================================================== repos
@api.get("/repos")
def list_repos():
    db = _db()
    try:
        seed_samples(db)
        ws = _ws(db)
        repos = (
            db.query(Repository).filter_by(workspace_id=ws.id)
            .order_by(Repository.is_sample.desc(), Repository.connected_at.desc()).all()
        )
        return jsonify({"repos": [repo_dict(r) for r in repos]})
    finally:
        db.close()


def _normalize_full_name(raw: str) -> str | None:
    name = (raw or "").strip().lstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    name = name.removesuffix(".git").strip("/")
    parts = [p for p in name.split("/") if p]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


@api.post("/repos")
def add_repo():
    payload = request.get_json(silent=True) or {}
    full_name = _normalize_full_name(payload.get("full_name") or payload.get("repo") or "")
    if not full_name:
        return _err("Use owner/name, for example pallets/flask.")
    owner, name = full_name.split("/", 1)

    db = _db()
    try:
        ws = _ws(db)
        existing = db.query(Repository).filter_by(workspace_id=ws.id, full_name=full_name).first()
        if existing:
            return jsonify({"repo": repo_dict(existing), "existed": True})

        try:
            meta = github_client.get_repo(ws.github_token, full_name)
        except GitHubError as exc:
            if not payload.get("force"):
                return _err(str(exc), 404)
            meta = {
                "full_name": full_name, "name": name, "owner": owner,
                "html_url": f"https://github.com/{full_name}",
                "clone_url": f"https://github.com/{full_name}.git",
                "default_branch": "main", "language": payload.get("language"),
                "description": "Added without GitHub metadata", "private": False,
            }

        repo = Repository(
            id=nid("repo"),
            workspace_id=ws.id,
            owner=meta["owner"] or owner,
            name=meta["name"] or name,
            full_name=meta["full_name"] or full_name,
            html_url=meta.get("html_url") or f"https://github.com/{full_name}",
            clone_url=meta.get("clone_url"),
            default_branch=meta.get("default_branch") or "main",
            language=meta.get("language"),
            description=meta.get("description"),
            private=bool(meta.get("private")),
            is_sample=False,
        )
        db.add(repo)
        db.commit()
        return jsonify({"repo": repo_dict(repo)}), 201
    finally:
        db.close()


@api.get("/repos/<repo_id>")
def get_repo(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        data = repo_dict(repo, include_runs=True, include_pushes=True)
        if repo.workspace_cloned and workspace.is_cloned(repo.id):
            try:
                data["workspace"] = workspace.stats(repo.id)
            except Exception as exc:  # noqa: BLE001
                data["workspace"] = {"cloned": False, "error": str(exc)}
        return jsonify({"repo": data})
    finally:
        db.close()


@api.delete("/repos/<repo_id>")
def delete_repo(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return _err("Not found", 404)
        if repo.is_sample:
            return _err("Sample targets stay connected — they are how the gate is demonstrated.")
        workspace.remove(repo.id)
        db.delete(repo)
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


@api.patch("/repos/<repo_id>")
def update_repo(repo_id: str):
    payload = request.get_json(silent=True) or {}
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return _err("Not found", 404)
        if "auto_run_on_push" in payload:
            repo.auto_run_on_push = bool(payload["auto_run_on_push"])
        if "default_branch" in payload and payload["default_branch"]:
            repo.default_branch = str(payload["default_branch"])
        db.commit()
        return jsonify({"repo": repo_dict(repo)})
    finally:
        db.close()


@api.post("/repos/<repo_id>/run")
def run_repo(repo_id: str):
    payload = request.get_json(silent=True) or {}
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        active = (
            db.query(PipelineRun)
            .filter(PipelineRun.repo_id == repo.id, PipelineRun.status.in_(("queued", "running")))
            .first()
        )
        if active:
            return jsonify({"run": run_dict(active, include_stages=True), "already": True})

        branch = payload.get("branch")
        sha = None
        if repo.workspace_cloned and workspace.is_cloned(repo.id):
            branch = branch or workspace.current_branch(repo.id)
            sha = workspace.head_sha(repo.id, short=False)

        run = create_run(
            db, repo,
            trigger=payload.get("trigger") or "manual",
            branch=branch,
            commit_sha=sha,
        )
        start_run_async(run.id, repo.workspace.github_token if repo.workspace else None)
        return jsonify({"run": run_dict(run, include_stages=True)}), 202
    finally:
        db.close()


@api.post("/repos/<repo_id>/dispatch")
def dispatch_repo(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return _err("Not found", 404)
        token = _token(db)
        if not token:
            return _err("Connect a GitHub token with the workflow scope to dispatch Actions.")
        try:
            github_client.dispatch_workflow(token, repo.full_name, repo.default_branch)
        except GitHubError as exc:
            return _err(str(exc), exc.status or 400)
        return jsonify({"ok": True, "message": f"Dispatched chaosgate.yml on {repo.full_name}"})
    finally:
        db.close()


@api.get("/repos/<repo_id>/actions")
def repo_actions(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return _err("Not found", 404)
        token = _token(db)
        if not token:
            return jsonify({"runs": [], "error": "GitHub is not connected"})
        return jsonify({"runs": github_client.list_workflow_runs(token, repo.full_name, 10)})
    finally:
        db.close()


@api.post("/repos/<repo_id>/workflow")
def install_workflow(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return _err("Not found", 404)
        token = _token(db)
        if not token:
            return _err("Connect GitHub with the workflow scope first.", 401)
        path = ROOT / "pipeline" / "workflows" / "chaosgate.yml"
        content = path.read_text(encoding="utf-8")
        try:
            result = github_client.install_workflow(token, repo.full_name, repo.default_branch, content)
        except GitHubError as exc:
            return _err(str(exc), exc.status or 400)
        repo.workflow_installed = True
        db.commit()
        return jsonify({"ok": True, "result": result, "repo": repo_dict(repo)})
    finally:
        db.close()


@api.post("/repos/<repo_id>/webhook")
def install_webhook(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return _err("Not found", 404)
        token = _token(db)
        if not token:
            return _err("Connect GitHub first.", 401)
        base = PUBLIC_URL or request.url_root.rstrip("/")
        if base.startswith("http://localhost") or base.startswith("http://127."):
            return _err(
                "GitHub cannot reach a localhost URL. Set PUBLIC_URL to a publicly reachable address first."
            )
        url = f"{base}/webhook/github"
        try:
            hook = github_client.create_webhook(token, repo.full_name, url, GITHUB_WEBHOOK_SECRET or "chaosgate")
        except GitHubError as exc:
            return _err(str(exc), exc.status or 400)
        repo.webhook_id = hook.get("id")
        db.commit()
        return jsonify({"ok": True, "webhook": hook, "url": url})
    finally:
        db.close()


@api.delete("/repos/<repo_id>/webhook")
def remove_webhook(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo or not repo.webhook_id:
            return _err("No webhook registered", 404)
        token = _token(db)
        if token:
            github_client.delete_webhook(token, repo.full_name, repo.webhook_id)
        repo.webhook_id = None
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


# ====================================================================== runs
@api.get("/runs")
def list_runs():
    db = _db()
    try:
        ws = _ws(db)
        q = db.query(PipelineRun).join(Repository).filter(Repository.workspace_id == ws.id)
        repo_id = request.args.get("repo_id")
        if repo_id:
            q = q.filter(PipelineRun.repo_id == repo_id)
        status = request.args.get("status")
        if status:
            q = q.filter(PipelineRun.status == status)
        runs = q.order_by(PipelineRun.created_at.desc()).limit(int(request.args.get("limit", 50))).all()
        return jsonify({"runs": [run_dict(r) for r in runs]})
    finally:
        db.close()


@api.get("/runs/<run_id>")
def get_run(run_id: str):
    db = _db()
    try:
        run = db.get(PipelineRun, run_id)
        if not run:
            return _err("Run not found", 404)
        return jsonify({"run": run_dict(run, include_stages=True, include_report=True)})
    finally:
        db.close()


@api.get("/runs/<run_id>/recovery")
def run_recovery(run_id: str):
    """What it would take to recover from this failing run. Read-only."""
    db = _db()
    try:
        run = db.get(PipelineRun, run_id)
        if not run:
            return _err("Run not found", 404)
        from core import recovery

        plan = json.loads(run.recovery_json) if run.recovery_json else None
        if plan is None:
            plan = recovery.build_revert_plan(db, run.repo, run)
        return jsonify({
            "plan": plan,
            "incident_url": run.incident_url,
            "reverted_by": run.reverted_by,
            "can_revert": bool(run.commit_sha) and not run.repo.is_sample,
        })
    finally:
        db.close()


@api.post("/runs/<run_id>/revert")
def run_revert(run_id: str):
    """Open a revert pull request for a failing default-branch commit.

    Deliberately a PR, not a push to the branch: a recovery tool that rewrites
    a shared branch on its own becomes the next outage.
    """
    db = _db()
    try:
        run = db.get(PipelineRun, run_id)
        if not run:
            return _err("Run not found", 404)
        repo = run.repo
        if repo.is_sample:
            return _err("Sample targets have no GitHub remote to revert against.")
        if not run.commit_sha:
            return _err("This run has no commit SHA to revert.")
        token = _token(db)
        if not token:
            return _err("Connect GitHub before reverting.", 401)

        from core import recovery

        result = recovery.execute_revert(
            repo.id, repo.full_name, token, run.commit_sha,
            repo.default_branch or "main",
        )
        if not result.get("ok"):
            return jsonify(result), 400

        pull = result.get("pull_request") or {}
        run.reverted_by = pull.get("html_url") or result.get("branch")
        db.commit()
        return jsonify({**result, "run": run_dict(run)})
    finally:
        db.close()


@api.post("/runs/<run_id>/incident")
def run_incident(run_id: str):
    """File (or find) the GitHub issue for a failing default-branch run."""
    db = _db()
    try:
        run = db.get(PipelineRun, run_id)
        if not run:
            return _err("Run not found", 404)
        if run.repo.is_sample:
            return _err("Sample targets have no GitHub repository to file against.")
        token = _token(db)
        if not token:
            return _err("Connect GitHub first.", 401)

        from core import recovery

        report = json.loads(run.report_json) if run.report_json else None
        plan = json.loads(run.recovery_json) if run.recovery_json else \
            recovery.build_revert_plan(db, run.repo, run)
        result = recovery.open_incident(token, run.repo, run, plan, report)
        if result.get("created") or result.get("existed"):
            run.incident_url = result.get("url")
            run.incident_number = result.get("number")
            db.commit()
            return jsonify(result)
        return jsonify(result), 400
    finally:
        db.close()


@api.get("/runs/<run_id>/artifacts")
def run_artifacts(run_id: str):
    directory = ARTIFACTS_DIR / run_id
    if not directory.is_dir():
        return jsonify({"artifacts": []})
    items = []
    for path in sorted(directory.iterdir()):
        if path.is_file():
            items.append({
                "name": path.name,
                "size": path.stat().st_size,
                "url": f"/api/runs/{run_id}/artifacts/{path.name}",
            })
    return jsonify({"artifacts": items})


@api.get("/runs/<run_id>/artifacts/<path:name>")
def run_artifact(run_id: str, name: str):
    directory = (ARTIFACTS_DIR / run_id).resolve()
    target = (directory / name).resolve()
    try:
        target.relative_to(directory)
    except ValueError:
        return _err("Invalid artifact path", 400)
    if not target.is_file():
        return _err("Artifact not found", 404)
    as_download = request.args.get("download") == "1"
    return send_file(target, as_attachment=as_download, download_name=target.name)


@api.get("/runs/<run_id>/stream")
def stream_run(run_id: str):
    def generate():
        last_id = int(request.args.get("after") or 0)
        idle = 0
        yield ": chaosgate stream open\n\n"
        while True:
            db = SessionLocal()
            try:
                run = db.get(PipelineRun, run_id)
                if not run:
                    yield f"data: {json.dumps({'kind': 'error', 'payload': {'message': 'missing'}})}\n\n"
                    return
                events = (
                    db.query(RunEvent)
                    .filter(RunEvent.run_id == run_id, RunEvent.id > last_id)
                    .order_by(RunEvent.id.asc()).limit(400).all()
                )
                for event in events:
                    last_id = event.id
                    idle = 0
                    body = {"id": event.id, "kind": event.kind, "payload": json.loads(event.payload_json)}
                    yield f"data: {json.dumps(body)}\n\n"
                    if event.kind == "done":
                        return
                if run.status in {"passed", "failed", "error"} and not events:
                    yield f"data: {json.dumps({'kind': 'done', 'payload': {'status': run.status, 'conclusion': run.conclusion}})}\n\n"
                    return
            finally:
                db.close()
            idle += 1
            if idle % 30 == 0:
                yield ": keepalive\n\n"
            if idle > 1200:
                return
            time.sleep(0.3)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ==================================================================== policy
@api.get("/policy")
def get_policy():
    db = _db()
    try:
        ws = _ws(db)
        policy = dict(DEFAULT_POLICY)
        if ws.policy_json:
            policy.update(json.loads(ws.policy_json))
        return jsonify({"policy": policy, "defaults": DEFAULT_POLICY})
    finally:
        db.close()


@api.put("/policy")
def put_policy():
    payload = request.get_json(silent=True) or {}
    db = _db()
    try:
        ws = _ws(db)
        current = dict(DEFAULT_POLICY)
        if ws.policy_json:
            current.update(json.loads(ws.policy_json))
        for key in DEFAULT_POLICY:
            if key in payload:
                current[key] = payload[key]
        ws.policy_json = json.dumps(current)
        db.commit()
        return jsonify({"policy": current})
    finally:
        db.close()


# =============================================================== observability
@api.get("/observability")
def observability():
    caps = toolchain.probe()
    exposition = metrics.render()
    return jsonify({
        "prometheus": {
            "configured": prometheus.configured(),
            "tool": caps["tools"].get("prometheus"),
            "exposition": prometheus.summarize(exposition),
            "scrape_config": prometheus.scrape_config(),
            "targets": prometheus.targets() if prometheus.configured() else None,
        },
        "grafana": {
            "tool": caps["tools"].get("grafana"),
            "health": grafana.health(),
            "dashboard_uid": "chaosgate-main",
        },
        "k6": caps["tools"].get("k6"),
        "docker": caps["tools"].get("docker"),
        "kubernetes": {**caps["tools"].get("kubectl", {}), "namespace": K8S_NAMESPACE},
    })


@api.get("/observability/dashboard")
def observability_dashboard():
    dashboard = grafana.build_dashboard()
    if request.args.get("download") == "1":
        return Response(
            json.dumps(dashboard, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=chaosgate-dashboard.json"},
        )
    return jsonify(dashboard)


@api.post("/observability/dashboard/publish")
def publish_dashboard():
    result = grafana.publish(grafana.build_dashboard())
    if not result.get("published"):
        return jsonify(result), 400
    return jsonify(result)


@api.get("/observability/query")
def observability_query():
    expr = request.args.get("q") or "chaosgate_gate_score"
    return jsonify(prometheus.query(expr))


# ==================================================================== assets
@api.get("/workflow")
def workflow_yaml():
    path = ROOT / "pipeline" / "workflows" / "chaosgate.yml"
    return jsonify({
        "path": ".github/workflows/chaosgate.yml",
        "content": path.read_text(encoding="utf-8") if path.is_file() else "",
    })


@api.get("/contract")
def contract_yaml():
    path = ROOT / "docs" / "chaosgate.example.yml"
    return jsonify({
        "path": "chaosgate.yml",
        "content": path.read_text(encoding="utf-8") if path.is_file() else "",
    })


@api.get("/webhooks")
def list_webhook_events():
    db = _db()
    try:
        events = db.query(WebhookEvent).order_by(WebhookEvent.created_at.desc()).limit(40).all()
        return jsonify({"events": [webhook_dict(e) for e in events]})
    finally:
        db.close()


# ================================================================== webhook in
@hooks.post("/webhook/github")
def github_webhook():
    raw = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256")
    event_name = request.headers.get("X-GitHub-Event", "unknown")
    delivery = request.headers.get("X-GitHub-Delivery")
    payload = request.get_json(silent=True) or {}

    # The secret is resolved here and passed down explicitly, so there is
    # exactly one source of truth for whether a signature is required.
    verified = github_client.verify_webhook_signature(raw, signature, GITHUB_WEBHOOK_SECRET)
    if GITHUB_WEBHOOK_SECRET and not verified:
        metrics.webhook_events_total.inc(event=event_name, result="bad-signature")
        return _err("Invalid webhook signature", 401)

    if event_name == "ping":
        metrics.webhook_events_total.inc(event="ping", result="ok")
        return jsonify({"ok": True, "pong": True})

    repo_full = ((payload.get("repository") or {}).get("full_name"))
    branch = None
    sha = None
    action = payload.get("action")
    pr_number = None
    commit_message = None

    if event_name == "push":
        branch = (payload.get("ref") or "").replace("refs/heads/", "") or None
        sha = payload.get("after")
        head = payload.get("head_commit") or {}
        commit_message = (head.get("message") or "").split("\n")[0][:200] or None
    elif event_name == "pull_request":
        pr = payload.get("pull_request") or {}
        branch = ((pr.get("head") or {}).get("ref"))
        sha = ((pr.get("head") or {}).get("sha"))
        pr_number = pr.get("number")
        commit_message = pr.get("title")

    db = _db()
    try:
        record = WebhookEvent(
            delivery_id=delivery, event=event_name, repo_full_name=repo_full,
            branch=branch, sha=sha, action=action, verified=verified,
        )
        db.add(record)
        db.commit()

        should_run = (
            event_name == "push"
            or (event_name == "pull_request" and action in ("opened", "synchronize", "reopened"))
        )
        if not should_run or not repo_full:
            record.note = f"No gate run for {event_name}/{action}"
            db.commit()
            metrics.webhook_events_total.inc(event=event_name, result="ignored")
            return jsonify({"ok": True, "ran": False, "reason": record.note})

        if sha and sha.startswith("0000000"):
            record.note = "Branch deletion — ignored"
            db.commit()
            metrics.webhook_events_total.inc(event=event_name, result="ignored")
            return jsonify({"ok": True, "ran": False, "reason": record.note})

        repo = db.query(Repository).filter_by(full_name=repo_full).first()
        if not repo:
            record.note = f"{repo_full} is not connected to this workspace"
            db.commit()
            metrics.webhook_events_total.inc(event=event_name, result="unknown-repo")
            return jsonify({"ok": True, "ran": False, "reason": record.note})
        if not repo.auto_run_on_push:
            record.note = "auto_run_on_push is disabled for this repository"
            db.commit()
            metrics.webhook_events_total.inc(event=event_name, result="disabled")
            return jsonify({"ok": True, "ran": False, "reason": record.note})

        run = create_run(
            db, repo, trigger=f"github:{event_name}", branch=branch or repo.default_branch,
            commit_sha=sha, commit_message=commit_message, pr_number=pr_number,
        )
        record.triggered_run_id = run.id
        record.note = f"Started gate run {run.id}"
        db.commit()
        start_run_async(run.id, repo.workspace.github_token if repo.workspace else None)
        metrics.webhook_events_total.inc(event=event_name, result="triggered")
        current_app.logger.info("webhook %s → run %s", event_name, run.id)
        return jsonify({"ok": True, "ran": True, "run_id": run.id})
    finally:
        db.close()
