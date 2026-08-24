# Running ChaosGate locally

Verified from a clean clone on Python 3.11 — install, 112 tests, boot, samples seeded.

---

## Requirements

| Need | Why | Without it |
| --- | --- | --- |
| **Python 3.10+** | The control plane | Nothing runs |
| **git** | Cloning target repos | Nothing runs |
| Node.js 18+ | JavaScript targets' unit tests | JS targets skip their unit stage |
| Docker | Container stage builds real images | Stage runs `degraded` — audits the Dockerfile only |
| kubectl + a cluster | Server-side manifest validation | Stage runs `degraded` — static audit only |
| k6 | Real load testing | Falls back to the built-in generator |

**Only Python and git are required.** Everything else degrades honestly and says so in the UI.

---

## Option A — Local Python (fastest)

```bash
git clone https://github.com/uzimmortal9-stack/ChaosGate.git
cd ChaosGate
git checkout arena/01a03235-chaosgate

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

Open **http://localhost:5000** and click **Launch demo console**.

Or use the Makefile:

```bash
make install
make run
```

### Verify it works

```bash
make test                          # 112 tests
curl localhost:5000/healthz        # {"status":"ok",...}
curl localhost:5000/metrics        # Prometheus exposition
```

---

## Option B — Docker

```bash
docker compose up -d --build       # → http://localhost:5000
```

With the full observability stack:

```bash
docker compose --profile observability up -d --build
```

| Service | URL | Login |
| --- | --- | --- |
| ChaosGate | http://localhost:5000 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | `admin` / `admin` |

The Grafana dashboard is pre-provisioned — open it under the **ChaosGate** folder.

> The compose file mounts `/var/run/docker.sock` so the container stage can build real
> images. That grants root-equivalent host access. Remove the mount to force degraded mode.

Tear down with `docker compose --profile observability down`.

---

## What to click first

1. **Launch demo console** — three sample targets are already connected.
2. **Repositories → `atlas-shop/atlas-api` → Run Gate.** Watch 13 stages stream live.
   Expect **PASS**, score ~82, with several stages marked `degraded` if you have no
   Docker/k6.
3. **Repositories → `mercury-pay/checkout-service` → Run Gate.** Expect **FAIL** — failing
   unit tests plus a committed secret. This is the gate refusing a bad change.
4. **Observability** — metric families, scrape config, and a dashboard download.
5. **Settings** — flip what seals the gate.

---

## Connecting your own GitHub repositories

### Personal access token (no setup)

1. https://github.com/settings/tokens → **Generate new token (classic)**
2. Scopes: **`repo`** and **`workflow`**
3. Console → **Connect** → paste it → **Save token**

Your repositories appear in a searchable list.

### OAuth (one-click sign-in)

Create an OAuth App at https://github.com/settings/developers:

- **Homepage URL**: `http://localhost:5000`
- **Authorization callback URL**: `http://localhost:5000/api/auth/github/callback`

Then in `.env`:

```bash
cp .env.example .env
```

```ini
GITHUB_CLIENT_ID=Iv1.xxxxxxxxxxxx
GITHUB_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
PUBLIC_URL=http://localhost:5000
```

Restart. The Connect page now shows **Continue with GitHub**.

---

## The edit → push → gate loop

1. **Connect** → select a repository (this is your own repo, not a sample).
2. **Open folder** — clones it to `data/workspaces/<repo-id>`.
3. **Editor** tab — click a file, edit it, `⌘S` / `Ctrl+S` to save.
4. **Changes** tab — review per-file diffs, tick what to include.
5. Write a commit message → **Push & run gate**.

ChaosGate pushes a `chaosgate/<timestamp>` branch, opens a PR, and starts the pipeline.
When it finishes it posts a commit status back to GitHub.

**To actually block merges:** GitHub repo → Settings → Branches → protect `main` → require
the **`ChaosGate / release-gate`** status check.

> Sample targets are read-only fixtures — the editor is disabled for them. Connect one of
> your own repositories to use it.

---

## Making the pipeline fire on a real `git push`

The in-app push triggers the gate directly. For pushes made outside ChaosGate, either:

**GitHub Actions** — repo → **Automation** tab → **Install workflow**. Commits
`.github/workflows/chaosgate.yml`. Runs on GitHub's runners, where Docker and k6 exist, so
no stage degrades.

**Webhook into your machine** — needs a public URL, since GitHub cannot reach `localhost`:

```bash
ngrok http 5000
```

```ini
# .env
PUBLIC_URL=https://your-id.ngrok-free.app
GITHUB_WEBHOOK_SECRET=pick-something-long
```

Restart, then **Automation → Install webhook**. Every push and PR now starts a run locally.

---

## Getting the stages out of degraded mode

**Docker** — install Docker Desktop or Engine, confirm `docker ps` works, restart ChaosGate.

**k6**
```bash
brew install k6                                    # macOS
sudo apt install k6                                # Debian/Ubuntu (after adding the repo)
choco install k6                                   # Windows
```

**Kubernetes** — any cluster reachable from `kubectl cluster-info`:
```bash
brew install kind && kind create cluster           # or Docker Desktop's built-in cluster
```
Validation is dry-run only by default. Set `K8S_APPLY=1` to really apply manifests.

**Prometheus / Grafana** — easiest via `docker compose --profile observability up -d`, or
point at existing instances with `PROMETHEUS_URL` / `GRAFANA_URL` / `GRAFANA_API_KEY`.

After installing anything: **Settings → Re-probe toolchain** (no restart needed).

---

## Testing your own app properly

Autodetect works, but a contract makes the runtime stages real. Add `chaosgate.yml` to your
repo root:

```yaml
version: 1
app:
  name: my-api
  type: auto
services:
  api:
    url: http://localhost:8000
    health: /health
tests:
  unit:
    command: python -m pytest -q
load:
  duration: 30s
  vus: 20
  endpoints:
    - {method: GET, path: /health}
  thresholds:
    p95_ms: 800
    error_rate: 0.05
chaos:
  enabled: true
  experiments: [restart_api]
```

Full reference: [`CHAOSGATE_YML.md`](CHAOSGATE_YML.md).

---

## Troubleshooting

**Port 5000 in use** (common on macOS — AirPlay Receiver):
```bash
PORT=5001 python app.py
```

**`ModuleNotFoundError`** — the venv isn't active. Re-run `source .venv/bin/activate`.

**Editor won't open on a repo** — sample targets are read-only by design. Use one of yours.

**Push rejected** — token needs `repo` scope, and you need write access to that repository.

**Everything says degraded** — expected with only Python and git installed. See the section
above.

**Start over:**
```bash
make clean      # wipes the database, workspaces and artifacts
```

---

## Where things live

```
data/chaosgate.db        SQLite — repos, runs, stages, pushes, webhooks
data/workspaces/<id>/    your cloned repositories (the editor writes here)
data/artifacts/<run>/    k6 summaries, dashboards, reports, generated manifests
```

All of `data/` is gitignored. Deleting it resets the app.
