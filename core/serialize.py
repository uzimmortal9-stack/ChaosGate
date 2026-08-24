from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from core.models import PipelineRun, PushRecord, Repository, Stage, WebhookEvent, Workspace


def iso(value: datetime | None) -> str | None:
    """Serialise as UTC ISO-8601 so browsers localise correctly."""
    if not value:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def workspace_dict(ws: Workspace) -> dict[str, Any]:
    return {
        "id": ws.id,
        "mode": ws.mode,
        "github_login": ws.github_login,
        "github_avatar": ws.github_avatar,
        "github_name": ws.github_name,
        "auth_method": ws.auth_method,
        "scopes": (ws.github_scopes or "").split(",") if ws.github_scopes else [],
        "connected": bool(ws.github_token),
        "policy": json.loads(ws.policy_json) if ws.policy_json else {},
    }


def repo_dict(repo: Repository, include_runs: bool = False, include_pushes: bool = False) -> dict[str, Any]:
    data = {
        "id": repo.id,
        "owner": repo.owner,
        "name": repo.name,
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "clone_url": repo.clone_url,
        "default_branch": repo.default_branch,
        "language": repo.language,
        "description": repo.description,
        "private": bool(repo.private),
        "is_sample": repo.is_sample,
        "workspace_cloned": bool(repo.workspace_cloned),
        "workspace_branch": repo.workspace_branch,
        "workspace_sha": repo.workspace_sha,
        "workspace_synced_at": iso(repo.workspace_synced_at),
        "webhook_id": repo.webhook_id,
        "workflow_installed": bool(repo.workflow_installed),
        "auto_run_on_push": bool(repo.auto_run_on_push),
        "last_status": repo.last_status,
        "last_run_id": repo.last_run_id,
        "last_run_at": iso(repo.last_run_at),
        "connected_at": iso(repo.connected_at),
    }
    if include_runs:
        runs = sorted(repo.runs, key=lambda x: x.created_at, reverse=True)[:15]
        data["runs"] = [run_dict(r) for r in runs]
    if include_pushes:
        data["pushes"] = [push_dict(p) for p in (repo.pushes or [])[:15]]
    return data


def stage_dict(stage: Stage) -> dict[str, Any]:
    metrics = json.loads(stage.metrics_json) if stage.metrics_json else {}
    duration_ms = None
    if stage.started_at and stage.finished_at:
        duration_ms = int((stage.finished_at - stage.started_at).total_seconds() * 1000)
    return {
        "key": stage.key,
        "name": stage.name,
        "index": stage.index,
        "status": stage.status,
        "degraded": bool(stage.degraded),
        "summary": stage.summary,
        "logs": stage.logs or "",
        "metrics": metrics,
        "started_at": iso(stage.started_at),
        "finished_at": iso(stage.finished_at),
        "duration_ms": duration_ms,
    }


def run_dict(run: PipelineRun, include_stages: bool = False, include_report: bool = False) -> dict[str, Any]:
    data = {
        "id": run.id,
        "repo_id": run.repo_id,
        "repo": {
            "id": run.repo.id,
            "full_name": run.repo.full_name,
            "name": run.repo.name,
            "owner": run.repo.owner,
            "language": run.repo.language,
            "html_url": run.repo.html_url,
            "is_sample": run.repo.is_sample,
        } if run.repo else None,
        "status": run.status,
        "conclusion": run.conclusion,
        "trigger": run.trigger,
        "engine": run.engine,
        "branch": run.branch,
        "commit_sha": run.commit_sha,
        "commit_short": (run.commit_sha or "")[:7] or None,
        "commit_message": run.commit_message,
        "pr_number": run.pr_number,
        "pr_url": run.pr_url,
        "score": run.score,
        "summary": run.summary,
        "duration_s": run.duration_s,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "created_at": iso(run.created_at),
    }
    if include_stages:
        data["stages"] = [stage_dict(s) for s in sorted(run.stages, key=lambda s: s.index)]
    if include_report:
        data["report"] = json.loads(run.report_json) if run.report_json else None
    return data


def push_dict(push: PushRecord) -> dict[str, Any]:
    return {
        "id": push.id,
        "repo_id": push.repo_id,
        "branch": push.branch,
        "base_branch": push.base_branch,
        "sha": push.sha,
        "short_sha": (push.sha or "")[:7] or None,
        "message": push.message,
        "files": json.loads(push.files_json) if push.files_json else [],
        "file_count": push.file_count,
        "strategy": push.strategy,
        "pr_number": push.pr_number,
        "pr_url": push.pr_url,
        "run_id": push.run_id,
        "status": push.status,
        "created_at": iso(push.created_at),
    }


def webhook_dict(event: WebhookEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "delivery_id": event.delivery_id,
        "event": event.event,
        "repo": event.repo_full_name,
        "branch": event.branch,
        "sha": (event.sha or "")[:7] or None,
        "action": event.action,
        "verified": event.verified,
        "run_id": event.triggered_run_id,
        "note": event.note,
        "created_at": iso(event.created_at),
    }
