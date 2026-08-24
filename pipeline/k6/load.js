// ChaosGate load profile.
//
//   k6 run --env TARGET=http://localhost:8000 pipeline/k6/load.js
//
// Thresholds are the gate: k6 exits non-zero when they are breached, which
// fails the CI job and seals the merge.
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

const gateErrors = new Rate("gate_errors");
const gateLatency = new Trend("gate_latency", true);
const gateChecks = new Counter("gate_checks");

const BASE = __ENV.TARGET || "http://localhost:8000";
const PATHS = (__ENV.PATHS || "/health").split(",").map((p) => p.trim()).filter(Boolean);

export const options = {
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || "30s",
      gracefulStop: "10s",
    },
  },
  thresholds: {
    http_req_failed: [`rate<${__ENV.MAX_ERROR_RATE || 0.05}`],
    http_req_duration: [`p(95)<${__ENV.MAX_P95_MS || 800}`],
    gate_errors: [`rate<${__ENV.MAX_ERROR_RATE || 0.05}`],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export function setup() {
  const probe = http.get(`${BASE}${PATHS[0]}`);
  if (probe.status === 0) {
    throw new Error(`target ${BASE} is unreachable — nothing to load test`);
  }
  return { startedAt: Date.now() };
}

export default function () {
  for (const path of PATHS) {
    const res = http.get(`${BASE}${path}`, { tags: { path } });
    const ok = res.status >= 200 && res.status < 400;
    gateErrors.add(!ok);
    gateLatency.add(res.timings.duration);
    gateChecks.add(1);
    check(res, {
      [`GET ${path} is 2xx/3xx`]: () => ok,
      [`GET ${path} under 1s`]: () => res.timings.duration < 1000,
    });
  }
  sleep(Number(__ENV.SLEEP || 0.5));
}

export function handleSummary(data) {
  const m = data.metrics || {};
  const p95 = m.http_req_duration?.values?.["p(95)"] ?? 0;
  const err = m.http_req_failed?.values?.rate ?? 0;
  const line =
    `ChaosGate load: p95=${p95.toFixed(1)}ms errors=${(err * 100).toFixed(2)}% ` +
    `reqs=${m.http_reqs?.values?.count ?? 0}`;
  return {
    stdout: `\n${line}\n`,
    "k6-summary.json": JSON.stringify(data, null, 2),
  };
}
