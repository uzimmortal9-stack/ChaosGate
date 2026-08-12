from __future__ import annotations

import json
import time

from flask import Blueprint, Response, current_app, jsonify, request, session, stream_with_context

from core import github_client
from core.db import SessionLocal
from core.github_client import GitHubError
from core.ids import nid
from core.models import PipelineRun, Repository, RunEvent
from core.pipeline_service import create_run, start_run_async
from core.seed import ensure_workspace, seed_samples
from core.serialize import repo_dict, run_dict, workspace_dict
from core.settings import DEFAULT_POLICY, ROOT

api = Blueprint("api", __name__, url_prefix="/api")
hooks = Blueprint("hooks", __name__)


def _db():
    return SessionLocal()


def _ws(db) -> Workspace:
    return ensure_workspace(db)


@api.get("/health")
def health():
    return jsonify({"ok": True, "service": "chaosgate", "gate": "armed"})


@api.get("/me")
def me():
    db = _db()
    try:
        seed_samples(db)
        ws = _ws(db)
        repos = db.query(Repository).filter_by(workspace_id=ws.id).all()
        runs = (
            db.query(PipelineRun)
            .join(Repository)
            .filter(Repository.workspace_id == ws.id)
            .order_by(PipelineRun.created_at.desc())
            .limit(8)
            .all()
        )
        passed = db.query(PipelineRun).join(Repository).filter(
            Repository.workspace_id == ws.id, PipelineRun.conclusion == "PASS"
        ).count()
        failed = db.query(PipelineRun).join(Repository).filter(
            Repository.workspace_id == ws.id, PipelineRun.conclusion == "FAIL"
        ).count()
        blocked = failed
        return jsonify(
            {
                "workspace": workspace_dict(ws),
                "stats": {
                    "repos": len(repos),
                    "runs": passed + failed,
                    "passed": passed,
                    "failed": failed,
                    "blocked": blocked,
                    "pass_rate": round(100 * passed / (passed + failed), 1) if (passed + failed) else None,
                },
                "recent_runs": [run_dict(r) for r in runs],
            }
        )
    finally:
        db.close()


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


@api.post("/auth/github")
def auth_github():
    payload = request.get_json(silent=True) or {}
    token = (payload.get("token") or "").strip()
    if not token:
        return jsonify({"error": "Paste a GitHub personal access token."}), 400
    try:
        user = github_client.get_user(token)
    except GitHubError as exc:
        return jsonify({"error": str(exc)}), 401
    db = _db()
    try:
        ws = _ws(db)
        ws.mode = "github"
        ws.github_token = token
        ws.github_login = user["login"]
        ws.github_avatar = user["avatar"]
        db.commit()
        session["workspace"] = 1
        seed_samples(db)
        return jsonify({"ok": True, "workspace": workspace_dict(ws)})
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
        db.commit()
        session.clear()
        return jsonify({"ok": True})
    finally:
        db.close()


@api.get("/github/repos")
def github_repos():
    db = _db()
    try:
        ws = _ws(db)
        if not ws.github_token:
            return jsonify({"error": "Connect GitHub first."}), 401
        try:
            repos = github_client.list_repos(ws.github_token)
        except GitHubError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"repos": repos})
    finally:
        db.close()


@api.get("/repos")
def list_repos():
    db = _db()
    try:
        seed_samples(db)
        ws = _ws(db)
        repos = (
            db.query(Repository)
            .filter_by(workspace_id=ws.id)
            .order_by(Repository.is_sample.desc(), Repository.connected_at.desc())
            .all()
        )
        return jsonify({"repos": [repo_dict(r) for r in repos]})
    finally:
        db.close()


@api.post("/repos")
def add_repo():
    payload = request.get_json(silent=True) or {}
    full_name = (payload.get("full_name") or payload.get("repo") or "").strip().lstrip("/")
    if full_name.startswith("https://github.com/"):
        full_name = full_name.replace("https://github.com/", "").removesuffix(".git")
    if "/" not in full_name:
        return jsonify({"error": "Use owner/name, for example facebook/react."}), 400
    owner, name = full_name.split("/", 1)
    full_name = f"{owner}/{name}"

    db = _db()
    try:
        ws = _ws(db)
        existing = db.query(Repository).filter_by(workspace_id=ws.id, full_name=full_name).first()
        if existing:
            return jsonify({"repo": repo_dict(existing), "existed": True})
        meta = None
        try:
            if ws.github_token:
                meta = github_client.get_repo(ws.github_token, full_name)
            else:
                meta = github_client.get_public_repo(full_name)
        except GitHubError as exc:
            if payload.get("force"):
                meta = {
                    "full_name": full_name,
                    "name": name,
                    "owner": owner,
                    "html_url": f"https://github.com/{full_name}",
                    "default_branch": "main",
                    "language": payload.get("language"),
                    "description": "Added without GitHub metadata",
                }
            else:
                return jsonify({"error": str(exc)}), 404
        repo = Repository(
            id=nid("repo"),
            workspace_id=ws.id,
            owner=meta["owner"],
            name=meta["name"],
            full_name=meta["full_name"],
            html_url=meta.get("html_url") or f"https://github.com/{full_name}",
            default_branch=meta.get("default_branch") or "main",
            language=meta.get("language"),
            description=meta.get("description"),
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
            return jsonify({"error": "Repository not connected."}), 404
        return jsonify({"repo": repo_dict(repo, include_runs=True)})
    finally:
        db.close()


@api.delete("/repos/<repo_id>")
def delete_repo(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return jsonify({"error": "Not found"}), 404
        if repo.is_sample:
            return jsonify({"error": "Sample targets stay connected — they are how the gate is demonstrated."}), 400
        db.delete(repo)
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


@api.post("/repos/<repo_id>/run")
def run_repo(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return jsonify({"error": "Repository not connected."}), 404
        active = (
            db.query(PipelineRun)
            .filter(PipelineRun.repo_id == repo.id, PipelineRun.status.in_(("queued", "running")))
            .first()
        )
        if active:
            return jsonify({"run": run_dict(active, include_stages=True), "already": True})
        run = create_run(db, repo, trigger=request.json.get("trigger") if request.is_json else "manual")
        token = repo.workspace.github_token if repo.workspace else None
        start_run_async(run.id, token)
        return jsonify({"run": run_dict(run, include_stages=True)}), 202
    finally:
        db.close()


@api.post("/repos/<repo_id>/dispatch")
def dispatch_repo(repo_id: str):
    db = _db()
    try:
        repo = db.get(Repository, repo_id)
        if not repo:
            return jsonify({"error": "Not found"}), 404
        ws = repo.workspace
        if not ws or not ws.github_token:
            return jsonify({"error": "Connect a GitHub token with the workflow scope to dispatch Actions."}), 400
        try:
            github_client.dispatch_workflow(ws.github_token, repo.full_name, repo.default_branch)
        except GitHubError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "message": f"Dispatched chaosgate.yml on {repo.full_name}"})
    finally:
        db.close()


@api.get("/runs")
def list_runs():
    db = _db()
    try:
        ws = _ws(db)
        q = db.query(PipelineRun).join(Repository).filter(Repository.workspace_id == ws.id)
        repo_id = request.args.get("repo_id")
        if repo_id:
            q = q.filter(PipelineRun.repo_id == repo_id)
        runs = q.order_by(PipelineRun.created_at.desc()).limit(40).all()
        return jsonify({"runs": [run_dict(r) for r in runs]})
    finally:
        db.close()


@api.get("/runs/<run_id>")
def get_run(run_id: str):
    db = _db()
    try:
        run = db.get(PipelineRun, run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404
        return jsonify({"run": run_dict(run, include_stages=True, include_report=True)})
    finally:
        db.close()


@api.get("/runs/<run_id>/stream")
def stream_run(run_id: str):
    def generate():
        last_id = int(request.args.get("after") or 0)
        idle = 0
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
                    .order_by(RunEvent.id.asc())
                    .all()
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
            if idle > 300:
                return
            time.sleep(0.35)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api.get("/policy")
def get_policy():
    db = _db()
    try:
        ws = _ws(db)
        policy = json.loads(ws.policy_json) if ws.policy_json else DEFAULT_POLICY
        return jsonify({"policy": policy})
    finally:
        db.close()


@api.put("/policy")
def put_policy():
    payload = request.get_json(silent=True) or {}
    db = _db()
    try:
        ws = _ws(db)
        current = json.loads(ws.policy_json) if ws.policy_json else dict(DEFAULT_POLICY)
        for key in DEFAULT_POLICY:
            if key in payload:
                current[key] = payload[key]
        ws.policy_json = json.dumps(current)
        db.commit()
        return jsonify({"policy": current})
    finally:
        db.close()


@api.get("/workflow")
def workflow_yaml():
    path = ROOT / "pipeline" / "workflows" / "chaosgate.yml"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return jsonify({"path": ".github/workflows/chaosgate.yml", "content": text})


@api.get("/contract")
def contract_yaml():
    path = ROOT / "docs" / "chaosgate.example.yml"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return jsonify({"path": "chaosgate.yml", "content": text})


@hooks.post("/webhook/github")
def github_webhook():
    payload = request.get_json(silent=True) or {}
    current_app.logger.info("github webhook: %s", payload.get("action") or payload.get("zen"))
    return jsonify({"ok": True})
