"""Kubernetes stage.

Discovers manifests, audits them against production-readiness rules, and —
when a cluster is actually reachable — runs `kubectl apply --dry-run=server`
(or a real apply plus rollout wait when K8S_APPLY=1).

With no cluster the audit still runs and the stage is reported as *degraded*.
ChaosGate also synthesises a Deployment/Service/HPA set for repositories that
have no manifests of their own, so the generated YAML can be downloaded.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from core.settings import K8S_APPLY, K8S_NAMESPACE, KUBECTL_BIN
from core.toolchain import get as tool_get

Logger = Callable[[str], None]

MANIFEST_DIRS = ("k8s", "kubernetes", "deploy", "manifests", "charts", ".k8s", "infra")
WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet", "Pod"}


def _run(cmd: list[str], timeout: int = 60, stdin: str | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, input=stdin
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except FileNotFoundError:
        return 127, "kubectl not found"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def discover_manifests(root: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()

    def consider(path: Path) -> None:
        if path in seen or not path.is_file():
            return
        if path.stat().st_size > 512_000:
            return
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        except OSError:
            return
        if re.search(r"^\s*apiVersion\s*:", head, re.M) and re.search(r"^\s*kind\s*:", head, re.M):
            seen.add(path)
            found.append(path)

    for dirname in MANIFEST_DIRS:
        directory = root / dirname
        if directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if path.suffix.lower() in {".yaml", ".yml"}:
                    consider(path)

    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        if path.name in {"chaosgate.yml", "chaosgate.yaml", "docker-compose.yml", "docker-compose.yaml"}:
            continue
        consider(path)

    return found[:60]


def load_documents(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    import yaml

    docs: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in paths:
        try:
            for doc in yaml.safe_load_all(path.read_text(encoding="utf-8", errors="ignore")):
                if isinstance(doc, dict) and doc.get("kind"):
                    doc["__source__"] = path.name
                    docs.append(doc)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: {exc}")
    return docs, errors


def _pod_spec(doc: dict[str, Any]) -> dict[str, Any]:
    spec = doc.get("spec") or {}
    if doc.get("kind") == "Pod":
        return spec
    if doc.get("kind") == "CronJob":
        return (
            ((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {}
        ).get("spec") or {}
    return (spec.get("template") or {}).get("spec") or {}


def _containers(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return list(_pod_spec(doc).get("containers") or [])


def audit(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Production-readiness rules for Kubernetes workloads."""
    findings: list[dict[str, Any]] = []

    def add(sev: str, rule: str, detail: str, source: str | None = None) -> None:
        findings.append({"severity": sev, "rule": rule, "detail": detail, "source": source})

    kinds = [d.get("kind") for d in docs]
    workloads = [d for d in docs if d.get("kind") in WORKLOAD_KINDS]

    for doc in workloads:
        kind = doc.get("kind")
        name = ((doc.get("metadata") or {}).get("name")) or "<unnamed>"
        src = doc.get("__source__")
        label = f"{kind}/{name}"
        spec = doc.get("spec") or {}

        if kind in {"Deployment", "StatefulSet"} and not spec.get("replicas"):
            add("info", "single-replica", f"{label} does not set replicas — defaults to 1, so no redundancy.", src)
        elif kind in {"Deployment", "StatefulSet"} and int(spec.get("replicas") or 1) < 2:
            add("info", "single-replica", f"{label} runs a single replica; a node drain causes downtime.", src)

        containers = _containers(doc)
        if not containers:
            add("critical", "no-containers", f"{label} defines no containers.", src)
            continue

        # Pod-level securityContext is inherited by every container in the pod.
        pod_sc = _pod_spec(doc).get("securityContext") or {}

        for c in containers:
            cname = c.get("name") or "<unnamed>"
            ref = f"{label}[{cname}]"
            image = str(c.get("image") or "")
            if not image:
                add("critical", "no-image", f"{ref} has no image.", src)
            elif ":" not in image.split("/")[-1] or image.endswith(":latest"):
                add("warning", "mutable-image", f"{ref} uses a mutable image tag '{image}'. Pin a digest or version.", src)

            resources = c.get("resources") or {}
            if not resources.get("limits"):
                add("warning", "no-limits", f"{ref} sets no resource limits — one pod can starve the node.", src)
            if not resources.get("requests"):
                add("warning", "no-requests", f"{ref} sets no resource requests — the scheduler is guessing.", src)

            if not c.get("livenessProbe"):
                add("warning", "no-liveness", f"{ref} has no livenessProbe; a hung process is never restarted.", src)
            if not c.get("readinessProbe"):
                add("warning", "no-readiness", f"{ref} has no readinessProbe; traffic reaches it before it is ready.", src)

            sc = c.get("securityContext") or {}
            if sc.get("privileged"):
                add("critical", "privileged", f"{ref} runs privileged.", src)
            # Container setting wins; otherwise the pod-level value applies.
            non_root = sc.get("runAsNonRoot")
            if non_root is None:
                non_root = pod_sc.get("runAsNonRoot")
            run_as_user = sc.get("runAsUser", pod_sc.get("runAsUser"))
            if non_root is not True and run_as_user in (None, 0):
                add("info", "may-run-root", f"{ref} does not set runAsNonRoot: true.", src)
            if sc.get("allowPrivilegeEscalation") is not False:
                add("info", "priv-escalation", f"{ref} does not disable privilege escalation.", src)

            for env in c.get("env") or []:
                if not isinstance(env, dict):
                    continue
                key = str(env.get("name") or "")
                val = env.get("value")
                if val and re.search(r"(PASSWORD|SECRET|TOKEN|API_?KEY)", key, re.I):
                    add("critical", "inline-secret", f"{ref} sets {key} as a literal value. Use a Secret reference.", src)

    if workloads and "Service" not in kinds:
        add("info", "no-service", "Workloads are defined but no Service exposes them.")
    if any(k == "Deployment" for k in kinds) and "HorizontalPodAutoscaler" not in kinds:
        add("info", "no-hpa", "No HorizontalPodAutoscaler — the deployment cannot absorb a traffic spike.")
    if workloads and "PodDisruptionBudget" not in kinds:
        add("info", "no-pdb", "No PodDisruptionBudget — voluntary evictions can take the service down.")

    order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))
    return findings


def dry_run(paths: list[Path], namespace: str, log: Logger, server_side: bool = True) -> dict[str, Any]:
    """Validate manifests against a live API server."""
    mode = "server" if server_side else "client"
    results: list[dict[str, Any]] = []
    ok = True
    for path in paths:
        cmd = [
            KUBECTL_BIN, "apply", "-f", str(path),
            f"--dry-run={mode}", "-n", namespace, "-o", "name",
        ]
        code, out = _run(cmd, timeout=60)
        entry = {"file": path.name, "ok": code == 0, "output": out[-600:]}
        results.append(entry)
        if code == 0:
            for line in out.splitlines():
                if line.strip():
                    log(f"  ✓ {line.strip()} ({mode} dry-run)")
        else:
            ok = False
            log(f"  ✗ {path.name}: {out.splitlines()[-1][:200] if out else 'rejected'}")
    return {"ok": ok, "mode": f"{mode}-dry-run", "results": results}


def apply(paths: list[Path], namespace: str, log: Logger) -> dict[str, Any]:
    _run([KUBECTL_BIN, "create", "namespace", namespace], timeout=30)
    applied: list[str] = []
    ok = True
    for path in paths:
        code, out = _run([KUBECTL_BIN, "apply", "-f", str(path), "-n", namespace, "-o", "name"], timeout=120)
        for line in out.splitlines():
            if line.strip():
                log(f"  {line.strip()}")
                if code == 0:
                    applied.append(line.strip())
        if code != 0:
            ok = False
    return {"ok": ok, "applied": applied, "namespace": namespace}


def rollout_status(resources: list[str], namespace: str, log: Logger, timeout_s: int = 120) -> dict[str, Any]:
    statuses = []
    healthy = True
    for ref in resources:
        if not ref.startswith(("deployment", "statefulset", "daemonset")):
            continue
        code, out = _run(
            [KUBECTL_BIN, "rollout", "status", ref, "-n", namespace, f"--timeout={timeout_s}s"],
            timeout=timeout_s + 20,
        )
        log(f"  {out.splitlines()[-1][:200] if out else ref}")
        statuses.append({"resource": ref, "ok": code == 0, "output": out[-300:]})
        if code != 0:
            healthy = False
    return {"ok": healthy, "statuses": statuses}


def cluster_snapshot(namespace: str) -> dict[str, Any]:
    code, out = _run(
        [KUBECTL_BIN, "get", "pods", "-n", namespace, "-o", "json", "--request-timeout=8s"], timeout=20
    )
    if code != 0:
        return {"available": False}
    try:
        doc = json.loads(out)
    except json.JSONDecodeError:
        return {"available": False}
    pods = []
    for item in doc.get("items") or []:
        status = item.get("status") or {}
        restarts = sum(
            (cs.get("restartCount") or 0) for cs in (status.get("containerStatuses") or [])
        )
        pods.append({
            "name": (item.get("metadata") or {}).get("name"),
            "phase": status.get("phase"),
            "restarts": restarts,
            "ready": all(cs.get("ready") for cs in (status.get("containerStatuses") or [])) or False,
        })
    return {"available": True, "namespace": namespace, "pods": pods, "count": len(pods)}


def generate_manifests(app_name: str, image: str, port: int = 8000, replicas: int = 2, namespace: str = K8S_NAMESPACE) -> str:
    """Produce a hardened baseline manifest set for a repo that has none."""
    safe = re.sub(r"[^a-z0-9-]", "-", app_name.lower()).strip("-") or "app"
    return f"""# Generated by ChaosGate for {app_name}.
# Hardened baseline: probes, resource bounds, non-root, HPA and a PDB.
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {safe}
  namespace: {namespace}
  labels:
    app.kubernetes.io/name: {safe}
    app.kubernetes.io/managed-by: chaosgate
spec:
  replicas: {replicas}
  revisionHistoryLimit: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {safe}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {safe}
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "{port}"
        prometheus.io/path: /metrics
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: {safe}
          image: {image}
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: {port}
          env:
            - name: PORT
              value: "{port}"
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 15
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 3
            periodSeconds: 5
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {{}}
---
apiVersion: v1
kind: Service
metadata:
  name: {safe}
  namespace: {namespace}
  labels:
    app.kubernetes.io/name: {safe}
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: {safe}
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {safe}
  namespace: {namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {safe}
  minReplicas: {replicas}
  maxReplicas: {max(replicas * 5, 10)}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {safe}
  namespace: {namespace}
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {safe}
"""


def should_apply() -> bool:
    return K8S_APPLY and tool_get("kubectl").get("available", False)
