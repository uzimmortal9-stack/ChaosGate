"""Container stage.

With a Docker daemon: lint the Dockerfile, build a real image, read back its
size and layer count, and optionally boot it.

Without one: perform a static Dockerfile audit (base image pinning, root user,
COPY . before dependency install, missing HEALTHCHECK, apt cache left behind)
and report the stage as *degraded* — never as a passing build.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from core.settings import DOCKER_BIN, DOCKER_BUILD_TIMEOUT
from core.toolchain import get as tool_get

Logger = Callable[[str], None]

COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


def find_dockerfile(root: Path) -> Path | None:
    for name in ("Dockerfile", "dockerfile", "Containerfile"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    for candidate in sorted(root.glob("*/Dockerfile")):
        return candidate
    return None


def find_compose(root: Path) -> Path | None:
    for name in COMPOSE_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def lint_dockerfile(path: Path) -> list[dict[str, Any]]:
    """Static best-practice audit. Returns findings, most severe first."""
    findings: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return [{"severity": "critical", "rule": "unreadable", "detail": str(exc)}]

    instructions = []
    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        instructions.append((lineno, stripped))

    text = "\n".join(s for _, s in instructions)
    froms = [(n, s) for n, s in instructions if s.upper().startswith("FROM ")]

    if not froms:
        findings.append(
            {"severity": "critical", "rule": "no-from", "detail": "Dockerfile has no FROM instruction."}
        )
        return findings

    for lineno, line in froms:
        image = line.split()[1]
        if ":" not in image.split("/")[-1]:
            findings.append({
                "severity": "warning", "rule": "unpinned-base", "line": lineno,
                "detail": f"Base image '{image}' has no tag — implicitly :latest, so builds are not reproducible.",
            })
        elif image.endswith(":latest"):
            findings.append({
                "severity": "warning", "rule": "latest-tag", "line": lineno,
                "detail": f"Base image '{image}' uses :latest. Pin a version or digest.",
            })

    if not re.search(r"^\s*USER\s+(?!root\b)", text, re.M | re.I):
        findings.append({
            "severity": "warning", "rule": "runs-as-root",
            "detail": "No non-root USER instruction — the container runs as root.",
        })

    if not re.search(r"^\s*HEALTHCHECK", text, re.M | re.I):
        findings.append({
            "severity": "info", "rule": "no-healthcheck",
            "detail": "No HEALTHCHECK instruction; orchestrators cannot tell when the app is ready.",
        })

    if not re.search(r"^\s*(EXPOSE|CMD|ENTRYPOINT)", text, re.M | re.I):
        findings.append({
            "severity": "warning", "rule": "no-entrypoint",
            "detail": "Neither CMD nor ENTRYPOINT is defined — the image cannot start a process.",
        })

    copy_all = next((n for n, s in instructions if re.match(r"^COPY\s+\.\s", s, re.I)), None)
    dep_install = next(
        (n for n, s in instructions if re.search(r"(pip install|npm ci|npm install|poetry install)", s, re.I)),
        None,
    )
    if copy_all and dep_install and copy_all < dep_install:
        findings.append({
            "severity": "info", "rule": "cache-busting-copy", "line": copy_all,
            "detail": "COPY . precedes dependency installation, so every source edit invalidates the dependency layer.",
        })

    if re.search(r"apt-get install", text, re.I) and "rm -rf /var/lib/apt/lists" not in text:
        findings.append({
            "severity": "info", "rule": "apt-cache",
            "detail": "apt-get install without cleaning /var/lib/apt/lists — the image carries dead weight.",
        })

    if re.search(r"^\s*ADD\s+http", text, re.M | re.I):
        findings.append({
            "severity": "warning", "rule": "add-remote",
            "detail": "ADD with a remote URL bypasses checksum verification. Prefer RUN curl with a hash check.",
        })

    if re.search(r"(ENV|ARG)\s+\w*(PASSWORD|SECRET|TOKEN|API_KEY)\w*\s*=\s*\S+", text, re.I):
        findings.append({
            "severity": "critical", "rule": "baked-secret",
            "detail": "A credential-looking ENV/ARG has a default value baked into the image.",
        })

    stages = len(froms)
    if stages == 1 and re.search(r"(npm run build|pip install|go build|mvn package)", text, re.I):
        findings.append({
            "severity": "info", "rule": "single-stage",
            "detail": "Single-stage build ships toolchain and build artifacts together. Consider a multi-stage build.",
        })

    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return findings


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except FileNotFoundError:
        return 127, "docker binary not found"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def build_image(root: Path, tag: str, dockerfile: Path, log: Logger, timeout: int | None = None) -> dict[str, Any]:
    """Run a real `docker build` and collect image facts."""
    timeout = timeout or DOCKER_BUILD_TIMEOUT
    cmd = [DOCKER_BIN, "build", "-t", tag, "-f", str(dockerfile), "."]
    log(f"$ docker build -t {tag} -f {dockerfile.name} .")
    started = time.perf_counter()
    code, out = _run(cmd, cwd=root, timeout=timeout)
    elapsed = time.perf_counter() - started

    tail = out.splitlines()
    for line in tail[-45:]:
        if line.strip():
            log(line.rstrip())

    result: dict[str, Any] = {
        "built": code == 0,
        "tag": tag,
        "exit_code": code,
        "duration_s": round(elapsed, 2),
        "dockerfile": dockerfile.name,
    }
    if code != 0:
        result["error"] = "\n".join(tail[-8:])[:800] or "docker build failed"
        return result

    icode, iout = _run(
        [DOCKER_BIN, "image", "inspect", tag, "--format",
         "{{.Size}}|{{.Os}}/{{.Architecture}}|{{len .RootFS.Layers}}|{{.Config.User}}"],
        timeout=30,
    )
    if icode == 0 and "|" in iout:
        size, platform, layers, user = (iout.strip().split("|") + ["", "", "", ""])[:4]
        try:
            result["size_bytes"] = int(size)
            result["size_mb"] = round(int(size) / (1024 * 1024), 1)
        except ValueError:
            pass
        result["platform"] = platform
        result["layers"] = int(layers) if layers.isdigit() else None
        result["user"] = user or "root"
        log(f"image {tag}: {result.get('size_mb', '?')} MB · {result.get('layers', '?')} layers · user={result['user']}")
    return result


def run_container(tag: str, port: int, container_port: int, log: Logger, env: dict[str, str] | None = None) -> dict[str, Any]:
    name = f"chaosgate-{tag.replace('/', '-').replace(':', '-')}-{int(time.time())}"
    cmd = [DOCKER_BIN, "run", "-d", "--rm", "--name", name, "-p", f"{port}:{container_port}"]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd.append(tag)
    log(f"$ docker run -d -p {port}:{container_port} {tag}")
    code, out = _run(cmd, timeout=90)
    if code != 0:
        log(f"container failed to start: {out[:300]}")
        return {"running": False, "error": out[:400]}
    return {"running": True, "name": name, "container_id": out.strip()[:12], "port": port}


def stop_container(name: str) -> None:
    _run([DOCKER_BIN, "rm", "-f", name], timeout=45)


def container_logs(name: str, lines: int = 50) -> str:
    _, out = _run([DOCKER_BIN, "logs", "--tail", str(lines), name], timeout=20)
    return out


def compose_config(compose_file: Path, log: Logger) -> dict[str, Any]:
    """Validate a compose file. Uses the CLI when available, YAML parsing otherwise."""
    docker = tool_get("docker")
    if docker.get("available") and (docker.get("extra") or {}).get("compose"):
        code, out = _run(
            [DOCKER_BIN, "compose", "-f", str(compose_file), "config", "--format", "json"],
            cwd=compose_file.parent, timeout=60,
        )
        if code == 0:
            try:
                doc = json.loads(out)
                services = list((doc.get("services") or {}).keys())
                log(f"docker compose config OK — services: {', '.join(services) or 'none'}")
                return {"valid": True, "services": services, "engine": "docker-compose", "raw": doc}
            except json.JSONDecodeError:
                pass
        else:
            log(f"docker compose config rejected the file: {out.splitlines()[-1][:200] if out else ''}")
            return {"valid": False, "error": out[-500:], "engine": "docker-compose"}

    try:
        import yaml

        doc = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "error": f"unparseable compose file: {exc}", "engine": "yaml"}

    if not isinstance(doc, dict):
        return {"valid": False, "error": "compose file is not a mapping", "engine": "yaml"}
    services = list((doc.get("services") or {}).keys())
    issues = []
    for name, svc in (doc.get("services") or {}).items():
        if not isinstance(svc, dict):
            issues.append(f"service '{name}' is not a mapping")
            continue
        if not svc.get("image") and not svc.get("build"):
            issues.append(f"service '{name}' has neither image nor build")
    log(f"compose parsed statically — services: {', '.join(services) or 'none'}")
    return {
        "valid": not issues,
        "services": services,
        "issues": issues,
        "engine": "yaml",
        "degraded": True,
    }
