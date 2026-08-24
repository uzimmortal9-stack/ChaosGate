"""Local working copies of connected repositories.

This is what makes "open the folder of your app and push changes" real:

* ``clone``     — full clone into data/workspaces/<repo_id>
* ``tree``      — directory listing for the file browser
* ``read_file`` / ``write_file`` — the editor
* ``status`` / ``diff`` — what changed
* ``commit_and_push`` — commit, push a branch, and (optionally) open a PR

All paths are resolved and checked against the workspace root, so the editor
cannot escape into the host filesystem.
"""

from __future__ import annotations

import fnmatch
import mimetypes
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from core.settings import (
    GIT_AUTHOR_EMAIL,
    GIT_AUTHOR_NAME,
    PUSH_BRANCH_PREFIX,
    WORKSPACES_DIR,
)

HIDDEN_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", ".next", ".turbo",
    ".cache", "target", ".idea", ".vscode", "coverage", ".tox", "site-packages",
}

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff", ".svgz",
    ".pdf", ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z", ".rar",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".mov", ".avi", ".webm", ".wav", ".ogg",
    ".so", ".dylib", ".dll", ".exe", ".bin", ".class", ".jar", ".pyc", ".wasm",
    ".db", ".sqlite", ".sqlite3",
}

MAX_EDIT_BYTES = 2_000_000


class WorkspaceError(Exception):
    pass


@dataclass
class GitResult:
    ok: bool
    output: str
    code: int = 0


def workspace_path(repo_id: str) -> Path:
    return WORKSPACES_DIR / repo_id


def _git(
    root: Path,
    *args: str,
    timeout: int = 180,
    env_extra: dict[str, str] | None = None,
    raw: bool = False,
) -> GitResult:
    """Run git. `raw=True` preserves leading whitespace, which the porcelain
    status format encodes as meaning (a leading space is a real status code)."""
    env = os.environ.copy()
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "echo",
        "GIT_AUTHOR_NAME": GIT_AUTHOR_NAME,
        "GIT_AUTHOR_EMAIL": GIT_AUTHOR_EMAIL,
        "GIT_COMMITTER_NAME": GIT_AUTHOR_NAME,
        "GIT_COMMITTER_EMAIL": GIT_AUTHOR_EMAIL,
        "LC_ALL": "C",
    })
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True,
            timeout=timeout, env=env,
        )
        if raw:
            out = proc.stdout or ""
            if proc.returncode != 0:
                out += proc.stderr or ""
        else:
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return GitResult(proc.returncode == 0, out, proc.returncode)
    except FileNotFoundError:
        return GitResult(False, "git is not installed on this host", 127)
    except subprocess.TimeoutExpired:
        return GitResult(False, f"git {args[0]} timed out after {timeout}s", 124)
    except Exception as exc:  # noqa: BLE001
        return GitResult(False, str(exc), 1)


def _redact(text: str, token: str | None) -> str:
    if token and token in text:
        text = text.replace(token, "***")
    return text


def remote_url(full_name: str, token: str | None) -> str:
    if token:
        return f"https://x-access-token:{token}@github.com/{full_name}.git"
    return f"https://github.com/{full_name}.git"


# ------------------------------------------------------------------ lifecycle
def is_cloned(repo_id: str) -> bool:
    return (workspace_path(repo_id) / ".git").is_dir()


def clone(repo_id: str, full_name: str, branch: str, token: str | None = None, depth: int | None = None) -> dict[str, Any]:
    """Clone (or refresh) a repository into the local workspace."""
    dest = workspace_path(repo_id)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)

    url = remote_url(full_name, token)
    args = ["clone"]
    if depth:
        args += ["--depth", str(depth)]
    args += ["--branch", branch, url, str(dest)]

    result = _git(dest.parent, *args, timeout=300)
    if not result.ok:
        # Retry without the explicit branch (repo may use a different default).
        args = ["clone"] + (["--depth", str(depth)] if depth else []) + [url, str(dest)]
        result = _git(dest.parent, *args, timeout=300)
        if not result.ok:
            shutil.rmtree(dest, ignore_errors=True)
            raise WorkspaceError(_redact(result.output, token)[-600:] or "clone failed")

    _git(dest, "config", "user.name", GIT_AUTHOR_NAME)
    _git(dest, "config", "user.email", GIT_AUTHOR_EMAIL)
    # Never persist the token inside .git/config.
    _git(dest, "remote", "set-url", "origin", f"https://github.com/{full_name}.git")

    return {
        "path": str(dest),
        "branch": current_branch(repo_id),
        "sha": head_sha(repo_id),
        "cloned_at": time.time(),
    }


def remove(repo_id: str) -> None:
    shutil.rmtree(workspace_path(repo_id), ignore_errors=True)


def pull(repo_id: str, token: str | None, full_name: str) -> dict[str, Any]:
    root = workspace_path(repo_id)
    if not (root / ".git").is_dir():
        raise WorkspaceError("workspace is not cloned")
    url = remote_url(full_name, token)
    result = _git(root, "pull", "--ff-only", url, current_branch(repo_id), timeout=180)
    return {"ok": result.ok, "output": _redact(result.output, token)[-1500:]}


def current_branch(repo_id: str) -> str:
    result = _git(workspace_path(repo_id), "rev-parse", "--abbrev-ref", "HEAD", timeout=15)
    return result.output.strip() if result.ok else "main"


def head_sha(repo_id: str, short: bool = True) -> str | None:
    args = ["rev-parse"] + (["--short"] if short else []) + ["HEAD"]
    result = _git(workspace_path(repo_id), *args, timeout=15)
    return result.output.strip() if result.ok else None


def last_commit(repo_id: str) -> dict[str, Any] | None:
    result = _git(
        workspace_path(repo_id), "log", "-1", "--pretty=format:%h%x1f%an%x1f%ar%x1f%s", timeout=15
    )
    if not result.ok or "\x1f" not in result.output:
        return None
    sha, author, when, subject = (result.output.split("\x1f") + ["", "", "", ""])[:4]
    return {"sha": sha, "author": author, "when": when, "subject": subject}


def branches(repo_id: str) -> list[str]:
    result = _git(workspace_path(repo_id), "branch", "--format=%(refname:short)", timeout=15)
    if not result.ok:
        return []
    return [b.strip() for b in result.output.splitlines() if b.strip()]


# -------------------------------------------------------------- path handling
def _safe_join(repo_id: str, rel: str) -> Path:
    """Resolve a workspace-relative path, refusing anything that leaves it.

    Absolute paths are rejected outright rather than silently reinterpreted as
    relative — quietly turning "/etc/passwd" into "<workspace>/etc/passwd" is
    contained but surprising, and surprise is how path bugs get shipped.
    """
    root = workspace_path(repo_id).resolve()
    rel = (rel or "").strip()
    if rel.startswith(("/", "\\")) or (len(rel) > 1 and rel[1] == ":"):
        raise WorkspaceError("absolute paths are not allowed — use a path relative to the repository root")
    if not rel or rel == ".":
        return root
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise WorkspaceError("path escapes the workspace root")
    if ".git" in candidate.relative_to(root).parts:
        raise WorkspaceError("the .git directory is not editable")
    return candidate


def _is_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    try:
        with path.open("rb") as fh:
            return b"\x00" in fh.read(4096)
    except OSError:
        return True


def _load_gitignore(root: Path) -> list[str]:
    patterns: list[str] = []
    path = root / ".gitignore"
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line.rstrip("/"))
    return patterns


def _ignored(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


# ----------------------------------------------------------------- browsing
def tree(repo_id: str, rel: str = "", show_hidden: bool = False) -> dict[str, Any]:
    """One directory level, sorted folders-first."""
    root = workspace_path(repo_id)
    if not root.is_dir():
        raise WorkspaceError("workspace is not cloned yet")
    target = _safe_join(repo_id, rel)
    if not target.is_dir():
        raise WorkspaceError(f"{rel or '/'} is not a directory")

    ignore = _load_gitignore(root)
    entries: list[dict[str, Any]] = []
    changed = {item["path"] for item in status(repo_id).get("files", [])}

    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        name = child.name
        if name == ".git":
            continue
        if not show_hidden and name in HIDDEN_DIRS:
            continue
        relpath = str(child.relative_to(root)).replace(os.sep, "/")
        try:
            stat = child.stat()
        except OSError:
            continue
        entries.append({
            "name": name,
            "path": relpath,
            "type": "dir" if child.is_dir() else "file",
            "size": stat.st_size if child.is_file() else None,
            "modified": stat.st_mtime,
            "binary": child.is_file() and _is_binary(child),
            "ignored": _ignored(name, ignore),
            "dirty": relpath in changed or any(c.startswith(relpath + "/") for c in changed),
            "language": _language(child.suffix.lower()) if child.is_file() else None,
        })

    parent = None
    if rel:
        parent = str(Path(rel).parent).replace(os.sep, "/")
        parent = "" if parent == "." else parent

    return {
        "path": rel,
        "parent": parent,
        "entries": entries,
        "branch": current_branch(repo_id),
        "sha": head_sha(repo_id),
    }


def flat_tree(repo_id: str, limit: int = 3000) -> list[str]:
    """Every tracked-ish file path, for the quick-open palette."""
    root = workspace_path(repo_id)
    if not root.is_dir():
        return []
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in HIDDEN_DIRS and d != ".git"]
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = str(full.relative_to(root)).replace(os.sep, "/")
            out.append(rel)
            if len(out) >= limit:
                return sorted(out)
    return sorted(out)


LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript", ".json": "json",
    ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".md": "markdown", ".markdown": "markdown", ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".fish": "shell",
    ".sql": "sql", ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".swift": "swift", ".xml": "xml", ".svg": "xml",
    ".txt": "text", ".env": "shell", ".dockerfile": "dockerfile", ".tf": "hcl",
}


def _language(suffix: str) -> str:
    return LANGUAGES.get(suffix, "text")


def read_file(repo_id: str, rel: str) -> dict[str, Any]:
    path = _safe_join(repo_id, rel)
    if not path.is_file():
        raise WorkspaceError(f"{rel} is not a file")
    stat = path.stat()
    if stat.st_size > MAX_EDIT_BYTES:
        raise WorkspaceError(f"{rel} is {stat.st_size // 1024}KB — too large to edit in the browser")
    if _is_binary(path):
        return {
            "path": rel, "binary": True, "size": stat.st_size,
            "mime": mimetypes.guess_type(path.name)[0], "content": None,
            "language": _language(path.suffix.lower()),
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": rel,
        "binary": False,
        "size": stat.st_size,
        "content": text,
        "lines": text.count("\n") + 1,
        "language": _language(path.suffix.lower()) if path.name != "Dockerfile" else "dockerfile",
        "modified": stat.st_mtime,
    }


def write_file(repo_id: str, rel: str, content: str) -> dict[str, Any]:
    path = _safe_join(repo_id, rel)
    if path.is_dir():
        raise WorkspaceError(f"{rel} is a directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")
    return {"path": rel, "size": path.stat().st_size, "saved": True}


def create_entry(repo_id: str, rel: str, kind: str = "file", content: str = "") -> dict[str, Any]:
    path = _safe_join(repo_id, rel)
    if path.exists():
        raise WorkspaceError(f"{rel} already exists")
    if kind == "dir":
        path.mkdir(parents=True)
        (path / ".gitkeep").write_text("", encoding="utf-8")
        return {"path": rel, "type": "dir", "created": True}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": rel, "type": "file", "created": True}


def delete_entry(repo_id: str, rel: str) -> dict[str, Any]:
    path = _safe_join(repo_id, rel)
    if path == workspace_path(repo_id).resolve():
        raise WorkspaceError("refusing to delete the workspace root")
    if not path.exists():
        raise WorkspaceError(f"{rel} does not exist")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return {"path": rel, "deleted": True}


def rename_entry(repo_id: str, rel: str, new_rel: str) -> dict[str, Any]:
    src = _safe_join(repo_id, rel)
    dst = _safe_join(repo_id, new_rel)
    if not src.exists():
        raise WorkspaceError(f"{rel} does not exist")
    if dst.exists():
        raise WorkspaceError(f"{new_rel} already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return {"from": rel, "to": new_rel, "renamed": True}


# ------------------------------------------------------------------- git ops
_STATUS_LABELS = {
    "M": "modified", "A": "added", "D": "deleted", "R": "renamed",
    "C": "copied", "U": "conflicted", "?": "untracked", "!": "ignored",
}


def status(repo_id: str) -> dict[str, Any]:
    root = workspace_path(repo_id)
    if not (root / ".git").is_dir():
        return {"clean": True, "files": [], "cloned": False}
    result = _git(root, "status", "--porcelain=v1", "-uall", timeout=60, raw=True)
    if not result.ok:
        return {"clean": True, "files": [], "cloned": True, "error": result.output[-300:]}

    files: list[dict[str, Any]] = []
    hidden = 0
    for line in result.output.splitlines():
        if len(line) < 4:
            continue
        # XY<space><path> — columns 0 and 1 are status codes and may be spaces.
        index_st, work_st, path = line[0], line[1], line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')

        # Build artifacts are never something the user meant to commit.
        if any(part in HIDDEN_DIRS for part in Path(path).parts) or path.endswith(".pyc"):
            hidden += 1
            continue

        code = index_st if index_st != " " else work_st
        files.append({
            "path": path,
            "code": code,
            "status": _STATUS_LABELS.get(code, "changed"),
            "staged": index_st not in (" ", "?"),
        })
    return {
        "clean": not files,
        "files": files,
        "count": len(files),
        "hidden": hidden,
        "cloned": True,
    }


def diff(repo_id: str, rel: str | None = None, staged: bool = False) -> str:
    root = workspace_path(repo_id)
    args = ["diff"]
    if staged:
        args.append("--cached")
    args += ["--no-color", "--unified=3"]
    if rel:
        args += ["--", rel]
    result = _git(root, *args, timeout=60, raw=True)
    text = result.output if result.ok else ""

    if not staged:
        # Untracked files never appear in `git diff` — synthesise their patches
        # so the review pane shows everything that is about to be pushed.
        untracked = [f["path"] for f in status(repo_id)["files"] if f["code"] == "?"]
        targets = [rel] if rel else untracked
        chunks = []
        for item in targets:
            if not item or item not in untracked:
                continue
            try:
                path = _safe_join(repo_id, item)
                if path.is_dir():
                    continue
                body = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, WorkspaceError):
                continue
            lines = body.splitlines()[:600]
            chunks.append(
                f"diff --git a/{item} b/{item}\n"
                f"new file mode 100644\n--- /dev/null\n+++ b/{item}\n"
                f"@@ -0,0 +1,{len(lines)} @@\n"
                + "".join(f"+{line}\n" for line in lines)
            )
        if chunks:
            text = (text.rstrip("\n") + "\n" if text.strip() else "") + "\n".join(chunks)
    return text[:200_000]


def branch_name(prefix: str | None = None) -> str:
    return f"{prefix or PUSH_BRANCH_PREFIX}/{time.strftime('%Y%m%d-%H%M%S')}"


def commit_and_push(
    repo_id: str,
    full_name: str,
    message: str,
    token: str,
    paths: list[str] | None = None,
    strategy: str = "branch_pr",
    target_branch: str | None = None,
    base_branch: str = "main",
) -> dict[str, Any]:
    """Stage, commit and push. Returns the branch and sha that landed."""
    root = workspace_path(repo_id)
    if not (root / ".git").is_dir():
        raise WorkspaceError("workspace is not cloned")
    if not token:
        raise WorkspaceError("a GitHub token is required to push")

    state = status(repo_id)
    if state["clean"]:
        raise WorkspaceError("nothing to commit — the working tree is clean")

    if strategy == "direct":
        branch = target_branch or base_branch
        checkout = _git(root, "checkout", branch, timeout=60)
        if not checkout.ok:
            _git(root, "checkout", "-b", branch, timeout=60)
    else:
        branch = target_branch or branch_name()
        created = _git(root, "checkout", "-b", branch, timeout=60)
        if not created.ok:
            switched = _git(root, "checkout", branch, timeout=60)
            if not switched.ok:
                raise WorkspaceError(f"could not create branch {branch}: {created.output[-300:]}")

    if paths:
        for rel in paths:
            _safe_join(repo_id, rel)  # validate
            _git(root, "add", "--", rel, timeout=60)
    else:
        # Stage exactly what the UI showed as changed — `git add -A` would also
        # sweep in build artifacts the changes list deliberately hides.
        visible = [f["path"] for f in state["files"]]
        if not visible:
            raise WorkspaceError("nothing to commit — only ignored build artifacts changed")
        for rel in visible:
            _git(root, "add", "--", rel, timeout=60)

    staged = _git(root, "diff", "--cached", "--name-only", timeout=30)
    changed_files = [f for f in staged.output.splitlines() if f.strip()]
    if not changed_files:
        raise WorkspaceError("nothing staged to commit")

    committed = _git(root, "commit", "-m", message or "Update via ChaosGate", timeout=60)
    if not committed.ok and "nothing to commit" not in committed.output.lower():
        raise WorkspaceError(f"commit failed: {committed.output[-400:]}")

    sha = head_sha(repo_id, short=False)
    url = remote_url(full_name, token)
    pushed = _git(root, "push", "--set-upstream", url, f"HEAD:refs/heads/{branch}", timeout=300)
    if not pushed.ok:
        raise WorkspaceError(f"push rejected: {_redact(pushed.output, token)[-500:]}")

    return {
        "branch": branch,
        "base": base_branch,
        "sha": sha,
        "short_sha": (sha or "")[:7],
        "files": changed_files,
        "file_count": len(changed_files),
        "message": message,
        "strategy": strategy,
        "output": _redact(pushed.output, token)[-800:],
    }


def discard(repo_id: str, rel: str | None = None) -> dict[str, Any]:
    root = workspace_path(repo_id)
    if rel:
        _safe_join(repo_id, rel)
        _git(root, "checkout", "--", rel, timeout=60)
        _git(root, "clean", "-fd", "--", rel, timeout=60)
        return {"reverted": rel}
    _git(root, "reset", "--hard", timeout=60)
    _git(root, "clean", "-fd", timeout=60)
    return {"reverted": "all"}


def stats(repo_id: str) -> dict[str, Any]:
    root = workspace_path(repo_id)
    if not root.is_dir():
        return {"cloned": False}
    files = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in HIDDEN_DIRS and d != ".git"]
        for name in filenames:
            files += 1
            try:
                total += (Path(dirpath) / name).stat().st_size
            except OSError:
                pass
    return {
        "cloned": True,
        "path": str(root),
        "files": files,
        "bytes": total,
        "branch": current_branch(repo_id),
        "sha": head_sha(repo_id),
        "last_commit": last_commit(repo_id),
        "status": status(repo_id),
    }
