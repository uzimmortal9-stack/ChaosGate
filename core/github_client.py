from __future__ import annotations

from typing import Any

import httpx

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ChaosGate/1.0",
    }


def get_user(token: str) -> dict[str, Any]:
    with httpx.Client(timeout=20) as client:
        res = client.get(f"{API}/user", headers=_headers(token))
    if res.status_code >= 400:
        raise GitHubError("GitHub rejected that token. Check scopes: repo, workflow.", res.status_code)
    data = res.json()
    return {
        "login": data.get("login"),
        "avatar": data.get("avatar_url"),
        "name": data.get("name") or data.get("login"),
        "html_url": data.get("html_url"),
    }


def list_repos(token: str, limit: int = 40) -> list[dict[str, Any]]:
    with httpx.Client(timeout=30) as client:
        res = client.get(
            f"{API}/user/repos",
            headers=_headers(token),
            params={"per_page": limit, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
        )
    if res.status_code >= 400:
        raise GitHubError("Could not list repositories.", res.status_code)
    out = []
    for repo in res.json():
        out.append(
            {
                "full_name": repo.get("full_name"),
                "name": repo.get("name"),
                "owner": (repo.get("owner") or {}).get("login"),
                "html_url": repo.get("html_url"),
                "default_branch": repo.get("default_branch") or "main",
                "language": repo.get("language"),
                "description": repo.get("description"),
                "private": repo.get("private"),
                "pushed_at": repo.get("pushed_at"),
            }
        )
    return out


def get_repo(token: str, full_name: str) -> dict[str, Any]:
    with httpx.Client(timeout=20) as client:
        res = client.get(f"{API}/repos/{full_name}", headers=_headers(token))
    if res.status_code == 404:
        # Try unauthenticated for public repos
        res = httpx.get(f"{API}/repos/{full_name}", timeout=20, headers={"User-Agent": "ChaosGate/1.0"})
    if res.status_code >= 400:
        raise GitHubError(f"Repository {full_name} was not found or is not accessible.", res.status_code)
    repo = res.json()
    return {
        "full_name": repo.get("full_name"),
        "name": repo.get("name"),
        "owner": (repo.get("owner") or {}).get("login"),
        "html_url": repo.get("html_url"),
        "default_branch": repo.get("default_branch") or "main",
        "language": repo.get("language"),
        "description": repo.get("description"),
        "clone_url": repo.get("clone_url"),
        "private": repo.get("private"),
    }


def get_public_repo(full_name: str) -> dict[str, Any]:
    res = httpx.get(f"{API}/repos/{full_name}", timeout=20, headers={"User-Agent": "ChaosGate/1.0"})
    if res.status_code >= 400:
        raise GitHubError(f"Public repository {full_name} was not found.", res.status_code)
    repo = res.json()
    return {
        "full_name": repo.get("full_name"),
        "name": repo.get("name"),
        "owner": (repo.get("owner") or {}).get("login"),
        "html_url": repo.get("html_url"),
        "default_branch": repo.get("default_branch") or "main",
        "language": repo.get("language"),
        "description": repo.get("description"),
        "clone_url": repo.get("clone_url"),
        "private": repo.get("private"),
    }


def dispatch_workflow(token: str, full_name: str, branch: str, workflow: str = "chaosgate.yml") -> None:
    with httpx.Client(timeout=20) as client:
        res = client.post(
            f"{API}/repos/{full_name}/actions/workflows/{workflow}/dispatches",
            headers=_headers(token),
            json={"ref": branch},
        )
    if res.status_code not in (204, 200):
        raise GitHubError(
            "Could not dispatch chaosgate.yml. Add the workflow file and grant the token the workflow scope.",
            res.status_code,
        )


def latest_workflow_run(token: str, full_name: str) -> dict[str, Any] | None:
    with httpx.Client(timeout=20) as client:
        res = client.get(
            f"{API}/repos/{full_name}/actions/runs",
            headers=_headers(token),
            params={"per_page": 1},
        )
    if res.status_code >= 400:
        return None
    runs = (res.json() or {}).get("workflow_runs") or []
    return runs[0] if runs else None
