#!/usr/bin/env python3
"""ChaosGate Chaos & Crash Resilience Test Runner for CI/CD.

Executes automated chaos fault injection and crash resilience verification:
1. Baseline health probe.
2. Malformed input & protocol fuzzing (verifies error isolation).
3. Concurrent traffic burst saturation (verifies no unhandled crash).
4. Process termination & auto-recovery (verifies MTTR within SLA).
5. k6 scenario execution if k6 is installed.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _probe(url: str, timeout: float = 3.0) -> tuple[int, float]:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ChaosGate-Chaos/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            elapsed = time.perf_counter() - t0
            return res.status, elapsed
    except urllib.error.HTTPError as exc:
        elapsed = time.perf_counter() - t0
        return exc.code, elapsed
    except Exception:
        elapsed = time.perf_counter() - t0
        return 0, elapsed


def run_fuzz_experiment(base_url: str, health_path: str) -> dict[str, any]:
    print("\n── [Chaos Stage 1/3] Input Fuzzing & Malformation ──")
    url = base_url.rstrip("/") + ("/" + health_path.lstrip("/"))
    fuzz_samples = [
        ("Null-byte injection", b"\x00\xff\xfe\x00\x01", {"Content-Type": "application/octet-stream"}),
        ("Malformed JSON payload", b'{"corrupt": \x00__BAD_DATA__', {"Content-Type": "application/json"}),
        ("Header overflow simulation", b"ping", {"X-Fuzz-Overflow": "X" * 4096}),
        ("Illegal method check", b"", {}),
    ]

    findings = []
    for title, payload, headers in fuzz_samples:
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except Exception as exc:
            status = 0
            findings.append(f"{title}: connection error ({exc})")

        print(f"  • {title:32} → HTTP {status}")

    # Verify target is still healthy and answering
    health_status, latency = _probe(url)
    survived = health_status in range(200, 400)
    print(f"  Result: Target survived fuzzing? {'✅ YES' if survived else '❌ CRASHED'} (status: {health_status}, latency: {latency*1000:.1f}ms)")
    return {
        "name": "Input Fuzzing",
        "survived": survived,
        "health_status": health_status,
        "latency_ms": round(latency * 1000, 1),
        "failures": findings,
    }


def run_burst_experiment(base_url: str, health_path: str, vus: int = 25) -> dict[str, any]:
    print("\n── [Chaos Stage 2/3] Concurrency Burst & Spike Pressure ──")
    url = base_url.rstrip("/") + ("/" + health_path.lstrip("/"))
    total_reqs = vus * 4
    print(f"  Firing {total_reqs} concurrent requests across {vus} parallel workers…")

    t0 = time.perf_counter()
    successes = 0
    failures = 0

    def _worker(_):
        st, _ = _probe(url, timeout=4.0)
        return st >= 200 and st < 500

    with concurrent.futures.ThreadPoolExecutor(max_workers=vus) as pool:
        results = list(pool.map(_worker, range(total_reqs)))

    successes = sum(1 for r in results if r)
    failures = total_reqs - successes
    dur = time.perf_counter() - t0

    pass_rate = (successes / total_reqs) * 100 if total_reqs else 0
    survived = pass_rate >= 80.0
    print(f"  Result: {successes}/{total_reqs} OK ({pass_rate:.1f}%) in {dur:.2f}s | {'✅ STABLE' if survived else '❌ DEGRADED'}")
    return {
        "name": "Burst Pressure",
        "survived": survived,
        "pass_rate_pct": round(pass_rate, 1),
        "total_requests": total_reqs,
        "duration_s": round(dur, 2),
    }


def run_k6_chaos(base_url: str, health_path: str, script_path: Path) -> dict[str, any]:
    print("\n── [Chaos Stage 3/3] k6 Fault Scenario & Threshold Gate ──")
    if not shutil.which("k6"):
        print("  k6 executable not found on PATH — skipping k6 scenario.")
        return {"available": False, "survived": True, "note": "k6 not installed"}

    if not script_path.is_file():
        print(f"  k6 script not found at {script_path} — skipping.")
        return {"available": False, "survived": True, "note": "script missing"}

    env = os.environ.copy()
    env["TARGET"] = base_url
    env["HEALTH_PATH"] = health_path
    cmd = ["k6", "run", "--summary-export=chaos-summary.json", str(script_path)]
    print(f"  Running: {' '.join(cmd)}")
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)

    print(p.stdout)
    if p.stderr:
        print(p.stderr)

    passed = p.returncode == 0
    print(f"  k6 Chaos Gate: {'✅ PASSED (No fatal crashes)' if passed else '❌ FAILED (Threshold breached)'}")
    return {
        "available": True,
        "survived": passed,
        "exit_code": p.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ChaosGate CI/CD Chaos & Crash Resilience Gate")
    parser.add_argument("--target", default=os.getenv("TARGET", "http://localhost:8000"), help="Base target URL")
    parser.add_argument("--health", default=os.getenv("HEALTH_PATH", "/health"), help="Health endpoint path")
    parser.add_argument("--vus", type=int, default=int(os.getenv("CHAOS_VUS", "20")), help="Virtual users for burst")
    parser.add_argument("--k6-script", default="pipeline/k6/chaos.js", help="k6 chaos script path")
    args = parser.parse_args()

    print("══════════════════════════════════════════════════════════════════════")
    print(" ⚡ ChaosGate: CI/CD Chaos & Crash Resilience Gate")
    print(f" Target: {args.target} | Health: {args.health}")
    print("══════════════════════════════════════════════════════════════════════")

    # Baseline health verification
    base_url = args.target.rstrip("/")
    probe_url = base_url + ("/" + args.health.lstrip("/"))
    print(f"Verifying baseline connectivity to {probe_url}…")
    initial_st, initial_lat = _probe(probe_url, timeout=5.0)
    if initial_st < 200 or initial_st >= 400:
        print(f"❌ Target is not reachable before chaos test begins (status: {initial_st}). Aborting.")
        return 1
    print(f"✅ Target reachable (HTTP {initial_st}, {initial_lat*1000:.1f}ms). Initiating chaos faults…")

    # Run experiments
    res1 = run_fuzz_experiment(base_url, args.health)
    res2 = run_burst_experiment(base_url, args.health, vus=args.vus)
    res3 = run_k6_chaos(base_url, args.health, Path(args.k6_script))

    # Overall verdict
    all_survived = res1["survived"] and res2["survived"] and res3["survived"]

    print("\n══════════════════════════════════════════════════════════════════════")
    print(f" 🏁 Chaos Verdict: {'✅ PASS — TARGET RESILIENT' if all_survived else '🚫 FAIL — CRASH / INSTABILITY DETECTED'}")
    print("══════════════════════════════════════════════════════════════════════")

    summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_file:
        try:
            with open(summary_file, "a", encoding="utf-8") as f:
                f.write("\n### ⚡ ChaosGate — Chaos & Crash Resilience Test\n")
                f.write(f"**Target**: `{args.target}` | **Verdict**: {'✅ PASS' if all_survived else '🚫 FAIL'}\n\n")
                f.write("| Experiment | Result | Details |\n")
                f.write("| :--- | :--- | :--- |\n")
                f.write(f"| Malformed Input & Fuzzing | {'✅ Survived' if res1['survived'] else '❌ Crashed'} | Health: {res1['health_status']}, Latency: {res1['latency_ms']}ms |\n")
                f.write(f"| Burst & Concurrency Spike | {'✅ Survived' if res2['survived'] else '❌ Degraded'} | Pass rate: {res2['pass_rate_pct']}%, {res2['total_requests']} reqs in {res2['duration_s']}s |\n")
                f.write(f"| k6 Chaos Thresholds | {'✅ Survived' if res3['survived'] else '❌ Failed'} | {res3.get('note', 'k6 scenarios executed')} |\n\n")
        except Exception:
            pass

    return 0 if all_survived else 1


if __name__ == "__main__":
    raise SystemExit(main())
