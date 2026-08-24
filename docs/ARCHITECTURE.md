# ChaosGate architecture

ChaosGate is a **control plane**. It does not replace the application you are shipping. It tests that application and decides whether the change may enter `main`.

```
Browser (vanilla-JS SPA, no build step)
  │
  ▼
Flask control plane ─── SQLite (workspaces, repos, runs, stages, pushes, webhooks)
  │
  ├─ core/github_client.py    OAuth + PAT · repos · PRs · commit statuses · webhooks
  ├─ core/workspace.py        clone · browse · edit · diff · commit · push
  ├─ core/toolchain.py        probes what this host can actually do
  ├─ core/metrics.py          Prometheus exposition (/metrics)
  │
  └─ core/pipeline_service.py   the 13-stage engine
        ├─  1 validate      chaosgate.yml or autodetect
        ├─  2 detect        stack + host capabilities
        ├─  3 unit          pytest / node --test / npm test
        ├─  4 build         npm run build / compileall
        ├─  5 security      secrets · unpinned deps · lockfiles
        ├─  6 docker        core/docker_runner.py — audit + real build
        ├─  7 k8s           core/k8s_runner.py — audit + server dry-run
        ├─  8 smoke         boot container → Flask → static, hit /health
        ├─  9 load          core/k6_runner.py — real k6 or built-in
        ├─ 10 prometheus    core/prometheus.py — validate · query · push
        ├─ 11 chaos         kill + restart, measure recovery
        ├─ 12 grafana       core/grafana.py — build + publish dashboard
        └─ 13 verdict       score · PASS/FAIL · commit status back to GitHub
                                     │
/metrics ──── Prometheus ──── Grafana
```

## Stage outcomes

Every stage reports one of four states. The fourth is the one that matters:

| State | Meaning |
| --- | --- |
| `passed` | The work ran and succeeded |
| `failed` | The work ran and failed — this can seal the gate |
| `skipped` | Not applicable to this repository (no Dockerfile, chaos disabled) |
| `degraded` | The tool is unavailable on this host; the static subset ran instead |

`degraded` exists so the gate never reports a container build it did not perform. A
degraded stage costs a few points, is listed explicitly in the verdict, and does not
block a merge unless `fail_on_degraded` is set.

## The edit → push → gate loop

```
1. Connect GitHub          OAuth or PAT  →  list repositories
2. Select a repository     POST /api/repos
3. Open folder             POST /api/repos/<id>/workspace   → git clone into data/workspaces/<id>
4. Browse and edit         GET/PUT /api/repos/<id>/file     → path-guarded filesystem access
5. Review                  GET /api/repos/<id>/diff         → per-file patches
6. Push                    POST /api/repos/<id>/push        → branch + commit + push + PR
7. Gate fires              create_run() → start_run_async() → 13 stages
8. Verdict                 POST /repos/<repo>/statuses/<sha> → required check blocks the merge
```

Three other paths reach step 7: an inbound webhook (`/webhook/github`), the GitHub
Actions workflow, and the manual **Run Gate** button.


## Two apps, never one

| App | Role |
| --- | --- |
| **Target** | The Python, Node, React, or full-stack product under test |
| **ChaosGate** | The product in this repository |

The small sample services in `samples/` are **targets**. They exist so the gate can be demonstrated without a GitHub account.

## How a foreign app is tested

ChaosGate cannot invent a health endpoint or a start command. Target repositories should ship a `chaosgate.yml` contract (see `docs/CHAOSGATE_YML.md`). If the file is missing, the engine autodetection still runs, but runtime stages may skip.

## Blocking merges

Pushed commits cannot be un-pushed. The correct control is:

1. Protect `main`
2. Require a pull request
3. Require the ChaosGate status check
4. Failed gate → merge disabled

`pipeline/workflows/chaosgate.yml` is the Actions file you copy into a target repo so GitHub can enforce that check. The control-plane **Run Gate** button runs the same stages locally for the demo and for repos the engine can clone.

## MVP boundary

This workspace is a single-tenant control panel. Tokens are stored in local SQLite and are not production-safe. Multi-tenant SaaS, OAuth apps, and self-hosted runners are the next phase — not a prerequisite for proving the gate.
