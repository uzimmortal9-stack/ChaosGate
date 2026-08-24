from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from core import metrics
from core.settings import (
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    GITHUB_OAUTH_SCOPES,
    GITHUB_WEBHOOK_SECRET,
    OAUTH_ENABLED,
)

API = "https://api.github.com"
OAUTH_AUTHORIZE = "https://github.com/login/oauth/authorize"
OAUTH_TOKEN = "https://github.com/login/oauth/access_token"


class GitHubError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ChaosGate/2.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _track(operation: str, ok: bool) -> None:
    try:
        metrics.github_api_calls_total.inc(operation=operation, result="ok" if ok else "error")
    except Exception:  # noqa: BLE001
        pass


def _request(
    method: str,
    path: str,
    token: str | None = None,
    operation: str = "generic",
    expect: tuple[int, ...] = (200, 201, 202, 204),
    **kwargs: Any,
) -> httpx.Response:
    url = path if path.startswith("http") else f"{API}{path}"
    try:
        with httpx.Client(timeout=kwargs.pop("timeout", 25), follow_redirects=True) as client:
            res = client.request(method, url, headers=_headers(token), **kwargs)
    except Exception as exc:  # noqa: BLE001
        _track(operation, False)
        raise GitHubError(f"GitHub is unreachable: {type(exc).__name__}") from exc
    ok = res.status_code in expect
    _track(operation, ok)
    return res


def _error_message(res: httpx.Response, fallback: str) -> str:
    try:
        body = res.json()
        message = body.get("message") or fallback
        errors = body.get("errors")
        if errors and isinstance(errors, list):
            details = "; ".join(
                e.get("message") or f"{e.get('field', '')} {e.get('code', '')}".strip()
                for e in errors if isinstance(e, dict)
            )
            if details:
                message = f"{message} — {details}"
        return message
    except Exception:  # noqa: BLE001
        return fallback


# --------------------------------------------------------------------- OAuth
def oauth_enabled() -> bool:
    return OAUTH_ENABLED


def oauth_authorize_url(redirect_uri: str, state: str | None = None) -> tuple[str, str]:
    if not OAUTH_ENABLED:
        raise GitHubError("GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.")
    state = state or secrets.token_urlsafe(24)
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": GITHUB_OAUTH_SCOPES.replace(",", " "),
        "state": state,
        "allow_signup": "true",
    }
    return f"{OAUTH_AUTHORIZE}?{urlencode(params)}", state


def oauth_exchange(code: str, redirect_uri: str) -> dict[str, Any]:
    if not OAUTH_ENABLED:
        raise GitHubError("GitHub OAuth is not configured.")
    try:
        with httpx.Client(timeout=25) as client:
            res = client.post(
                OAUTH_TOKEN,
                headers={"Accept": "application/json", "User-Agent": "ChaosGate/2.0"},
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
    except Exception as exc:  # noqa: BLE001
        _track("oauth_exchange", False)
        raise GitHubError(f"Could not reach GitHub to exchange the code: {exc}") from exc

    data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    if res.status_code != 200 or data.get("error"):
        _track("oauth_exchange", False)
        raise GitHubError(
            data.get("error_description") or data.get("error") or "GitHub rejected the OAuth code."
        )
    token = data.get("access_token")
    if not token:
        _track("oauth_exchange", False)
        raise GitHubError("GitHub returned no access token.")
    _track("oauth_exchange", True)
    return {"token": token, "scope": data.get("scope", ""), "token_type": data.get("token_type")}


# ---------------------------------------------------------------------- user
def get_user(token: str) -> dict[str, Any]:
    res = _request("GET", "/user", token, operation="get_user")
    if res.status_code >= 400:
        raise GitHubError(
            _error_message(res, "GitHub rejected that token. It needs the repo and workflow scopes."),
            res.status_code,
        )
    data = res.json()
    scopes = res.headers.get("x-oauth-scopes", "")
    return {
        "login": data.get("login"),
        "avatar": data.get("avatar_url"),
        "name": data.get("name") or data.get("login"),
        "html_url": data.get("html_url"),
        "email": data.get("email"),
        "scopes": [s.strip() for s in scopes.split(",") if s.strip()],
        "public_repos": data.get("public_repos"),
        "company": data.get("company"),
    }


def _repo_row(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": repo.get("full_name"),
        "name": repo.get("name"),
        "owner": (repo.get("owner") or {}).get("login"),
        "avatar": (repo.get("owner") or {}).get("avatar_url"),
        "html_url": repo.get("html_url"),
        "clone_url": repo.get("clone_url"),
        "default_branch": repo.get("default_branch") or "main",
        "language": repo.get("language"),
        "description": repo.get("description"),
        "private": repo.get("private"),
        "fork": repo.get("fork"),
        "archived": repo.get("archived"),
        "stars": repo.get("stargazers_count"),
        "size_kb": repo.get("size"),
        "pushed_at": repo.get("pushed_at"),
        "updated_at": repo.get("updated_at"),
        "permissions": repo.get("permissions") or {},
    }


def list_repos(token: str, limit: int = 100, page: int = 1, query: str = "") -> list[dict[str, Any]]:
    if query:
        res = _request(
            "GET", "/search/repositories", token, operation="search_repos",
            params={"q": f"{query} user:@me fork:true", "per_page": min(limit, 50)},
        )
        if res.status_code >= 400:
            raise GitHubError(_error_message(res, "Repository search failed."), res.status_code)
        return [_repo_row(r) for r in (res.json().get("items") or [])]

    res = _request(
        "GET", "/user/repos", token, operation="list_repos",
        params={
            "per_page": min(limit, 100),
            "page": page,
            "sort": "pushed",
            "direction": "desc",
            "affiliation": "owner,collaborator,organization_member",
        },
    )
    if res.status_code >= 400:
        raise GitHubError(_error_message(res, "Could not list repositories."), res.status_code)
    return [_repo_row(r) for r in res.json()]


def list_orgs(token: str) -> list[dict[str, Any]]:
    res = _request("GET", "/user/orgs", token, operation="list_orgs", params={"per_page": 50})
    if res.status_code >= 400:
        return []
    return [
        {"login": o.get("login"), "avatar": o.get("avatar_url"), "description": o.get("description")}
        for o in res.json()
    ]


def get_repo(token: str | None, full_name: str) -> dict[str, Any]:
    res = _request("GET", f"/repos/{full_name}", token, operation="get_repo")
    if res.status_code == 404 and token:
        res = _request("GET", f"/repos/{full_name}", None, operation="get_repo_public")
    if res.status_code >= 400:
        raise GitHubError(
            _error_message(res, f"Repository {full_name} was not found or is not accessible."),
            res.status_code,
        )
    return _repo_row(res.json())


def get_public_repo(full_name: str) -> dict[str, Any]:
    return get_repo(None, full_name)


def list_branches(token: str | None, full_name: str) -> list[dict[str, Any]]:
    res = _request(
        "GET", f"/repos/{full_name}/branches", token, operation="list_branches",
        params={"per_page": 100},
    )
    if res.status_code >= 400:
        return []
    return [
        {"name": b.get("name"), "sha": (b.get("commit") or {}).get("sha"), "protected": b.get("protected")}
        for b in res.json()
    ]


def list_commits(token: str | None, full_name: str, branch: str = "main", limit: int = 10) -> list[dict[str, Any]]:
    res = _request(
        "GET", f"/repos/{full_name}/commits", token, operation="list_commits",
        params={"sha": branch, "per_page": limit},
    )
    if res.status_code >= 400:
        return []
    out = []
    for item in res.json():
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        out.append({
            "sha": (item.get("sha") or "")[:7],
            "full_sha": item.get("sha"),
            "message": (commit.get("message") or "").split("\n")[0][:120],
            "author": author.get("name"),
            "date": author.get("date"),
            "html_url": item.get("html_url"),
        })
    return out


# ----------------------------------------------------------------- pull request
def create_pull_request(
    token: str, full_name: str, head: str, base: str, title: str, body: str = "", draft: bool = False
) -> dict[str, Any]:
    res = _request(
        "POST", f"/repos/{full_name}/pulls", token, operation="create_pr",
        json={"title": title, "head": head, "base": base, "body": body, "draft": draft},
    )
    if res.status_code == 422:
        message = _error_message(res, "")
        if "already exists" in message.lower():
            existing = find_pull_request(token, full_name, head)
            if existing:
                return {**existing, "existed": True}
        raise GitHubError(message or "GitHub rejected the pull request.", 422)
    if res.status_code >= 400:
        raise GitHubError(_error_message(res, "Could not open a pull request."), res.status_code)
    pr = res.json()
    return {
        "number": pr.get("number"),
        "html_url": pr.get("html_url"),
        "state": pr.get("state"),
        "title": pr.get("title"),
        "head": head,
        "base": base,
        "draft": pr.get("draft"),
    }


def find_pull_request(token: str, full_name: str, head: str) -> dict[str, Any] | None:
    owner = full_name.split("/")[0]
    res = _request(
        "GET", f"/repos/{full_name}/pulls", token, operation="find_pr",
        params={"head": f"{owner}:{head}", "state": "open"},
    )
    if res.status_code >= 400:
        return None
    items = res.json() or []
    if not items:
        return None
    pr = items[0]
    return {
        "number": pr.get("number"),
        "html_url": pr.get("html_url"),
        "state": pr.get("state"),
        "title": pr.get("title"),
        "head": head,
    }


def comment_on_pr(token: str, full_name: str, number: int, body: str) -> bool:
    res = _request(
        "POST", f"/repos/{full_name}/issues/{number}/comments", token,
        operation="comment_pr", json={"body": body},
    )
    return res.status_code in (200, 201)


# ------------------------------------------------------------- commit status
def create_commit_status(
    token: str, full_name: str, sha: str, state: str, description: str,
    context: str = "ChaosGate", target_url: str | None = None,
) -> dict[str, Any]:
    """state ∈ error | failure | pending | success — this is the merge blocker."""
    payload = {"state": state, "description": description[:139], "context": context}
    if target_url:
        payload["target_url"] = target_url
    res = _request(
        "POST", f"/repos/{full_name}/statuses/{sha}", token,
        operation="commit_status", json=payload,
    )
    if res.status_code >= 400:
        raise GitHubError(_error_message(res, "Could not publish the commit status."), res.status_code)
    return {"posted": True, "state": state, "context": context}


def list_check_runs(token: str, full_name: str, ref: str) -> list[dict[str, Any]]:
    res = _request(
        "GET", f"/repos/{full_name}/commits/{ref}/check-runs", token, operation="check_runs"
    )
    if res.status_code >= 400:
        return []
    return [
        {
            "name": c.get("name"),
            "status": c.get("status"),
            "conclusion": c.get("conclusion"),
            "html_url": c.get("html_url"),
            "started_at": c.get("started_at"),
            "completed_at": c.get("completed_at"),
        }
        for c in (res.json().get("check_runs") or [])
    ]


# ---------------------------------------------------------------- workflows
def put_file(
    token: str, full_name: str, path: str, content: str, message: str, branch: str
) -> dict[str, Any]:
    """Create or update a single file via the contents API."""
    import base64

    sha = None
    probe = _request(
        "GET", f"/repos/{full_name}/contents/{path}", token,
        operation="get_content", params={"ref": branch},
    )
    if probe.status_code == 200:
        body = probe.json()
        if isinstance(body, dict):
            sha = body.get("sha")

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    res = _request(
        "PUT", f"/repos/{full_name}/contents/{path}", token,
        operation="put_content", json=payload,
    )
    if res.status_code >= 400:
        raise GitHubError(_error_message(res, f"Could not write {path}."), res.status_code)
    data = res.json()
    return {
        "path": path,
        "sha": ((data.get("content") or {}).get("sha")),
        "commit": ((data.get("commit") or {}).get("html_url")),
        "updated": bool(sha),
    }


def install_workflow(token: str, full_name: str, branch: str, content: str) -> dict[str, Any]:
    return put_file(
        token, full_name, ".github/workflows/chaosgate.yml", content,
        "ci: install the ChaosGate release gate workflow", branch,
    )


def dispatch_workflow(token: str, full_name: str, branch: str, workflow: str = "chaosgate.yml", inputs: dict | None = None) -> None:
    payload: dict[str, Any] = {"ref": branch}
    if inputs:
        payload["inputs"] = inputs
    res = _request(
        "POST", f"/repos/{full_name}/actions/workflows/{workflow}/dispatches", token,
        operation="dispatch", json=payload,
    )
    if res.status_code not in (204, 200):
        raise GitHubError(
            _error_message(
                res,
                "Could not dispatch chaosgate.yml. Install the workflow first and use a token with the workflow scope.",
            ),
            res.status_code,
        )


def list_workflow_runs(token: str, full_name: str, limit: int = 10) -> list[dict[str, Any]]:
    res = _request(
        "GET", f"/repos/{full_name}/actions/runs", token,
        operation="workflow_runs", params={"per_page": limit},
    )
    if res.status_code >= 400:
        return []
    out = []
    for run in (res.json().get("workflow_runs") or []):
        out.append({
            "id": run.get("id"),
            "name": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "event": run.get("event"),
            "branch": run.get("head_branch"),
            "sha": (run.get("head_sha") or "")[:7],
            "html_url": run.get("html_url"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
        })
    return out


def latest_workflow_run(token: str, full_name: str) -> dict[str, Any] | None:
    runs = list_workflow_runs(token, full_name, limit=1)
    return runs[0] if runs else None


# ----------------------------------------------------------------- webhooks
def create_webhook(token: str, full_name: str, url: str, secret: str, events: list[str] | None = None) -> dict[str, Any]:
    res = _request(
        "POST", f"/repos/{full_name}/hooks", token, operation="create_hook",
        json={
            "name": "web",
            "active": True,
            "events": events or ["push", "pull_request"],
            "config": {"url": url, "content_type": "json", "secret": secret, "insecure_ssl": "0"},
        },
    )
    if res.status_code == 422:
        hooks = list_webhooks(token, full_name)
        for hook in hooks:
            if (hook.get("config") or {}).get("url") == url:
                return {"id": hook.get("id"), "existed": True, "url": url}
    if res.status_code >= 400:
        raise GitHubError(_error_message(res, "Could not create the webhook."), res.status_code)
    hook = res.json()
    return {"id": hook.get("id"), "url": url, "events": hook.get("events"), "existed": False}


def list_webhooks(token: str, full_name: str) -> list[dict[str, Any]]:
    res = _request("GET", f"/repos/{full_name}/hooks", token, operation="list_hooks")
    if res.status_code >= 400:
        return []
    return res.json()


def delete_webhook(token: str, full_name: str, hook_id: int) -> bool:
    res = _request(
        "DELETE", f"/repos/{full_name}/hooks/{hook_id}", token,
        operation="delete_hook", expect=(204,),
    )
    return res.status_code == 204


def verify_webhook_signature(payload: bytes, signature: str | None, secret: str | None = None) -> bool:
    """Constant-time HMAC check for X-Hub-Signature-256."""
    secret = secret or GITHUB_WEBHOOK_SECRET
    if not secret:
        return True  # no secret configured — accept but the caller should warn
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)


def rate_limit(token: str) -> dict[str, Any]:
    res = _request("GET", "/rate_limit", token, operation="rate_limit")
    if res.status_code >= 400:
        return {}
    core = ((res.json().get("resources") or {}).get("core")) or {}
    return {
        "limit": core.get("limit"),
        "remaining": core.get("remaining"),
        "reset_in_s": max(0, int((core.get("reset") or 0) - time.time())),
    }
