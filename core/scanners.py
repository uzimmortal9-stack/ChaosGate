from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    "data",
    ".mypy_cache",
}

TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yml",
    ".yaml",
    ".env",
    ".ini",
    ".cfg",
    ".toml",
    ".md",
    ".txt",
    ".sh",
    ".html",
    ".css",
}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub PAT", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("Stripe live secret", re.compile(r"sk_live_[A-Za-z0-9]{16,}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    (
        "Hardcoded API key",
        re.compile(r"""api[_-]?key\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]""", re.I),
    ),
    (
        "Hardcoded password",
        re.compile(r"""password\s*[:=]\s*['"][^'"]{6,}['"]""", re.I),
    ),
]

# Sample / fixture values that should not trip the scanner.
ALLOWLIST = {
    "AKIAEXAMPLEKEY0000",
    "password",
    "changeme",
}


def scan_secrets(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    root = Path(root)
    for path in _iter_text_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(lines, 1):
            if "pragma: allowlist secret" in line or "not-a-real-secret" in line:
                continue
            for title, pattern in SECRET_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                token = match.group(0)
                if any(allowed in token for allowed in ALLOWLIST):
                    continue
                findings.append(
                    {
                        "severity": "critical",
                        "category": "security",
                        "title": f"{title} committed in source",
                        "detail": f"{rel}:{lineno} matches {title}. Rotate the credential and remove it from git history.",
                        "file": rel,
                        "line": lineno,
                    }
                )
    return findings


def scan_dependencies(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    root = Path(root)
    req = root / "requirements.txt"
    if req.is_file():
        unpinned: list[str] = []
        for raw in req.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "==" not in line and "@" not in line:
                unpinned.append(line.split()[0])
        if unpinned:
            findings.append(
                {
                    "severity": "warning",
                    "category": "security",
                    "title": "Unpinned Python dependencies",
                    "detail": "These packages are not pinned to an exact version: "
                    + ", ".join(unpinned[:12]),
                    "file": "requirements.txt",
                }
            )

    pkg_path = root / "package.json"
    if pkg_path.is_file():
        lock = (root / "package-lock.json").exists() or (root / "pnpm-lock.yaml").exists() or (
            root / "yarn.lock"
        ).exists()
        if not lock:
            findings.append(
                {
                    "severity": "warning",
                    "category": "security",
                    "title": "No JavaScript lockfile",
                    "detail": "package.json is present without package-lock.json, pnpm-lock.yaml, or yarn.lock. Builds are not reproducible.",
                    "file": "package.json",
                }
            )
    return findings


def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".env":
            continue
        if path.stat().st_size > 400_000:
            continue
        yield path
