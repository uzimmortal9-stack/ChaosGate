"""HTTP surface for the folder editor and the push → pipeline flow."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from core import github_client, metrics, workspace
from core.db import SessionLocal
from core.github_client import GitHubError
from core.ids import nid
from core.models import PushRecord, Repository
from core.pipeline_service import create_run, start_run_async
from core.seed import ensure_workspace
from core.serialize import push_dict, repo_dict, run_dict
from core.settings import PUSH_BRANCH_PREFIX, PUSH_STRATEGY
from core.workspace import WorkspaceError

ws_api = Blueprint("workspace_api", __name__, url_prefix="/api/repos")


def _db():
    return SessionLocal()


def _err(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _repo_or_404(db, repo_id: str) -> Repository | None:
    return db.get(Repository, repo_id)


def _token(db) -> str | None:
    return ensure_workspace(db).github_token


def _sync_repo_state(db, repo: Repository) -> None:
    from core.models import utcnow

    if workspace.is_cloned(repo.id):
        repo.workspace_cloned = True
        repo.workspace_branch = workspace.current_branch(repo.id)
        repo.workspace_sha = workspace.head_sha(repo.id)
        repo.workspace_synced_at = utcnow()
    else:
        repo.workspace_cloned = False
    db.commit()


# ================================================================ clone / sync
@ws_api.post("/<repo_id>/workspace")
def open_workspace(repo_id: str):
    """Clone the repository locally so its folder can be browsed and edited."""
    payload = request.get_json(silent=True) or {}
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)

        if repo.is_sample and repo.local_path:
            return _err(
                "Sample targets are bundled folders, not clones. Connect a real GitHub repository to use the editor."
            )
        if not repo.full_name:
            return _err("This repository has no GitHub origin to clone.")

        if workspace.is_cloned(repo.id) and not payload.get("force"):
            _sync_repo_state(db, repo)
            return jsonify({
                "ok": True, "existed": True,
                "workspace": workspace.stats(repo.id),
                "repo": repo_dict(repo),
            })

        token = _token(db)
        if repo.private and not token:
            return _err("This repository is private — connect GitHub first.", 401)

        try:
            result = workspace.clone(
                repo.id, repo.full_name, payload.get("branch") or repo.default_branch, token
            )
        except WorkspaceError as exc:
            return _err(str(exc), 400)

        _sync_repo_state(db, repo)
        return jsonify({
            "ok": True, "clone": result,
            "workspace": workspace.stats(repo.id),
            "repo": repo_dict(repo),
        }), 201
    finally:
        db.close()


@ws_api.get("/<repo_id>/workspace")
def workspace_info(repo_id: str):
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        if not workspace.is_cloned(repo.id):
            return jsonify({"cloned": False, "repo": repo_dict(repo)})
        return jsonify({**workspace.stats(repo.id), "repo": repo_dict(repo)})
    finally:
        db.close()


@ws_api.delete("/<repo_id>/workspace")
def close_workspace(repo_id: str):
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        workspace.remove(repo.id)
        repo.workspace_cloned = False
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


@ws_api.post("/<repo_id>/workspace/pull")
def pull_workspace(repo_id: str):
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        if not workspace.is_cloned(repo.id):
            return _err("Open the workspace first.")
        try:
            result = workspace.pull(repo.id, _token(db), repo.full_name)
        except WorkspaceError as exc:
            return _err(str(exc))
        _sync_repo_state(db, repo)
        return jsonify({"ok": result["ok"], "output": result["output"], "workspace": workspace.stats(repo.id)})
    finally:
        db.close()


# ================================================================ file browser
@ws_api.get("/<repo_id>/files")
def list_files(repo_id: str):
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        try:
            if repo.is_sample and repo.local_path and not workspace.is_cloned(repo.id):
                return _err("Sample targets are read-only. Connect a GitHub repository to use the editor.")
            return jsonify(workspace.tree(
                repo.id,
                request.args.get("path", ""),
                show_hidden=request.args.get("hidden") == "1",
            ))
        except WorkspaceError as exc:
            return _err(str(exc))
    finally:
        db.close()


@ws_api.get("/<repo_id>/files/all")
def all_files(repo_id: str):
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        return jsonify({"files": workspace.flat_tree(repo.id)})
    finally:
        db.close()


@ws_api.get("/<repo_id>/file")
def read_file(repo_id: str):
    path = request.args.get("path")
    if not path:
        return _err("A path query parameter is required.")
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        try:
            return jsonify(workspace.read_file(repo.id, path))
        except WorkspaceError as exc:
            return _err(str(exc), 404)
    finally:
        db.close()


@ws_api.put("/<repo_id>/file")
def save_file(repo_id: str):
    payload = request.get_json(silent=True) or {}
    path = payload.get("path")
    if not path:
        return _err("A path is required.")
    if "content" not in payload:
        return _err("Content is required.")
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        try:
            result = workspace.write_file(repo.id, path, payload["content"])
        except WorkspaceError as exc:
            return _err(str(exc))
        return jsonify({**result, "status": workspace.status(repo.id)})
    finally:
        db.close()


@ws_api.post("/<repo_id>/file")
def create_file(repo_id: str):
    payload = request.get_json(silent=True) or {}
    path = payload.get("path")
    if not path:
        return _err("A path is required.")
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        try:
            result = workspace.create_entry(
                repo.id, path, payload.get("type", "file"), payload.get("content", "")
            )
        except WorkspaceError as exc:
            return _err(str(exc))
        return jsonify({**result, "status": workspace.status(repo.id)}), 201
    finally:
        db.close()


@ws_api.delete("/<repo_id>/file")
def delete_file(repo_id: str):
    path = request.args.get("path") or (request.get_json(silent=True) or {}).get("path")
    if not path:
        return _err("A path is required.")
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        try:
            result = workspace.delete_entry(repo.id, path)
        except WorkspaceError as exc:
            return _err(str(exc))
        return jsonify({**result, "status": workspace.status(repo.id)})
    finally:
        db.close()


@ws_api.post("/<repo_id>/file/rename")
def rename_file(repo_id: str):
    payload = request.get_json(silent=True) or {}
    if not payload.get("path") or not payload.get("to"):
        return _err("Both path and to are required.")
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        try:
            result = workspace.rename_entry(repo.id, payload["path"], payload["to"])
        except WorkspaceError as exc:
            return _err(str(exc))
        return jsonify({**result, "status": workspace.status(repo.id)})
    finally:
        db.close()


# =================================================================== git state
@ws_api.get("/<repo_id>/status")
def git_status(repo_id: str):
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        return jsonify(workspace.status(repo.id))
    finally:
        db.close()


@ws_api.get("/<repo_id>/diff")
def git_diff(repo_id: str):
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        return jsonify({
            "diff": workspace.diff(repo.id, request.args.get("path")),
            "status": workspace.status(repo.id),
        })
    finally:
        db.close()


@ws_api.post("/<repo_id>/discard")
def git_discard(repo_id: str):
    payload = request.get_json(silent=True) or {}
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        result = workspace.discard(repo.id, payload.get("path"))
        return jsonify({**result, "status": workspace.status(repo.id)})
    finally:
        db.close()


# ======================================================================= push
@ws_api.post("/<repo_id>/push")
def push_changes(repo_id: str):
    """Commit, push, optionally open a PR, then fire the pipeline.

    This is the core loop the product is built around: edit → push → gate.
    """
    payload = request.get_json(silent=True) or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return _err("A commit message is required.")

    strategy = payload.get("strategy") or PUSH_STRATEGY
    if strategy not in ("branch_pr", "direct"):
        return _err("strategy must be branch_pr or direct")

    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        if not workspace.is_cloned(repo.id):
            return _err("Open the workspace before pushing.")

        token = _token(db)
        if not token:
            return _err("Connect GitHub before pushing.", 401)

        base = repo.default_branch or "main"
        branch = payload.get("branch")
        if strategy == "branch_pr" and not branch:
            branch = workspace.branch_name(payload.get("prefix") or PUSH_BRANCH_PREFIX)

        try:
            result = workspace.commit_and_push(
                repo.id, repo.full_name, message, token,
                paths=payload.get("paths"), strategy=strategy,
                target_branch=branch, base_branch=base,
            )
        except WorkspaceError as exc:
            metrics.github_pushes_total.inc(repo=repo.full_name, result="error")
            return _err(str(exc))

        metrics.github_pushes_total.inc(repo=repo.full_name, result="ok")

        record = PushRecord(
            id=nid("push"),
            repo_id=repo.id,
            branch=result["branch"],
            base_branch=base,
            sha=result["sha"],
            message=message,
            files_json=json.dumps(result["files"]),
            file_count=result["file_count"],
            strategy=strategy,
        )
        db.add(record)

        pull_request = None
        pr_error = None
        if strategy == "branch_pr" and payload.get("open_pr", True):
            title = payload.get("pr_title") or message.split("\n")[0][:120]
            body = payload.get("pr_body") or (
                "Opened by **ChaosGate** from the workspace editor.\n\n"
                f"- {result['file_count']} file(s) changed\n"
                f"- Branch `{result['branch']}` → `{base}`\n\n"
                "The ChaosGate release gate will post its verdict as a commit status "
                "on this branch. Make it a required check to block merges on failure."
            )
            try:
                pull_request = github_client.create_pull_request(
                    token, repo.full_name, result["branch"], base, title, body
                )
                record.pr_number = pull_request.get("number")
                record.pr_url = pull_request.get("html_url")
            except GitHubError as exc:
                pr_error = str(exc)

        db.commit()

        run_payload = None
        if payload.get("run_gate", True):
            run = create_run(
                db, repo,
                trigger="push",
                branch=result["branch"],
                commit_sha=result["sha"],
                commit_message=message,
                pr_number=record.pr_number,
            )
            run.pr_url = record.pr_url
            record.run_id = run.id
            db.commit()
            start_run_async(run.id, token)
            run_payload = run_dict(run, include_stages=True)

        _sync_repo_state(db, repo)

        return jsonify({
            "ok": True,
            "push": push_dict(record),
            "pull_request": pull_request,
            "pr_error": pr_error,
            "run": run_payload,
            "repo": repo_dict(repo),
        }), 201
    finally:
        db.close()


@ws_api.get("/<repo_id>/pushes")
def list_pushes(repo_id: str):
    db = _db()
    try:
        repo = _repo_or_404(db, repo_id)
        if not repo:
            return _err("Repository not connected.", 404)
        return jsonify({"pushes": [push_dict(p) for p in (repo.pushes or [])]})
    finally:
        db.close()
