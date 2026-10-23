# ChaosGate

[![Tests](https://img.shields.io/badge/tests-181%20passed-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](Dockerfile)
[![Security](https://img.shields.io/badge/tokens-AES--CTR%20%2B%20PBKDF2-orange.svg)](core/crypto.py)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**A Unified DevSecOps Release Gate and Control Plane.**

Traditional CI/CD pipelines only check the "happy path" — verifying that code compiles and basic unit tests pass. Fragile database queries, memory leaks, unpatched supply chain CVEs, and hardcoded API tokens slip through to production, causing outages and security incidents.

**ChaosGate shifts security and resilience strictly left to the Pull Request.** When a developer opens a PR, ChaosGate intercepts the webhook, dynamically detects the application stack, queries OSV.dev for unpatched CVEs, boots the application in an isolated Docker sandbox, bombards it with synthetic concurrency (k6) and chaos faults, and **physically disables the GitHub Merge button** via Branch Protection rules if SLAs are violated.

If a regression ever slips into production post-merge, ChaosGate's **Recovery Engine** analyzes git history, runs a 3-way merge conflict check, and automatically opens a clean **1-Click Revert PR**.

---

## Key Features

- **Zero-Config Stack Detection**: Automatically inspects manifests (`requirements.txt`, `package.json`, `Cargo.lock`, `go.mod`, `pyproject.toml`) and auto-configures test environments without custom scripts.
- **Multi-Ecosystem Supply Chain Scanner**: High-entropy regex scanner for leaked AWS/Stripe/JWT secrets + automated batch vulnerability lookups via **OSV.dev** across npm, PyPI, Crates.io, and Go.
- **Token Encryption at Rest**: Encrypts VCS personal access tokens using **PBKDF2 (100,000 iterations) + AES-CTR + HMAC-SHA256 authenticated encryption** (`core/crypto.py`).
- **Multi-VCS Webhook Support**: Ingests PR and push webhooks from **GitHub** (`/webhook/github`), **GitLab** (`/webhook/gitlab`), and **Generic CI** systems (`/webhook/generic`) with HMAC secret verification.
- **Ephemeral Container Sandboxing**: Spawns isolated Docker containers per test run via mounted host daemon, guaranteeing zero state leakage.
- **Synthetic Load & Chaos Injection**: Fires realistic traffic using **k6** (e.g. 200 VUs) while injecting faults: **container restarts**, **traffic bursts**, and **corrupt HTTP payloads**.
- **Post-Merge Disaster Recovery Engine**: Detects post-merge incidents, checks 3-way merge conflict matrices against `HEAD`, and generates instant **Revert PRs** (`core/recovery.py`).
- **Full Observability Stack**: Exposes **28 Prometheus metric families** at `/metrics` with pre-provisioned Grafana dashboards and 6 automated alert rules.
- **100% Automated Test Coverage**: **181 passing unit and integration tests** verifying cryptographic safety, pipeline stages, and recovery workflows.

---

## Architecture Overview

```
                      ┌──────────────────────────────────────┐
                      │    Developer Workstation / Git Push  │
                      └──────────────────┬───────────────────┘
                                         │ PR Opened / Webhook
                                         ▼
                      ┌──────────────────────────────────────┐
                      │      GitHub / GitLab Repository      │
                      └──────────────────┬───────────────────┘
                                         │ Webhook Payload
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CHAOSGATE CONTROL PLANE                               │
│                                                                                 │
│  ┌─────────────────────────┐  ┌──────────────────────────────────────────────┐  │
│  │   Flask API Gateway     │  │  Encrypted Token Store (AES-CTR + PBKDF2)    │  │
│  └───────────┬─────────────┘  └──────────────────────────────────────────────┘  │
│              │                                                                  │
│              ▼                                                                  │
│  ┌─────────────────────────┐                                                    │
│  │  1.0 Stack Detector     │ (Zero-config: Python, Node, Go, Rust)              │
│  └───────────┬─────────────┘                                                    │
│              │                                                                  │
│              ▼                                                                  │
│  ┌─────────────────────────┐         ┌───────────────────────────────────────┐  │
│  │  2.0 Supply Chain Scan  │ ◄─────► │  D3: OSV.dev Global Vulnerability DB  │  │
│  └───────────┬─────────────┘         └───────────────────────────────────────┘  │
│              │                                                                  │
│              ▼                                                                  │
│  ┌─────────────────────────┐         ┌───────────────────────────────────────┐  │
│  │  3.0 Ephemeral k6/Chaos │ ◄─────► │  D4: Prometheus / k6 Telemetry Store  │  │
│  └───────────┬─────────────┘         └───────────────────────────────────────┘  │
│              │                                                                  │
│              ▼                                                                  │
│  ┌─────────────────────────┐                                                    │
│  │  4.0 Composite Verdict  │ (0–100 Resilience Score across all 13 stages)     │
│  └───────────┬─────────────┘                                                    │
└──────────────┼──────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           GATE ENFORCEMENT & RECOVERY                           │
│                                                                                 │
│   [✔] Status Check: SUCCESS  ──► GitHub Merge Button ENABLED                    │
│   [✖] Status Check: FAILED   ──► GitHub Merge Button LOCKED + Diagnostics       │
│   [↺] Post-Merge Regression  ──► 3-Way Merge Clean Revert PR Auto-Generated     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## The 13-Stage Verification Pipeline

| # | Stage | Execution Logic |
| :---: | :--- | :--- |
| **1** | **Validate Contract** | Parses repository `chaosgate.yml` or falls back to intelligent zero-config mode. |
| **2** | **Stack Detection** | Discovers runtime: Python, Node.js, Go, Rust, or frontend frameworks. |
| **3** | **Unit Test Execution** | Executes native test runners (`pytest`, `npm test`, `cargo test`, `go test`). |
| **4** | **Build & Compilation** | Verifies artifact assembly (`npm run build`, `compileall`). |
| **5** | **Security & Supply Chain** | Scans regex for hardcoded secrets, flags committed `.env`, queries OSV.dev for lockfile CVEs. |
| **6** | **Docker Sandbox Build** | Builds an ephemeral container image; inspects layer caching and non-root users. |
| **7** | **Kubernetes Audit** | Discovers K8s manifests; validates resource limits, probe endpoints, and security contexts. |
| **8** | **Smoke Verification** | Boots container on an isolated bridge network and executes HTTP health probes. |
| **9** | **k6 Synthetic Load Test** | Generates concurrent load (e.g. 200 VUs); evaluates p95 latency and error rate against SLAs. |
| **10**| **Prometheus Telemetry** | Verifies exposition metrics, measures resource utilization, and evaluates SLO compliance. |
| **11**| **Chaos Engineering** | Injects faults: process termination, traffic surges, corrupt requests; measures recovery time. |
| **12**| **Grafana Dashboard** | Generates dynamic 20-panel telemetry dashboards for the PR run. |
| **13**| **Composite Verdict** | Aggregates all stage metrics into a 0–100 Resilience Score; enforces GitHub Branch Protection. |

---

## Quick Start

### Option 1: Native Local Run (Windows PowerShell)

```powershell
# 1. Navigate to app directory
cd app

# 2. Run the automated test suite (181 tests)
& ".\.venv\Scripts\pytest.exe" -v

# 3. Start the Flask Control Plane
& ".\.venv\Scripts\python.exe" app.py
```
*Open **http://127.0.0.1:8080** in your browser.*

---

### Option 2: Linux / macOS (Make)

```bash
cd app
make install    # Sets up virtualenv and installs dependencies
make test       # Runs the 181-test automated suite
make run        # Starts server on http://localhost:5000
```

---

### Option 3: Full Stack with Docker & Observability

```bash
cd app

# Launch Control Plane, Prometheus, Grafana & Pushgateway
docker compose --profile observability up -d

# Verify containers are healthy
docker compose ps
```

*Endpoints:*
- **ChaosGate Control Plane**: [http://localhost:5000](http://localhost:5000)
- **Prometheus**: [http://localhost:9090](http://localhost:9090)
- **Grafana**: [http://localhost:3000](http://localhost:3000) *(Credentials: `admin` / `admin`)*

---

## Database & Data Stores

ChaosGate uses a local, high-performance SQLite database stored at `data/chaosgate.db`.

### Querying Database Records

```powershell
# View all tables and row counts
python -c "import sqlite3; conn = sqlite3.connect('data/chaosgate.db'); print([(t[0], conn.execute('SELECT count(*) FROM ' + t[0]).fetchone()[0]) for t in conn.execute('SELECT name FROM sqlite_master WHERE type=\'table\'').fetchall()])"

# Inspect recent pipeline runs and verdicts
python -c "import sqlite3; conn = sqlite3.connect('data/chaosgate.db'); print('\n'.join([f'Run #{r[0]}: Repo={r[1]}, PR={r[2]}, Verdict={r[3]}, Score={r[4]}' for r in conn.execute('SELECT id, repo_name, pr_number, verdict, resilience_score FROM pipeline_runs LIMIT 5').fetchall()]))"
```

### Database Schema Overview:
- `workspaces`: Local repository checkouts and paths.
- `repositories`: Monitored repositories and encrypted access credentials.
- `pipeline_runs`: High-level run history, triggers, commit SHAs, and verdicts.
- `stages`: Granular execution logs, latency timings, and status for each of the 13 stages.
- `run_events`: Granular streaming telemetry and diagnostic log events.

---

## Sample Target Repositories

Included under `samples/` for end-to-end evaluation:

| Sample Target | Stack | Intended Gate Verdict | Why? |
| :--- | :--- | :---: | :--- |
| `atlas-shop/atlas-api` | Python / Flask | **PASS** | Clean dependencies, passing tests, p95 latency < 150ms. |
| `nova-labs/nova-web` | Node.js / React | **PASS** | Clean build, non-critical lockfile warning. |
| `mercury-pay/checkout-service` | Python | **FAIL** | Failing unit tests + hardcoded AWS credentials detected. |
| `helios-fin/legacy-billing` | Node.js / Express | **FAIL** | Committed `.env` file + pinned packages carry critical OSV.dev CVEs. |

---

## Project Structure

```
ChaosGate/
├── app/
│   ├── core/                  # Core engine & platform logic
│   │   ├── crypto.py          # AES-CTR + PBKDF2 token encryption
│   │   ├── pipeline.py        # 13-stage sequential execution engine
│   │   ├── recovery.py        # 3-way merge conflict detection & auto-revert
│   │   ├── supply_chain.py    # Multi-ecosystem secret & OSV.dev CVE scanner
│   │   ├── stack_detector.py  # Zero-config manifest detector
│   │   ├── container.py       # Ephemeral Docker build & lifecycle
│   │   ├── load.py            # k6 load generation & SLA thresholds
│   │   ├── chaos.py           # Process termination & fault injection
│   │   └── metrics.py         # 28 Prometheus metric definitions
│   ├── data/                  # SQLite DB, workspaces, and run artifacts
│   ├── docker/                # Prometheus & Grafana provisioning configs
│   ├── k8s/                   # Production Kubernetes deployment manifests
│   ├── samples/               # Target applications under test
│   ├── tests/                 # 181 automated unit and integration tests
│   ├── web/                   # Vanilla JS responsive control plane UI
│   ├── app.py                 # Flask REST gateway & webhook dispatcher
│   ├── Dockerfile             # Multi-stage container definition
│   └── docker-compose.yml     # Multi-service composition
└── README.md                  # Project documentation
```

---

## Academic Context

Developed as part of the **Third Year Engineering (DevOps VAP Review II)** curriculum:
* **Department**: Computer Science & Engineering (AI&ML)
* **Institution**: Vishwaniketan's Institute of Management Entrepreneurship & Engineering Technology (ViMEET), affiliated with the University of Mumbai.
* **Faculty Guide**: Prof. Pooja Lokhande
* **Head of Department**: Dr. Ankush B. Pawar
* **Principal**: Dr. B. R. Patil

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
