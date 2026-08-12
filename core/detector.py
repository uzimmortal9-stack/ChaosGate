from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_app(root: Path, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inspect a repository and infer how ChaosGate should test it."""
    root = Path(root)
    files = {p.name for p in root.iterdir()} if root.is_dir() else set()

    has_pkg = "package.json" in files
    has_req = "requirements.txt" in files or "pyproject.toml" in files or "Pipfile" in files
    has_compose = any(
        name in files for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml")
    )
    has_docker = "Dockerfile" in files
    pkg = _read_json(root / "package.json") if has_pkg else {}
    scripts = pkg.get("scripts") or {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}

    frameworks: list[str] = []
    language = None
    app_type = "unknown"
    test_command = None
    build_command = None
    start_command = None
    hints: list[str] = []

    if has_req or any((root / name).exists() for name in ("app.py", "main.py", "manage.py", "wsgi.py")):
        language = "python"
        if (root / "manage.py").exists():
            frameworks.append("django")
            app_type = "python.django"
            test_command = "python -m pytest -q"
        elif _looks_like_fastapi(root):
            frameworks.append("fastapi")
            app_type = "python.api"
            test_command = "python -m pytest -q"
        else:
            if _looks_like_flask(root):
                frameworks.append("flask")
            app_type = "python.api"
            test_command = "python -m pytest -q"
        if (root / "requirements.txt").exists():
            hints.append("Found requirements.txt")
        if (root / "pyproject.toml").exists():
            hints.append("Found pyproject.toml")

    if has_pkg:
        language = language or "javascript"
        if any(k in deps for k in ("next", "react-scripts")) or (root / "next.config.js").exists() or (
            root / "next.config.mjs"
        ).exists():
            frameworks.append("next")
            app_type = "js.react"
        elif any(k in deps for k in ("react", "react-dom")) or (root / "vite.config.js").exists() or (
            root / "vite.config.ts"
        ).exists():
            frameworks.append("react")
            app_type = "js.react"
        elif any(k in deps for k in ("express", "fastify", "koa", "hono")):
            frameworks.append("node-api")
            app_type = "js.api"
        else:
            app_type = "js.node" if app_type == "unknown" else app_type

        if "test" in scripts:
            test_command = "npm test -- --watchAll=false"
        elif (root / "tests").exists():
            test_command = test_command or "node --test tests/"
        if "build" in scripts:
            build_command = "npm run build"
        if "start" in scripts:
            start_command = "npm start"
        hints.append("Found package.json")

    if language == "python" and has_pkg:
        app_type = "fullstack"
        hints.append("Python + Node detected — treating as full-stack")

    if has_compose:
        hints.append("Docker Compose present — preferred start path")
    if has_docker:
        hints.append("Dockerfile present")

    if cfg:
        app = cfg.get("app") or {}
        tests = cfg.get("tests") or {}
        if app.get("type") and app.get("type") != "auto":
            app_type = str(app["type"])
        if tests.get("unit", {}).get("command") if isinstance(tests.get("unit"), dict) else None:
            test_command = tests["unit"]["command"]
        elif isinstance(tests.get("unit"), str):
            test_command = tests["unit"]
        if tests.get("build", {}).get("command") if isinstance(tests.get("build"), dict) else None:
            build_command = tests["build"]["command"]
        elif isinstance(tests.get("build"), str):
            build_command = tests["build"]
        if app.get("name"):
            hints.append(f"Config name: {app['name']}")

    # Prefer node --test when package.json test script would need node_modules
    if has_pkg and (root / "tests").exists() and list((root / "tests").glob("*.js")):
        if not (root / "node_modules").exists() and (
            not test_command or test_command.startswith("npm")
        ):
            test_command = "node --test tests/*.js"

    return {
        "type": app_type,
        "language": language,
        "frameworks": frameworks,
        "has_compose": has_compose,
        "has_dockerfile": has_docker,
        "has_chaosgate": bool(cfg),
        "package_manager": "npm" if has_pkg else ("pip" if has_req else None),
        "test_command": test_command,
        "build_command": build_command,
        "start_command": start_command,
        "hints": hints,
        "files": sorted(files)[:40],
    }


def _file_contains(root: Path, names: tuple[str, ...], needle: str) -> bool:
    for name in names:
        path = root / name
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if needle in text:
                return True
    return False


def _looks_like_flask(root: Path) -> bool:
    return _file_contains(root, ("app.py", "main.py", "wsgi.py", "server.py"), "Flask")


def _looks_like_fastapi(root: Path) -> bool:
    return _file_contains(root, ("app.py", "main.py", "server.py"), "FastAPI")
