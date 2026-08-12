from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from core.models import PipelineRun, Repository, Stage, Workspace


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def workspace_dict(ws: Workspace) -> dict[str, Any]:
    return {
        "id": ws.id,
        "mode": ws.mode,
        "github_login": ws.github_login,
        "github_avatar": ws.github_avatar,
        "connected": bool(ws.github_token),
        "policy": json.loads(ws.policy_json) if ws.policy_json else {},
    }


def repo_dict(repo: Repository, include_runs: bool = False) -> dict[str, Any]:
    data = {
        "id": repo.id,
        "owner": repo.owner,
        "name": repo.name,
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "default_branch": repo.default_branch,
        "language": repo.language,
        "description": repo.description,
        "is_sample": repo.is_sample,
        "last_status": repo.last_status,
        "last_run_id": repo.last_run_id,
        "last_run_at": iso(repo.last_run_at),
        "connected_at": iso(repo.connected_at),
    }
    if include_runs:
        data["runs"] = [run_dict(r) for r in sorted(repo.runs, key=lambda x: x.created_at, reverse=True)[:12]]
    return data


def stage_dict(stage: Stage) -> dict[str, Any]:
    metrics = json.loads(stage.metrics_json) if stage.metrics_json else {}
    started = stage.started_at
    finished = stage.finished_at
    duration_ms = None
    if started and finished:
        duration_ms = int((finished - started).total_seconds() * 1000)
    return {
        "key": stage.key,
        "name": stage.name,
        "index": stage.index,
        "status": stage.status,
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
            "is_sample": run.repo.is_sample,
        }
        if run.repo
        else None,
        "status": run.status,
        "conclusion": run.conclusion,
        "trigger": run.trigger,
        "engine": run.engine,
        "branch": run.branch,
        "commit_sha": run.commit_sha,
        "summary": run.summary,
        "started_at": iso(run.started_at),
        "finished_at": iso(run.finished_at),
        "created_at": iso(run.created_at),
    }
    if include_stages:
        data["stages"] = [stage_dict(s) for s in sorted(run.stages, key=lambda s: s.index)]
    if include_report:
        data["report"] = json.loads(run.report_json) if run.report_json else None
    return data
