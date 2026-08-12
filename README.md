# ChaosGate

**The release gate chaos must pass.**

ChaosGate is a DevOps control plane. A developer connects a real Python, JavaScript, or React repository. The gate pulls the code, detects the stack, runs unit tests, builds, scans for secrets and sloppy dependencies, boots the app, hits it with traffic, and optionally kills a process to see if it comes back. Then it prints a verdict:

- **PASS** — merge is allowed
- **FAIL** — `main` stays sealed, with the exact stage and reason

This repository is the **platform**. The Flask/Node apps in `samples/` are **targets** — applications under test, not the product.

Pushed git commits are not un-pushed. The correct control is a pull request plus a required status check. ChaosGate is that check.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open [http://localhost:5000](http://localhost:5000) and click **Launch demo console**.

Three sample targets are already connected:

| Target | What happens |
| --- | --- |
| `atlas-shop/atlas-api` | Healthy Python API. Should **PASS**. |
| `nova-labs/nova-web` | JS storefront. Should **PASS** with a lockfile warning. |
| `mercury-pay/checkout-service` | Failing tests + committed secrets. Should **FAIL** and block. |

## What the gate runs

1. **Validate** — `chaosgate.yml`, Dockerfile, package manifest
2. **Detect** — Python / Django / FastAPI / Flask / Node / React / Compose
3. **Unit** — `pytest`, `node --test`, or the command in the contract
4. **Build** — `compileall`, `npm run build`, or Dockerfile sanity
5. **Security** — committed secrets, unpinned deps, missing lockfile
6. **Smoke** — boot the target, hit `/health`
7. **Load** — in-process traffic generator (k6-compatible script shipped for Actions)
8. **Chaos** — kill and restart, measure recovery
9. **Verdict** — score, reasons, merge block

## Testing *your* app

Add a `chaosgate.yml` at the repo root. The contract is documented in [`docs/CHAOSGATE_YML.md`](docs/CHAOSGATE_YML.md).

In the console: **Connect →** paste `owner/name` or a GitHub token, then **Run Gate**.

Public repos are cloned shallowly. Private repos need a PAT with `repo` scope.

To block GitHub merges, copy [`pipeline/workflows/chaosgate.yml`](pipeline/workflows/chaosgate.yml) to `.github/workflows/chaosgate.yml` in the target repository and require the ChaosGate check on `main`.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
User → Web UI → Flask API → SQLite
                         ↘ GitHub API
                         ↘ Local gate engine → sample or cloned target
```

## Project layout

```
app.py                 # Flask control plane
core/                  # GitHub client, detector, scanners, pipeline, verdict
web/                   # Console UI
pipeline/              # Actions workflow, k6 script, CLI helpers
samples/               # Target applications used in the demo
docs/                  # Contract and architecture
```

## Configuration

Copy `.env.example` to `.env` if you want a default token or tighter policy.

```
GATE_MAX_P95_MS=800
GATE_MAX_ERROR_RATE=0.05
GATE_FAIL_ON_SECRET=1
```

Policy is also editable in the console under **Settings**.

## Tests

```bash
python -m pytest -q
```

## Docker

```bash
docker compose up --build
```

## Honest MVP boundary

- Single-tenant local workspace. Tokens live in SQLite — not for production SaaS.
- GitHub login is a personal access token. OAuth is next.
- Image scanning and a self-hosted runner are specified, not required for the demo.
- Runtime load/chaos only boot stacks the control plane can start (Flask apps and static frontends). Compose-heavy apps should use the Actions workflow on a runner with Docker.

That is enough to demonstrate the real product: a gate that tests *other* applications and refuses to let bad ones through.
