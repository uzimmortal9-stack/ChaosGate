"""The folder editor writes to a real git repo — path safety and git parsing
are the two things that must not be wrong."""

import subprocess
from pathlib import Path

import pytest

from core import workspace
from core.workspace import WorkspaceError


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A workspace backed by a real local git repository."""
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(workspace, "WORKSPACES_DIR", root)

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=origin, check=True)

    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True)
    (seed / "README.md").write_text("# Demo\n")
    (seed / "src").mkdir()
    (seed / "src" / "main.py").write_text("print('hello')\n")
    (seed / ".gitignore").write_text("*.log\n")
    for args in (
        ["add", "-A"],
        ["-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "init"],
        ["branch", "-M", "main"],
        ["push", "-q", "origin", "main"],
    ):
        subprocess.run(["git", *args], cwd=seed, check=True)

    repo_id = "repo_test"
    dest = root / repo_id
    subprocess.run(["git", "clone", "-q", str(origin), str(dest)], check=True)
    subprocess.run(["git", "config", "user.email", "gate@chaosgate.local"], cwd=dest, check=True)
    subprocess.run(["git", "config", "user.name", "ChaosGate"], cwd=dest, check=True)

    monkeypatch.setattr(workspace, "remote_url", lambda full, token: str(origin))
    return repo_id


def test_clone_detected(repo):
    assert workspace.is_cloned(repo)
    assert workspace.current_branch(repo) == "main"
    assert workspace.head_sha(repo)


def test_tree_lists_folders_first(repo):
    tree = workspace.tree(repo)
    names = [e["name"] for e in tree["entries"]]
    assert "src" in names and "README.md" in names
    assert tree["entries"][0]["type"] == "dir"
    assert ".git" not in names


def test_tree_navigates_into_subdirectory(repo):
    sub = workspace.tree(repo, "src")
    assert [e["name"] for e in sub["entries"]] == ["main.py"]
    assert sub["parent"] == ""


def test_read_and_write_roundtrip(repo):
    original = workspace.read_file(repo, "src/main.py")
    assert original["content"] == "print('hello')\n"
    assert original["language"] == "python"

    workspace.write_file(repo, "src/main.py", "print('changed')\n")
    assert workspace.read_file(repo, "src/main.py")["content"] == "print('changed')\n"


@pytest.mark.parametrize(
    "bad",
    ["../../../etc/passwd", "/etc/passwd", ".git/config", "src/../../escape", ".git/hooks/pre-commit"],
)
def test_path_traversal_is_blocked(repo, bad):
    with pytest.raises(WorkspaceError):
        workspace.read_file(repo, bad)
    with pytest.raises(WorkspaceError):
        workspace.write_file(repo, bad, "pwned")


def test_status_parses_porcelain_columns(repo):
    """A leading space in porcelain output is a real status code, not padding."""
    workspace.write_file(repo, "src/main.py", "print('edited')\n")
    workspace.create_entry(repo, "docs/notes.md", content="# Notes\n")

    state = workspace.status(repo)
    by_path = {f["path"]: f for f in state["files"]}

    assert "src/main.py" in by_path, f"path was truncated: {list(by_path)}"
    assert by_path["src/main.py"]["status"] == "modified"
    assert by_path["docs/notes.md"]["status"] == "untracked"
    assert state["clean"] is False


def test_tree_marks_dirty_entries(repo):
    workspace.write_file(repo, "src/main.py", "print('edited')\n")
    entries = {e["name"]: e for e in workspace.tree(repo)["entries"]}
    assert entries["src"]["dirty"] is True
    assert entries["README.md"]["dirty"] is False


def test_diff_includes_tracked_and_untracked(repo):
    workspace.write_file(repo, "README.md", "# Changed\n")
    workspace.create_entry(repo, "new.txt", content="brand new\n")
    diff = workspace.diff(repo)
    assert "# Changed" in diff
    assert "new.txt" in diff and "brand new" in diff


def test_create_and_delete(repo):
    workspace.create_entry(repo, "a/b/c.txt", content="deep\n")
    assert workspace.read_file(repo, "a/b/c.txt")["content"] == "deep\n"
    workspace.delete_entry(repo, "a/b/c.txt")
    with pytest.raises(WorkspaceError):
        workspace.read_file(repo, "a/b/c.txt")


def test_create_rejects_existing(repo):
    with pytest.raises(WorkspaceError):
        workspace.create_entry(repo, "README.md")


def test_commit_and_push_creates_branch(repo):
    workspace.write_file(repo, "README.md", "# Pushed\n")
    result = workspace.commit_and_push(repo, "o/n", "docs: update", "tok", strategy="branch_pr")

    assert result["branch"].startswith("chaosgate/")
    assert result["files"] == ["README.md"]
    assert result["sha"]
    assert workspace.status(repo)["clean"]


def test_push_only_selected_paths(repo):
    workspace.write_file(repo, "README.md", "# One\n")
    workspace.write_file(repo, "src/main.py", "print('two')\n")

    result = workspace.commit_and_push(
        repo, "o/n", "docs: readme only", "tok", paths=["README.md"], strategy="branch_pr"
    )
    assert result["files"] == ["README.md"]
    # The unselected edit stays in the working tree.
    remaining = [f["path"] for f in workspace.status(repo)["files"]]
    assert remaining == ["src/main.py"]


def test_push_refuses_clean_tree(repo):
    with pytest.raises(WorkspaceError, match="clean"):
        workspace.commit_and_push(repo, "o/n", "nothing", "tok")


def test_push_requires_token(repo):
    workspace.write_file(repo, "README.md", "# x\n")
    with pytest.raises(WorkspaceError, match="token"):
        workspace.commit_and_push(repo, "o/n", "msg", "")


def test_discard_reverts(repo):
    workspace.write_file(repo, "README.md", "# ruined\n")
    assert not workspace.status(repo)["clean"]
    workspace.discard(repo)
    assert workspace.status(repo)["clean"]
    assert workspace.read_file(repo, "README.md")["content"] == "# Demo\n"


def test_token_is_never_echoed(repo, monkeypatch):
    secret = "ghp_supersecrettoken000000000000000000"
    monkeypatch.setattr(workspace, "remote_url", lambda f, t: "https://github.com/nope/nope.git")
    workspace.write_file(repo, "README.md", "# x\n")
    with pytest.raises(WorkspaceError) as exc:
        workspace.commit_and_push(repo, "nope/nope", "msg", secret)
    assert secret not in str(exc.value)


def test_flat_tree_skips_noise(repo):
    (Path(workspace.workspace_path(repo)) / "node_modules").mkdir()
    (Path(workspace.workspace_path(repo)) / "node_modules" / "x.js").write_text("x")
    files = workspace.flat_tree(repo)
    assert "README.md" in files
    assert not any("node_modules" in f for f in files)


def test_status_hides_build_artifacts(repo):
    """A gate run must not leave .pyc files that the editor offers to commit."""
    root = workspace.workspace_path(repo)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "app.cpython-311.pyc").write_bytes(b"\x00compiled")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "dep.js").write_text("x")
    workspace.write_file(repo, "README.md", "# real change\n")

    state = workspace.status(repo)
    paths = [f["path"] for f in state["files"]]
    assert paths == ["README.md"]
    assert state["hidden"] >= 1


def test_push_ignores_build_artifacts(repo):
    root = workspace.workspace_path(repo)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    workspace.write_file(repo, "README.md", "# real\n")

    result = workspace.commit_and_push(repo, "o/n", "docs: real change", "tok")
    assert result["files"] == ["README.md"]


def test_push_refuses_when_only_artifacts_changed(repo):
    root = workspace.workspace_path(repo)
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    with pytest.raises(WorkspaceError):
        workspace.commit_and_push(repo, "o/n", "noop", "tok")


def test_pipeline_does_not_write_pycache(tmp_path):
    """PYTHONPYCACHEPREFIX must keep interpreter output out of the repo."""
    from core.pipeline_service import _run_cmd

    (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
    code, _ = _run_cmd("python -m compileall -q .", tmp_path, timeout=60)
    assert code == 0
    assert not list(tmp_path.rglob("__pycache__"))
    assert not list(tmp_path.rglob("*.pyc"))
