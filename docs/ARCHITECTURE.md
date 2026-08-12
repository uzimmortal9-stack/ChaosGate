# ChaosGate architecture

ChaosGate is a **control plane**. It does not replace the application you are shipping. It tests that application and decides whether the change may enter `main`.

```
User
  │
  ▼
ChaosGate Web UI
  │
  ▼
ChaosGate API  (Flask)
  │
  ├─ SQLite workspace
  ├─ GitHub API (optional token)
  └─ Local gate engine
        ├─ validate chaosgate.yml
        ├─ detect Python / JS / React / compose
        ├─ unit tests
        ├─ build / compile
        ├─ secret + dependency scan
        ├─ boot target + smoke
        ├─ traffic / load
        ├─ chaos restart
        └─ verdict
```

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
