"""Supply-chain scanning.

These cover the reviewer's objection directly: hardcoded-key scanning catches
only a small fraction of real exposure. The cases that matter are a committed
.env, a secret still present in git history, and vulnerable dependencies.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core import supply_chain as sc


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    return tmp_path


def _commit(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)


# ------------------------------------------------------------- committed env
def test_committed_env_is_critical(tmp_path):
    root = _git_repo(tmp_path)
    (root / ".env").write_text(
        "DATABASE_URL=postgres://admin:Xk7bQ2mNvR@db.prod:5432/app\n"
        "SESSION_SECRET=9f8e7d6c5b4a39281706f5e4d3c2b1a0\n"
    )
    _commit(root, "oops")

    findings = sc.scan_committed_env(root)
    assert len(findings) == 1
    assert findings[0]["severity"] == "critical"
    assert findings[0]["rule"] == "committed-env"
    assert "2 assigned value" in findings[0]["detail"]
    assert "git rm --cached" in findings[0]["remediation"]


def test_env_example_is_not_flagged(tmp_path):
    """Templates are how you document required variables. They are correct."""
    root = _git_repo(tmp_path)
    (root / ".env.example").write_text("API_KEY=your-key-here\nDB_PASS=change-me\n")
    (root / ".env.sample").write_text("TOKEN=<your token>\n")
    _commit(root, "docs")
    assert sc.scan_committed_env(root) == []


def test_untracked_env_is_not_flagged(tmp_path):
    """A .env that git ignores is correct practice, not a finding."""
    root = _git_repo(tmp_path)
    (root / ".gitignore").write_text(".env\n")
    (root / ".env").write_text("SECRET=Xk7bQ2mNvR9pLwStYu\n")
    _commit(root, "ignore env")
    assert sc.scan_committed_env(root) == []


def test_private_key_committed(tmp_path):
    root = _git_repo(tmp_path)
    (root / "id_rsa").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEow==\n")
    _commit(root, "key")
    findings = sc.scan_committed_env(root)
    assert any(f["severity"] == "critical" and "id_rsa" in f["title"] for f in findings)


def test_placeholder_values_are_not_counted(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "A=your-key-here\nB=changeme\nC=<token>\nD=example-value\nE=localhost\n"
    )
    assert sc._env_has_real_values(path) == 0


def test_real_values_are_counted(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=Xk7bQ2mNvR9pLwSt\nB=9f8e7d6c5b4a39281706f5e4d3c2b1a0\n")
    assert sc._env_has_real_values(path) == 2


def test_gitignore_warning_when_env_unprotected(tmp_path):
    (tmp_path / ".env").write_text("SECRET=abc\n")
    findings = sc.check_gitignore(tmp_path)
    assert len(findings) == 1
    assert findings[0]["rule"] == "missing-gitignore-env"


def test_no_gitignore_warning_when_protected(tmp_path):
    (tmp_path / ".env").write_text("SECRET=abc\n")
    (tmp_path / ".gitignore").write_text("__pycache__/\n.env\n")
    assert sc.check_gitignore(tmp_path) == []


def test_tracked_files_are_relative_to_scan_root(tmp_path):
    """git ls-files resolves against the repo root, not the scanned folder."""
    root = _git_repo(tmp_path)
    nested = root / "services" / "api"
    nested.mkdir(parents=True)
    (nested / ".env").write_text("SECRET=Xk7bQ2mNvR9pLwSt\n")
    _commit(root, "nested env")

    tracked = sc._tracked_files(nested)
    assert tracked is not None
    assert ".env" in tracked, f"paths were not relativized: {tracked}"
    assert sc.scan_committed_env(nested)


def test_not_a_git_repo_returns_none(tmp_path):
    assert sc._tracked_files(tmp_path) is None


# --------------------------------------------------------------- git history
def test_secret_deleted_from_head_is_still_found(tmp_path):
    """The whole point: deleting a key does not remove it from the repository."""
    root = _git_repo(tmp_path)
    (root / "app.py").write_text("x = 1\n")
    _commit(root, "init")

    (root / "config.py").write_text('AWS = "AKIA3XQZM7PLKD2NVBWC"\n')
    _commit(root, "add config")

    (root / "config.py").unlink()
    _commit(root, "remove config")

    assert not (root / "config.py").exists()

    result = sc.scan_git_history(root)
    assert result["scanned"]
    assert result["commits_scanned"] == 3
    titles = [f["title"] for f in result["findings"]]
    assert any("AWS Access Key" in t for t in titles)
    assert result["findings"][0]["severity"] == "critical"
    assert result["findings"][0]["commit"]


def test_history_finds_github_pat(tmp_path):
    root = _git_repo(tmp_path)
    (root / "s.py").write_text('T = "ghp_9sKmQ2xVn4RtY7wZ1aB3cD5eF6gH8iJ0kL2m"\n')
    _commit(root, "token")
    result = sc.scan_git_history(root)
    assert any("GitHub PAT" in f["title"] for f in result["findings"])


def test_history_skips_documented_dummy_keys(tmp_path):
    """AWS publishes AKIAIOSFODNN7EXAMPLE in its own docs."""
    root = _git_repo(tmp_path)
    (root / "readme.py").write_text('EXAMPLE = "AKIAIOSFODNN7EXAMPLE"\n')
    _commit(root, "docs")
    assert sc.scan_git_history(root)["findings"] == []


def test_history_on_non_git_directory(tmp_path):
    result = sc.scan_git_history(tmp_path)
    assert result["scanned"] is False
    assert result["findings"] == []


@pytest.mark.parametrize(
    "token,dummy",
    [
        ("AKIAIOSFODNN7EXAMPLE", True),
        ("AKIAXXXXXXXXXXXXXXXX", True),
        ("sk_live_00000000000000000000", True),
        ("AKIA3XQZM7PLKD2NVBWC", False),
        ("ghp_9sKmQ2xVn4RtY7wZ1aB3cD5eF6gH8iJ0kL2m", False),
    ],
)
def test_dummy_token_detection(token, dummy):
    assert sc._is_dummy(token) is dummy


# ---------------------------------------------------------------- dependency
def test_parse_pinned_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "# comment\nFlask==0.12.2\nrequests>=2.0\nJinja2==2.10  # inline\n-e .\n\n"
    )
    pkgs = sc.parse_requirements(tmp_path)
    assert {p["name"] for p in pkgs} == {"flask", "jinja2"}
    assert all(p["ecosystem"] == "PyPI" for p in pkgs)


def test_unpinned_requirements_are_skipped():
    """Only exact pins can be checked; ranges are handled by the hygiene scan."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        Path(d, "requirements.txt").write_text("flask>=2.0\nrequests~=2.31\n")
        assert sc.parse_requirements(Path(d)) == []


def test_parse_package_lock_v3(tmp_path):
    (tmp_path / "package-lock.json").write_text(
        '{"lockfileVersion":3,"packages":{'
        '"":{"name":"root","version":"1.0.0"},'
        '"node_modules/lodash":{"version":"4.17.19"},'
        '"node_modules/minimist":{"version":"1.2.0"}}}'
    )
    pkgs = sc.parse_package_lock(tmp_path)
    names = {p["name"]: p["version"] for p in pkgs}
    assert names["lodash"] == "4.17.19"
    assert names["minimist"] == "1.2.0"
    assert all(p["ecosystem"] == "npm" for p in pkgs)


def test_parse_package_lock_v1(tmp_path):
    (tmp_path / "package-lock.json").write_text(
        '{"lockfileVersion":1,"dependencies":{"lodash":{"version":"4.17.19"}}}'
    )
    assert sc.parse_package_lock(tmp_path)[0]["name"] == "lodash"


def test_malformed_lockfile_does_not_raise(tmp_path):
    (tmp_path / "package-lock.json").write_text("{not json")
    assert sc.parse_package_lock(tmp_path) == []


# ----------------------------------------------------------- CVSS severity
@pytest.mark.parametrize(
    "score,high",
    [
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:H", True),
        ("CVSS:3.1/AV:N/AC:H/PR:H/UI:R/S:U/C:H/I:N/A:N", True),
        ("CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", False),
        # AC:L is Attack Complexity, not Availability — must not read as high.
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", False),
        ("9.8", True),
        # The "3.1" in the CVSS prefix is a spec version, not a score.
        ("3.1", False),
    ],
)
def test_cvss_severity_parsing(score, high):
    assert sc._has_high_severity([{"severity": [{"score": score}]}]) is high


def test_database_specific_severity():
    assert sc._has_high_severity([{"database_specific": {"severity": "CRITICAL"}}])
    assert not sc._has_high_severity([{"database_specific": {"severity": "LOW"}}])


# ------------------------------------------------------------------- OSV API
def _osv_response(payload):
    resp = MagicMock(status_code=200)
    resp.json.return_value = payload
    return resp


def test_osv_reports_vulnerable_packages():
    pkgs = [{"name": "flask", "version": "0.12.2", "ecosystem": "PyPI"}]
    payload = {"results": [{"vulns": [{
        "id": "GHSA-test",
        "severity": [{"score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}],
        "affected": [{"ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.2.5"}]}]}],
    }]}]}

    with patch("httpx.Client") as client:
        client.return_value.__enter__.return_value.post.return_value = _osv_response(payload)
        result = sc.query_osv(pkgs)

    assert result["available"] is True
    assert result["vulnerable"] == 1
    finding = result["findings"][0]
    assert finding["severity"] == "critical"
    assert finding["category"] == "dependency"
    assert "GHSA-test" in finding["advisories"]
    assert "2.2.5" in finding["remediation"]


def test_osv_clean_packages_produce_no_findings():
    pkgs = [{"name": "flask", "version": "3.0.3", "ecosystem": "PyPI"}]
    with patch("httpx.Client") as client:
        client.return_value.__enter__.return_value.post.return_value = _osv_response(
            {"results": [{"vulns": []}]}
        )
        result = sc.query_osv(pkgs)
    assert result["available"] is True
    assert result["vulnerable"] == 0
    assert result["findings"] == []


def test_osv_network_failure_is_degraded_not_clean():
    """A failed lookup must never be reported as 'no vulnerabilities'."""
    pkgs = [{"name": "flask", "version": "0.12.2", "ecosystem": "PyPI"}]
    with patch("httpx.Client") as client:
        client.return_value.__enter__.return_value.post.side_effect = OSError("no network")
        result = sc.query_osv(pkgs)

    assert result["available"] is False
    assert "unreachable" in result["reason"].lower()
    assert result["findings"] == []


def test_osv_http_error_is_degraded():
    with patch("httpx.Client") as client:
        resp = MagicMock(status_code=503)
        client.return_value.__enter__.return_value.post.return_value = resp
        result = sc.query_osv([{"name": "x", "version": "1.0", "ecosystem": "PyPI"}])
    assert result["available"] is False
    assert "503" in result["reason"]


def test_no_packages_is_trivially_available():
    result = sc.query_osv([])
    assert result["available"] is True
    assert result["findings"] == []


def test_scan_dependencies_cve_end_to_end(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==0.12.2\n")
    with patch("httpx.Client") as client:
        client.return_value.__enter__.return_value.post.return_value = _osv_response(
            {"results": [{"vulns": [{"id": "GHSA-x"}]}]}
        )
        result = sc.scan_dependencies_cve(tmp_path)
    assert result["available"]
    assert result["packages"] == 1
    assert result["vulnerable"] == 1
