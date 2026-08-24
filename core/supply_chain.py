"""Supply-chain and secret-hygiene scanning.

Answers the reviewer's objection that hardcoded-key scanning only catches the
5-10% of cases where a developer pasted a credential into source. The other
90% are:

* ``.env`` committed to the repository (the file everyone assumes is ignored)
* a secret that was removed from HEAD but is still in git history forever
* a vulnerable dependency version — by far the most common real-world breach
  vector, and something no amount of code review catches
* a missing ``.gitignore`` rule, which is the root cause of the first item

CVE lookups use the OSV.dev API (free, no key, covers PyPI/npm/Go/Maven/etc).
When the network is unavailable the stage degrades honestly rather than
reporting a clean bill of health it did not earn.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

OSV_API = "https://api.osv.dev/v1/querybatch"
OSV_SINGLE = "https://api.osv.dev/v1/query"

# Files that must never be committed. Ordered most-dangerous first.
FORBIDDEN_FILES: list[tuple[str, str, str]] = [
    (".env", "critical", "Real environment file with live credentials"),
    (".env.local", "critical", "Local environment overrides"),
    (".env.production", "critical", "Production environment file"),
    (".env.prod", "critical", "Production environment file"),
    (".env.staging", "critical", "Staging environment file"),
    ("secrets.json", "critical", "Secret store"),
    ("credentials.json", "critical", "Cloud service-account credentials"),
    ("serviceaccount.json", "critical", "GCP service-account key"),
    ("id_rsa", "critical", "Private SSH key"),
    ("id_ed25519", "critical", "Private SSH key"),
    (".npmrc", "warning", "May contain an npm auth token"),
    (".pypirc", "warning", "May contain PyPI upload credentials"),
    ("terraform.tfstate", "warning", "Terraform state often embeds secrets"),
    (".htpasswd", "warning", "Password digest file"),
]

# Templates are fine — they are how you document required variables.
SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".dist", ".defaults")

SECRET_HISTORY_PATTERNS = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub PAT", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("Stripe live key", re.compile(r"sk_live_[A-Za-z0-9]{16,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]

PLACEHOLDER = re.compile(
    r"(example|sample|dummy|placeholder|your[_-]?|xxx+|changeme|<[^>]+>|test[_-]?key|fake)",
    re.I,
)

# Credentials that vendors publish in their own documentation. These are the
# only tokens safe to suppress by exact match — a substring rule like
# "contains the word example" would also hide a live key that happens to sit
# in a file named example.py.
KNOWN_DUMMY_TOKENS = {
    "AKIAIOSFODNN7EXAMPLE",           # AWS docs
    "AKIAEXAMPLEKEY00000",
    "sk_live_00000000000000000000",
    "AIzaSyDUMMYKEY0000000000000000000000000",
}


def _is_dummy(token: str) -> bool:
    """True when a matched token is a documented placeholder, not a credential."""
    if token in KNOWN_DUMMY_TOKENS:
        return True
    # Obvious filler: a long run of one repeated character, or all zeros.
    body = re.sub(r"^(AKIA|ghp_|sk_live_|AIza|xox[baprs]-)", "", token)
    if len(set(body)) <= 2:
        return True
    return bool(re.fullmatch(r"(?i)(x+|0+|1+|a+)", body))


# ---------------------------------------------------------------- env hygiene
def scan_committed_env(root: Path) -> list[dict[str, Any]]:
    """Find credential files that are tracked by git.

    This is the finding the reviewer's objection actually implies: if secrets
    live in .env, then .env being committed is the whole breach.
    """
    root = Path(root)
    findings: list[dict[str, Any]] = []
    tracked = _tracked_files(root)

    for name, severity, why in FORBIDDEN_FILES:
        for candidate in root.rglob(name):
            if ".git" in candidate.parts or "node_modules" in candidate.parts:
                continue
            rel = str(candidate.relative_to(root)).replace("\\", "/")
            if rel.endswith(SAFE_ENV_SUFFIXES):
                continue

            # A file only matters if git is actually tracking it.
            is_tracked = tracked is None or rel in tracked
            if not is_tracked:
                continue

            detail = f"{why}. `{rel}` is committed to the repository."
            populated = _env_has_real_values(candidate)
            if populated:
                detail += f" It contains {populated} assigned value(s)."

            findings.append({
                "severity": severity,
                "category": "security",
                "title": f"Credential file committed: {rel}",
                "detail": detail
                + " Remove it with `git rm --cached`, add it to .gitignore, and rotate every"
                  " credential it contained — it is in git history permanently.",
                "file": rel,
                "rule": "committed-env",
                "remediation": f"git rm --cached {rel} && echo '{rel}' >> .gitignore",
            })
    return findings


def _env_has_real_values(path: Path) -> int:
    """Count assignments that look like real values rather than placeholders."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    count = 0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        _, _, value = line.partition("=")
        value = value.strip().strip("\"'")
        if len(value) < 8:
            continue
        if PLACEHOLDER.search(value):
            continue
        # Documentation values are words joined by separators ("change-me",
        # "localhost:5432/billing"). A real credential carries entropy: mixed
        # case with digits, or a long unbroken token.
        stripped = re.sub(r"[^A-Za-z0-9]", "", value)
        if not stripped:
            continue
        has_mixed_case = stripped != stripped.lower() and stripped != stripped.upper()
        has_digit = any(c.isdigit() for c in stripped)
        longest_token = max((len(t) for t in re.split(r"[^A-Za-z0-9]", value)), default=0)
        if (has_mixed_case and has_digit) or longest_token >= 20:
            count += 1
    return count


def check_gitignore(root: Path) -> list[dict[str, Any]]:
    """A repo with .env but no ignore rule is one `git add -A` from disaster."""
    root = Path(root)
    gitignore = root / ".gitignore"
    has_env_file = any(
        (root / n).exists() for n in (".env", ".env.local", ".env.production")
    )
    if not has_env_file:
        return []

    patterns = ""
    if gitignore.is_file():
        patterns = gitignore.read_text(encoding="utf-8", errors="ignore")

    if re.search(r"^\s*\.env", patterns, re.M):
        return []

    return [{
        "severity": "warning",
        "category": "security",
        "title": "No .gitignore rule for .env",
        "detail": "This repository contains a .env file but .gitignore does not exclude it. "
                  "A single `git add -A` will commit live credentials.",
        "file": ".gitignore",
        "rule": "missing-gitignore-env",
        "remediation": "printf '.env\\n.env.local\\n.env.*.local\\n' >> .gitignore",
    }]


def _tracked_files(root: Path) -> set[str] | None:
    """Files git tracks, relative to `root`.

    `git ls-files` resolves against the repository root, which is not always
    the directory being scanned — a sample living inside a larger repo would
    otherwise never match. Passing an explicit pathspec keeps the results
    relative to `root`.

    Returns None when `root` is not inside a git repository, which the caller
    treats as "cannot verify tracking" rather than "nothing is tracked".
    """
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--", "."],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        return {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------- git history
def scan_git_history(root: Path, max_commits: int = 300) -> dict[str, Any]:
    """Search past commits for secrets that were 'removed' from HEAD.

    Deleting a key in a later commit does not remove it from the repository.
    Anyone who clones can still read it.
    """
    root = Path(root)
    if not (root / ".git").is_dir():
        return {"scanned": False, "reason": "not a git repository", "findings": []}

    total_commits = _count_commits(root)
    try:
        # --diff-filter=AM: only additions/modifications introduce a secret;
        # a deletion commit cannot. The total commit count is taken separately
        # so the report says how much history exists, not how much had diffs.
        proc = subprocess.run(
            ["git", "log", f"-{max_commits}", "--all", "-p", "--no-color",
             "--diff-filter=AM", "--", "."],
            cwd=root, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"scanned": False, "reason": "history scan timed out", "findings": []}
    except Exception as exc:  # noqa: BLE001
        return {"scanned": False, "reason": str(exc), "findings": []}

    if proc.returncode != 0:
        return {"scanned": False, "reason": "git log failed", "findings": []}

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    commit = ""
    subject = ""
    current_file = ""
    commits_seen = 0

    for line in proc.stdout.splitlines():
        if line.startswith("commit "):
            commit = line.split()[1][:8]
            commits_seen += 1
            continue
        if line.startswith("    ") and not subject:
            subject = line.strip()[:60]
            continue
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            subject = ""
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue

        for title, pattern in SECRET_HISTORY_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            token = match.group(0)
            if _is_dummy(token):
                continue
            key = (title, token[:24])
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "severity": "critical",
                "category": "security",
                "title": f"{title} found in git history",
                "detail": f"Commit {commit} added a {title} in `{current_file or 'unknown file'}`. "
                          "Even if it was deleted later, it remains readable to anyone who clones "
                          "this repository. Rotate the credential now.",
                "file": current_file or None,
                "commit": commit,
                "rule": "secret-in-history",
                "remediation": "Rotate the credential, then purge with git-filter-repo or BFG.",
            })

    return {
        "scanned": True,
        "commits_scanned": total_commits or commits_seen,
        "commits_with_diffs": commits_seen,
        "findings": findings[:40],
    }


def _count_commits(root: Path) -> int:
    try:
        proc = subprocess.run(
            ["git", "rev-list", "--all", "--count"],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        return int(proc.stdout.strip()) if proc.returncode == 0 else 0
    except Exception:  # noqa: BLE001
        return 0


# ------------------------------------------------------------- dependency CVE
def parse_requirements(root: Path) -> list[dict[str, str]]:
    """Pinned Python dependencies. Only exact pins can be checked against CVEs."""
    path = root / "requirements.txt"
    if not path.is_file():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9._-]+)\s*==\s*([0-9][^\s;,]*)", line)
        if match:
            out.append({"name": match.group(1).lower(), "version": match.group(2),
                        "ecosystem": "PyPI"})
    return out


def parse_package_lock(root: Path, limit: int = 250) -> list[dict[str, str]]:
    """Resolved npm dependencies from the lockfile."""
    path = root / "package-lock.json"
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return []

    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, version: str) -> None:
        if not name or not version or not re.match(r"^\d", version):
            return
        key = (name, version)
        if key in seen:
            return
        seen.add(key)
        out.append({"name": name, "version": version, "ecosystem": "npm"})

    # lockfileVersion 2/3
    for pkg_path, meta in (doc.get("packages") or {}).items():
        if not pkg_path or not isinstance(meta, dict):
            continue
        name = pkg_path.split("node_modules/")[-1]
        add(name, str(meta.get("version") or ""))
    # lockfileVersion 1
    for name, meta in (doc.get("dependencies") or {}).items():
        if isinstance(meta, dict):
            add(name, str(meta.get("version") or ""))

    return out[:limit]


def query_osv(packages: list[dict[str, str]], timeout: float = 25.0) -> dict[str, Any]:
    """Batch-query OSV.dev for known vulnerabilities.

    Returns a result dict; never raises. `available: False` means the lookup
    could not run, which the caller must surface as degraded — not as clean.
    """
    if not packages:
        return {"available": True, "queried": 0, "findings": [], "vulnerable": 0}

    queries = [
        {"package": {"name": p["name"], "ecosystem": p["ecosystem"]}, "version": p["version"]}
        for p in packages
    ]

    try:
        with httpx.Client(timeout=timeout) as client:
            res = client.post(OSV_API, json={"queries": queries})
            if res.status_code != 200:
                return {"available": False,
                        "reason": f"OSV returned HTTP {res.status_code}",
                        "findings": []}
            results = (res.json() or {}).get("results") or []
    except Exception as exc:  # noqa: BLE001
        return {"available": False,
                "reason": f"OSV unreachable: {type(exc).__name__}",
                "findings": []}

    findings: list[dict[str, Any]] = []
    vulnerable = 0

    for pkg, result in zip(packages, results):
        vulns = (result or {}).get("vulns") or []
        if not vulns:
            continue
        vulnerable += 1
        ids = [v.get("id") for v in vulns if v.get("id")]
        severity = "critical" if _has_high_severity(vulns) else "warning"
        findings.append({
            "severity": severity,
            "category": "dependency",
            "title": f"{pkg['name']} {pkg['version']} has {len(vulns)} known vulnerability(ies)",
            "detail": "Advisories: " + ", ".join(ids[:6])
                      + (f" (+{len(ids) - 6} more)" if len(ids) > 6 else "")
                      + ". Source: OSV.dev.",
            "file": "requirements.txt" if pkg["ecosystem"] == "PyPI" else "package-lock.json",
            "package": pkg["name"],
            "version": pkg["version"],
            "ecosystem": pkg["ecosystem"],
            "advisories": ids[:10],
            "rule": "vulnerable-dependency",
            "remediation": _fix_hint(pkg, vulns),
        })

    findings.sort(key=lambda f: 0 if f["severity"] == "critical" else 1)
    return {
        "available": True,
        "queried": len(packages),
        "vulnerable": vulnerable,
        "findings": findings,
    }


def _has_high_severity(vulns: list[dict[str, Any]]) -> bool:
    """True when any advisory is High/Critical.

    OSV reports severity either as a CVSS vector string or a bare numeric
    score. Both need care: the "CVSS:3.1" prefix is a *specification version*,
    not a score, and a naive number match reads it as 3.1 and downgrades a
    critical finding to a warning.
    """
    for vuln in vulns:
        for sev in vuln.get("severity") or []:
            score = str(sev.get("score") or "").strip()
            if not score:
                continue

            if score.upper().startswith("CVSS:"):
                # Impact metrics: Confidentiality / Integrity / Availability.
                # Anchor on the '/' so AC (Attack Complexity) is not mistaken
                # for A (Availability).
                impacts = re.findall(r"/([CIA]):([NLH])", score)
                if any(value == "H" for _, value in impacts):
                    return True
                continue

            try:
                if float(score) >= 7.0:
                    return True
            except ValueError:
                pass

        db = (vuln.get("database_specific") or {}).get("severity")
        if str(db).upper() in ("HIGH", "CRITICAL"):
            return True
    return False


def _fix_hint(pkg: dict[str, str], vulns: list[dict[str, Any]]) -> str:
    fixed: list[str] = []
    for vuln in vulns:
        for affected in vuln.get("affected") or []:
            for rng in affected.get("ranges") or []:
                for event in rng.get("events") or []:
                    if event.get("fixed"):
                        fixed.append(event["fixed"])
    if fixed:
        newest = sorted(set(fixed))[-1]
        if pkg["ecosystem"] == "PyPI":
            return f"Upgrade to {pkg['name']}=={newest} or later."
        return f"Upgrade to {pkg['name']}@{newest} or later."
    return f"No fixed version published yet — evaluate whether {pkg['name']} is still needed."


def scan_dependencies_cve(root: Path) -> dict[str, Any]:
    """Full dependency vulnerability scan for a repository."""
    root = Path(root)
    packages = parse_requirements(root) + parse_package_lock(root)
    if not packages:
        return {"available": True, "queried": 0, "findings": [], "vulnerable": 0,
                "note": "no pinned dependencies to check"}
    result = query_osv(packages)
    result["packages"] = len(packages)
    return result
