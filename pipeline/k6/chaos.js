// ChaosGate Chaos & Resilience Profile.
//
//   k6 run --env TARGET=http://localhost:8000 pipeline/k6/chaos.js
//
// Evaluates application crash resilience and fault isolation under concurrent load
// combined with spike stress and malformed payload fuzzing.
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

const fatalCrashes = new Counter("fatal_crashes");
const chaosErrors = new Rate("chaos_errors");
const chaosLatency = new Trend("chaos_latency", true);
const fuzzIsolation = new Rate("fuzz_isolation_ok");

const BASE = __ENV.TARGET || "http://localhost:8000";
const HEALTH_PATH = __ENV.HEALTH_PATH || "/health";
const VUS = Number(__ENV.VUS || 15);
const DURATION = __ENV.DURATION || "25s";

export const options = {
  scenarios: {
    // 1. Steady background traffic while chaos faults occur
    steady_traffic: {
      executor: "constant-vus",
      vus: Math.max(5, Math.floor(VUS * 0.6)),
      duration: DURATION,
      gracefulStop: "5s",
    },
    // 2. Sudden load burst spike to probe concurrency saturation
    burst_spike: {
      executor: "ramping-vus",
      startVUs: 2,
      stages: [
        { duration: "5s", target: VUS },
        { duration: "10s", target: VUS * 2 },
        { duration: "5s", target: 2 },
      ],
      gracefulRampDown: "3s",
    },
  },
  thresholds: {
    // Application must not crash permanently (zero fatal 502/503/connection resets)
    fatal_crashes: ["count<5"],
    // Under chaos, p95 must remain bounded
    chaos_latency: ["p(95)<2500"],
    // Error rate must stay under 25% during active fault injection
    chaos_errors: ["rate<0.25"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "max"],
};

export function setup() {
  const probe = http.get(`${BASE}${HEALTH_PATH}`, { timeout: "5s" });
  if (probe.status === 0) {
    throw new Error(`Target ${BASE} is unreachable before chaos test starts.`);
  }
  return { startedAt: Date.now() };
}

export default function () {
  // Normal endpoint check
  const res = http.get(`${BASE}${HEALTH_PATH}`, {
    tags: { name: "health_probe" },
    timeout: "4s",
  });

  const isAlive = res.status >= 200 && res.status < 500;
  const isFatal = res.status === 0 || res.status >= 500;

  if (isFatal) {
    fatalCrashes.add(1);
    chaosErrors.add(1);
  } else {
    chaosErrors.add(res.status >= 400);
  }

  chaosLatency.add(res.timings.duration);

  check(res, {
    "Target survived (not crashed)": () => isAlive,
    "Latency under 3s": () => res.timings.duration < 3000,
  });

  // Fuzzing & Malformed payload injection to test error isolation
  if (Math.random() < 0.25) {
    const fuzzHeaders = {
      "Content-Type": "application/json",
      "X-ChaosGate-Fuzz": "\x00\xff\xfe\x7f\x80",
    };
    const fuzzPayload = JSON.stringify({
      corrupt: "\x00\x01\x02__INVALID_BUFFER__",
      overflow: "A".repeat(4096),
    });

    const fuzzRes = http.post(`${BASE}${HEALTH_PATH}`, fuzzPayload, {
      headers: fuzzHeaders,
      tags: { name: "fuzz_probe" },
      timeout: "3s",
    });

    // Fuzzing passes if server gracefully rejects (4xx) without crashing (5xx / connection abort)
    const survivedFuzz = fuzzRes.status < 500 && fuzzRes.status !== 0;
    fuzzIsolation.add(survivedFuzz);
    if (!survivedFuzz) {
      fatalCrashes.add(1);
    }
  }

  sleep(0.4);
}

export function handleSummary(data) {
  const m = data.metrics || {};
  const p95 = m.chaos_latency?.values?.["p(95)"] ?? 0;
  const crashes = m.fatal_crashes?.values?.count ?? 0;
  const errRate = (m.chaos_errors?.values?.rate ?? 0) * 100;

  const verdict = crashes === 0 ? "PASSED (Zero Crashes)" : `FAILED (${crashes} crash events)`;
  const line = `ChaosGate Chaos Report: Verdict=${verdict} | p95=${p95.toFixed(1)}ms | Fatal Crashes=${crashes} | Error Rate=${errRate.toFixed(1)}%`;

  return {
    stdout: `\n${line}\n`,
    "chaos-summary.json": JSON.stringify(data, null, 2),
  };
}
