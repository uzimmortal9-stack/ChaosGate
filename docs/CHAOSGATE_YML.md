# chaosgate.yml

Every target application that wants a complete gate should commit this file at the repository root.

```yaml
version: 1

app:
  name: my-app
  type: fullstack          # python.api | js.api | js.react | fullstack | auto
  compose_file: docker-compose.yml

services:
  frontend:
    url: http://localhost:3000
  api:
    url: http://localhost:8000
    health: /health

tests:
  unit:
    command: npm test -- --watchAll=false
  build:
    command: npm run build

load:
  target: http://localhost:8000
  duration: 30s
  vus: 20
  endpoints:
    - method: GET
      path: /health
    - method: GET
      path: /api/items
  thresholds:
    p95_ms: 800
    error_rate: 0.05

security:
  secret_scan: true
  dependency_scan: true
  image_scan: true

chaos:
  enabled: true
  experiments:
    - kill_api
    - restart_frontend
```

Without this file ChaosGate still:

- detects `requirements.txt`, `package.json`, Dockerfiles
- runs `pytest` or `node --test` / `npm test` when it can
- scans for committed secrets

It will not invent load endpoints or chaos experiments for an unknown app.
