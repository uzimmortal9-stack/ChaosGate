# ChaosGate

**The release gate chaos must pass.**

Connect GitHub. Pick a repository. Open its folder right here and edit it. Push, and a
thirteen-stage pipeline fires: unit tests, secret scanning, a real container build,
Kubernetes validation, k6 load testing, Prometheus metrics, a chaos experiment, and a
Grafana dashboard. Then it prints a verdict:

- **PASS** — merge allowed
- **FAIL** — `main` stays sealed, with the exact stage and reason

GitHub's green tick comes from the Commit Status API, which is empty until some
system writes to it. ChaosGate is that system: it produces the check, GitHub
enforces it. And when bad code reaches `main` anyway, ChaosGate detects it, finds
the last verified-good commit, and prepares a revert.

> Responding to a review? See **[`docs/REVIEW_RESPONSE.md`](docs/REVIEW_RESPONSE.md)**.

This repository is the **platform**. The apps in `samples/` are **targets** — applications
under test, not the product.

---

## Quick start

```bash
make install     # creates .venv and installs dependencies
make run         # http://localhost:5000
```

Open **http://localhost:5000** and click **Launch demo console**.

> Full setup walkthrough — GitHub connection, the push loop, getting stages out of
> degraded mode, troubleshooting: **[`docs/RUNNING_LOCALLY.md`](docs/RUNNING_LOCALLY.md)**

Three sample targets are already connected:

| Target | What happens |
| --- | --- |
| `atlas-shop/atlas-api` | Healthy Python API. Should **PASS**. |
| `nova-labs/nova-web` | JS storefront. Should **PASS** with a lockfile warning. |
| `mercury-pay/checkout-service` | Failing tests + a hardcoded secret. Should **FAIL**. |
| `helios-fin/legacy-billing` | Zero hardcoded secrets — but `.env` is committed and the pinned deps carry CVEs. Should **FAIL**. |

With the full observability stack:

```bash
make obs
# ChaosGate  → http://localhost:5000
# Prometheus → http://localhost:9090
# Grafana    → http://localhost:3000  (admin/admin, dashboard pre-provisioned)
```

---

## The loop

### 1 · Connect GitHub

Two paths, both supported:

- **OAuth** — set `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` in `.env` and the console
  shows a *Continue with GitHub* button. Callback URL is `${PUBLIC_URL}/api/auth/github/callback`.
- **Personal access token** — paste a token with `repo` and `workflow` scopes. Works with
  zero setup.

Either way you get a searchable list of every repository you can push to.

### 2 · Select repos and open the folder

Selecting a repository connects it. **Open folder** clones it into a private local
workspace under `data/workspaces/<repo-id>`. The console then gives you a file tree, a
text editor with tabs and dirty tracking, and file create/rename/delete.

Path handling is locked down: absolute paths, `..` traversal and anything under `.git`
are rejected before touching the filesystem.

### 3 · Push

The **Changes** tab lists exactly what differs from `HEAD`, with per-file diffs and
checkboxes so you can commit a subset. Choose a strategy:

- **Branch + pull request** *(default)* — pushes `chaosgate/<timestamp>` and opens a PR
  against the default branch.
- **Direct** — commits straight onto the default branch.

Build artifacts (`__pycache__`, `node_modules`, `*.pyc`) are filtered out of the change
list and are never staged.

### 4 · The pipeline activates

The push triggers a run immediately. Three other triggers exist:

- a **webhook** into this control plane (`push` and `pull_request` events)
- the **GitHub Actions workflow**, installable from the Automation tab
- the **Run Gate** button

When the run finishes, ChaosGate posts a commit status back to GitHub
(`ChaosGate / release-gate`) and comments a stage table on the PR. Make that status a
required check on `main` and a failing gate cannot be merged.

---

## The thirteen stages

| # | Stage | What actually runs |
| --- | --- | --- |
| 1 | **Validate** | `chaosgate.yml` parse, or autodetect from manifest files |
| 2 | **Detect** | Python / Django / FastAPI / Flask / Node / React / Compose + host capabilities |
| 3 | **Unit** | `pytest`, `node --test`, `npm test`, or the contract's command |
| 4 | **Build** | `npm run build`, `compileall`, or the contract's command |
| 5 | **Security** | Hardcoded secrets · **committed `.env`** · **secrets in git history** · **CVEs via OSV.dev** · unpinned deps |
| 6 | **Docker** | Dockerfile audit + a real `docker build`; reads back size, layers, user |
| 7 | **Kubernetes** | Manifest discovery, production-readiness audit, server-side dry-run |
| 8 | **Smoke** | Boots the target (container → Flask → static) and hits `/health` |
| 9 | **Load** | Real **k6** when installed, else a threaded in-process generator. Evaluates p95 / error-rate / availability / throughput SLOs |
| 10 | **Prometheus** | Validates the exposition format, queries the server, pushes to a Pushgateway |
| 11 | **Chaos** | Kills the process and measures recovery, per experiment |
| 12 | **Grafana** | Builds a 20-panel dashboard and publishes it if credentials exist |
| 13 | **Verdict** | Scores everything, decides PASS/FAIL, writes the report |

### Degraded is not passing, and not failing

Stages depend on tools that may not exist on the host. ChaosGate never pretends
otherwise. Each stage reports one of `passed`, `failed`, `skipped`, or **`degraded`**.

With no Docker daemon, the Docker stage still audits the Dockerfile — unpinned base
images, root user, cache-busting `COPY`, baked-in credentials — and reports
`degraded: No Docker daemon — audited only`. It does not report a build it never ran.

With no cluster, the Kubernetes stage still audits manifests (missing probes, absent
resource limits, mutable image tags, privileged containers, literal secrets in `env`)
and generates a hardened baseline for repositories that have none.

Degraded stages cost a few points and are listed explicitly in the verdict. Set
`fail_on_degraded` in Settings to make them block instead.

---

## Observability

ChaosGate exports **28 Prometheus metric families** at `/metrics` about itself and every
gate run:

```
chaosgate_pipeline_runs_total{repo,trigger,verdict}
chaosgate_stage_duration_seconds_bucket{stage,status}
chaosgate_gate_score{repo}
chaosgate_load_p95_milliseconds{repo,engine}
chaosgate_chaos_recovery_seconds{repo,experiment}
chaosgate_docker_image_size_bytes{repo}
chaosgate_toolchain_available{tool}
…
```

The Grafana dashboard is **generated from those metric names** by `core/grafana.py`, and a
test asserts every panel query references a metric the app actually emits — so the
dashboard cannot silently drift into showing "No data".

```bash
make dashboard   # regenerate docker/grafana/... and the alert rules
```

Six alert rules ship in `docker/prometheus/alerts.yml`, covering blocked merges, latency
regressions, error-rate spikes, committed secrets, degraded tooling and slow pipelines.

---

## Testing *your* app

Add a `chaosgate.yml` at the repository root — see [`docs/CHAOSGATE_YML.md`](docs/CHAOSGATE_YML.md).

```yaml
version: 1
app: {name: my-api, type: auto}
services:
  api: {url: "http://localhost:8000", health: /health}
tests:
  unit: {command: python -m pytest -q}
load:
  duration: 30s
  vus: 20
  endpoints:
    - {method: GET, path: /health}
  thresholds: {p95_ms: 800, error_rate: 0.05}
chaos:
  enabled: true
  experiments: [restart_api]
```

Without one, autodetect still works — runtime stages just have less to go on.

---

## Deployment

**Docker**

```bash
docker compose up -d --build                      # gate only
docker compose --profile observability up -d      # + Prometheus, Grafana, Pushgateway
```

The compose file mounts `/var/run/docker.sock` so the container stage can build real
images. That is a genuine privilege grant — remove the mount to force degraded mode.

**Kubernetes**

```bash
kubectl apply -f k8s/chaosgate.yaml
kubectl -n chaosgate rollout status deploy/chaosgate
```

`k8s/chaosgate.yaml` passes ChaosGate's own manifest audit with zero findings: pinned
image, liveness/readiness/startup probes, resource bounds, non-root with dropped
capabilities, an HPA and a PodDisruptionBudget. A test enforces this.

---

## Configuration

Copy `.env.example` to `.env`. Everything is optional except `SECRET_KEY` in production.

| Variable | Purpose |
| --- | --- |
| `PUBLIC_URL` | Required for OAuth callbacks and webhooks — GitHub cannot reach localhost |
| `GITHUB_CLIENT_ID` / `_SECRET` | Enables one-click OAuth |
| `GITHUB_WEBHOOK_SECRET` | Enables HMAC signature verification on inbound hooks |
| `PUSH_STRATEGY` | `branch_pr` (default) or `direct` |
| `K8S_APPLY` | `0` = dry-run only (default), `1` = really apply and await rollout |
| `PROMETHEUS_URL` / `GRAFANA_URL` | Enables live querying and dashboard publishing |
| `GATE_MAX_P95_MS` / `GATE_MAX_ERROR_RATE` | Load thresholds |

Policy is also editable in the console under **Settings**.

---

## Architecture

```
Browser ── SPA (vanilla JS, no build step)
   │
   ├── Flask control plane ── SQLite
   │        ├── core/workspace.py      clone · browse · edit · commit · push
   │        ├── core/github_client.py  OAuth · PRs · commit statuses · webhooks
   │        ├── core/pipeline_service.py   the 13-stage engine
   │        ├── core/toolchain.py      what this host can actually do
   │        └── core/metrics.py        Prometheus exposition
   │
   └── /metrics ── Prometheus ── Grafana
```

More detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
app.py                 Flask app, /metrics, request instrumentation
core/                  engine, GitHub bridge, scanners, workspace, observability
web/                   console UI (no framework, no bundler)
pipeline/              Actions workflow, k6 script, CLI helpers
docker/                Prometheus + Grafana provisioning
k8s/                   deployment manifests
samples/               target applications used in the demo
tests/                 108 tests
```

---

## Tests

```bash
make test     # 108 tests
```

Coverage worth calling out:

- **Prometheus exposition** is parsed back and validated — label escaping, cumulative
  histogram buckets, counter monotonicity.
- **Every Grafana panel query** is checked against the metrics the app actually exports.
- **The Kubernetes auditor** is run against ChaosGate's own manifests and must find nothing.
- **Path traversal** is tested against `../`, absolute paths and `.git/`.
- **Porcelain parsing** — a leading space in `git status --porcelain` is a status code, not
  padding; getting that wrong truncates filenames.
- **Degraded ≠ failed ≠ passed** is asserted directly in the verdict tests.

---

## Honest boundaries

- Single-tenant local workspace. Tokens live in SQLite — fine for a self-hosted control
  plane, not for multi-tenant SaaS.
- The container stage needs a Docker socket. Mounting it grants root-equivalent access to
  the host; only do it on a machine you control.
- `K8S_APPLY=1` really applies manifests. It defaults to off.
- Runtime stages boot what the control plane can start: containers, importable Flask apps,
  and static sites. Compose-heavy stacks should use the Actions workflow, where a runner
  provides Docker and k6.
- Pushed commits are never un-pushed. The gate blocks the *merge*, via a required status
  check — that is the only control that actually works.
