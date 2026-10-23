import os
import subprocess

OUT_DIR = r"C:\Users\Mayuresh Thakur\Downloads\ChaosGate\app\screenshots\diagrams"
os.makedirs(OUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def render_html_to_png(html_content, output_name, width=1400, height=900):
    temp_html = os.path.join(OUT_DIR, f"temp_{output_name}.html")
    dest_png = os.path.join(OUT_DIR, output_name)
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    file_url = "file:///" + temp_html.replace("\\", "/")
    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--screenshot={dest_png}",
        f"--window-size={width},{height}",
        file_url
    ]
    subprocess.run(cmd, capture_output=True, timeout=20)
    if os.path.exists(temp_html):
        os.remove(temp_html)
    if os.path.exists(dest_png):
        print(f"Generated {output_name} ({os.path.getsize(dest_png)} bytes)")
    else:
        print(f"Failed to generate {output_name}")

# 1. sketch_dashboard_wireframe.png
html_dashboard = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 24px; background: #0c1017; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #c9d1d9; }
  .wireframe-container { border: 2px solid #30363d; border-radius: 12px; background: #161b22; box-shadow: 0 16px 40px rgba(0,0,0,0.6); overflow: hidden; }
  .nav-header { background: #0d1117; padding: 16px 24px; border-bottom: 2px solid #30363d; display: flex; align-items: center; justify-content: space-between; }
  .brand { display: flex; align-items: center; gap: 12px; font-weight: 700; font-size: 18px; color: #58a6ff; letter-spacing: 0.5px; }
  .badge { background: #238636; color: #fff; font-size: 11px; padding: 4px 8px; border-radius: 12px; font-weight: 600; text-transform: uppercase; }
  .nav-tabs { display: flex; gap: 20px; font-size: 14px; font-weight: 500; }
  .nav-tabs span { cursor: pointer; padding: 6px 12px; border-radius: 6px; }
  .nav-tabs .active { background: #21262d; color: #58a6ff; border: 1px solid #30363d; }
  .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 24px; background: #0d1117; border-bottom: 1px solid #30363d; }
  .stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
  .stat-label { font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
  .stat-val { font-size: 24px; font-weight: 700; color: #f0f6fc; }
  .content { padding: 24px; }
  .section-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; color: #f0f6fc; display: flex; justify-content: space-between; align-items: center; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
  th { padding: 12px 16px; background: #21262d; color: #8b949e; border-bottom: 2px solid #30363d; font-weight: 600; }
  td { padding: 14px 16px; border-bottom: 1px solid #21262d; }
  .status-pass { color: #3fb950; font-weight: 600; background: rgba(46,160,67,0.15); padding: 4px 10px; border-radius: 12px; display: inline-block; }
  .status-fail { color: #f85149; font-weight: 600; background: rgba(248,81,73,0.15); padding: 4px 10px; border-radius: 12px; display: inline-block; }
  .tag { background: #30363d; color: #c9d1d9; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace; }
</style>
</head>
<body>
<div class="wireframe-container">
  <div class="nav-header">
    <div class="brand">
      <span>🛡️ ChaosGate Control Plane</span>
      <span class="badge">Gate Armed</span>
    </div>
    <div class="nav-tabs">
      <span class="active">Overview</span>
      <span>Repositories</span>
      <span>Pipeline Runs</span>
      <span>Observability</span>
      <span>Gate Policy</span>
    </div>
  </div>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Active Gate Status</div>
      <div class="stat-val" style="color: #3fb950;">ARMED (Strict)</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Monitored Repos</div>
      <div class="stat-val">4 Repositories</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Avg p95 Load Latency</div>
      <div class="stat-val">187 ms (<300ms)</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Blocked Merges</div>
      <div class="stat-val" style="color: #f85149;">2 Violations</div>
    </div>
  </div>
  <div class="content">
    <div class="section-title">
      <span>Connected Repositories & Release Gate Pipeline Health</span>
      <span style="font-size: 12px; color: #8b949e;">Autodetect Active: Python, Node.js, Rust, Go</span>
    </div>
    <table>
      <thead>
        <tr>
          <th>Repository</th>
          <th>Stack Detected</th>
          <th>Unit Tests</th>
          <th>Secret & CVE Scan</th>
          <th>k6 Synthetic Load</th>
          <th>Chaos Resilience</th>
          <th>Composite Verdict</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>atlas-shop/atlas-api</strong></td>
          <td><span class="tag">Python (Flask)</span></td>
          <td><span class="status-pass">42/42 Passed</span></td>
          <td><span class="status-pass">Clean (0 CVEs)</span></td>
          <td><span class="status-pass">p95: 187ms</span></td>
          <td><span class="status-pass">Survived</span></td>
          <td><span class="status-pass">PASS — Merge Enabled</span></td>
        </tr>
        <tr>
          <td><strong>nova-labs/nova-web</strong></td>
          <td><span class="tag">Node.js / React</span></td>
          <td><span class="status-pass">28/28 Passed</span></td>
          <td><span class="status-pass">Clean (0 CVEs)</span></td>
          <td><span class="status-pass">p95: 95ms</span></td>
          <td><span class="status-pass">Survived</span></td>
          <td><span class="status-pass">PASS — Merge Enabled</span></td>
        </tr>
        <tr>
          <td><strong>mercury-pay/checkout-service</strong></td>
          <td><span class="tag">Python (FastAPI)</span></td>
          <td><span class="status-fail">2 Tests Failed</span></td>
          <td><span class="status-fail">1 Secret Detected</span></td>
          <td><span class="status-fail">p95: 487ms (>300ms)</span></td>
          <td><span class="status-fail">Crashed</span></td>
          <td><span class="status-fail">FAIL — Merge Blocked</span></td>
        </tr>
        <tr>
          <td><strong>helios-fin/legacy-billing</strong></td>
          <td><span class="tag">Python (Django)</span></td>
          <td><span class="status-pass">15/15 Passed</span></td>
          <td><span class="status-fail">Committed .env & CVE</span></td>
          <td><span class="status-pass">p95: 210ms</span></td>
          <td><span class="status-pass">Survived</span></td>
          <td><span class="status-fail">FAIL — Merge Blocked</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
</body>
</html>"""

# 2. sketch_pr_blocked_wireframe.png
html_pr_blocked = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 24px; background: #0d1117; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #c9d1d9; }
  .pr-box { max-width: 900px; margin: 0 auto; border: 1px solid #30363d; border-radius: 8px; background: #0d1117; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
  .pr-header { padding: 20px 24px; border-bottom: 1px solid #30363d; }
  .pr-title { font-size: 20px; font-weight: 600; color: #f0f6fc; margin-bottom: 8px; }
  .pr-meta { font-size: 13px; color: #8b949e; display: flex; align-items: center; gap: 8px; }
  .pr-badge { background: #238636; color: #fff; font-weight: 600; padding: 3px 10px; border-radius: 12px; font-size: 12px; }
  .checks-section { padding: 20px 24px; background: #161b22; border-bottom: 1px solid #30363d; }
  .checks-header { font-size: 14px; font-weight: 600; color: #f85149; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
  .check-card { background: #0d1117; border: 1px solid #f85149; border-radius: 6px; padding: 16px; margin-bottom: 12px; }
  .check-card-title { font-weight: 600; color: #f0f6fc; font-size: 14px; display: flex; justify-content: space-between; margin-bottom: 8px; }
  .check-details { font-size: 12px; color: #8b949e; line-height: 1.6; font-family: 'Consolas', monospace; }
  .check-fail-item { color: #f85149; font-weight: 600; }
  .merge-action-box { padding: 20px 24px; background: #161b22; display: flex; align-items: center; justify-content: space-between; }
  .merge-btn-disabled { background: #21262d; border: 1px solid #30363d; color: #484f58; font-size: 14px; font-weight: 600; padding: 10px 20px; border-radius: 6px; cursor: not-allowed; display: flex; align-items: center; gap: 8px; }
  .merge-warning { font-size: 13px; color: #f85149; font-weight: 500; }
</style>
</head>
<body>
<div class="pr-box">
  <div class="pr-header">
    <div class="pr-title">feat: add new payment gateway & billing sync #42</div>
    <div class="pr-meta">
      <span class="pr-badge">Open</span>
      <span>dev-team wants to merge 3 commits into <code>main</code> from <code>feature/billing-v2</code></span>
    </div>
  </div>
  <div class="checks-section">
    <div class="checks-header">
      <span style="font-size: 18px;">❌</span>
      <span>ChaosGate Admission Check: FAILED — Merging is blocked</span>
    </div>
    <div class="check-card">
      <div class="check-card-title">
        <span>ChaosGate DevSecOps Admission Gate (13 Stages)</span>
        <span style="color: #f85149;">Failing (2 policy violations)</span>
      </div>
      <div class="check-details">
        <div>[Stage 5: Supply Chain & Secret Scan] <span class="check-fail-item">FAILED</span> — 1 hardcoded AWS Key detected in <code>config.py:14</code> (AKIA-REDACTED-KEY)</div>
        <div>[Stage 9: k6 Synthetic Concurrency] <span class="check-fail-item">FAILED</span> — p95 response time 487ms exceeds configured SLA threshold (300ms)</div>
        <div style="color: #8b949e; margin-top: 6px;">[Stage 11: Chaos Engineering Probe] <span class="check-fail-item">FAILED</span> — Service crashed upon 500ms connection timeout injection</div>
      </div>
    </div>
  </div>
  <div class="merge-action-box">
    <div class="merge-warning">
      🔒 Merging is physically blocked by GitHub Branch Protection rules. Requires all ChaosGate status checks to pass before merging.
    </div>
    <button class="merge-btn-disabled" disabled>
      <span>🔒</span> Merge Pull Request (Blocked)
    </button>
  </div>
</div>
</body>
</html>"""

# 3. sketch_pipeline_stepper.png
html_stepper = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 32px; background: #0c1017; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #c9d1d9; }
  .stepper-card { background: #161b22; border: 2px solid #30363d; border-radius: 12px; padding: 24px; box-shadow: 0 16px 40px rgba(0,0,0,0.6); }
  .title { font-size: 18px; font-weight: 700; color: #58a6ff; margin-bottom: 24px; text-align: center; }
  .stepper { display: grid; grid-template-columns: repeat(13, 1fr); gap: 6px; position: relative; }
  .step-node { display: flex; flex-direction: column; align-items: center; text-align: center; }
  .circle { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 12px; margin-bottom: 8px; border: 2px solid; }
  .circle.done { background: rgba(46,160,67,0.2); border-color: #2ea043; color: #3fb950; }
  .circle.active { background: rgba(187,128,9,0.2); border-color: #d29922; color: #e3b341; box-shadow: 0 0 10px rgba(210,153,34,0.4); }
  .circle.fail { background: rgba(248,81,73,0.2); border-color: #f85149; color: #f85149; }
  .step-label { font-size: 10px; font-weight: 600; color: #8b949e; text-transform: uppercase; word-break: break-word; }
  .connector { height: 2px; background: #30363d; position: absolute; top: 18px; left: 24px; right: 24px; z-index: 0; }
</style>
</head>
<body>
<div class="stepper-card">
  <div class="title">ChaosGate: 13-Stage Verification Pipeline Execution Flow</div>
  <div style="position: relative; margin-top: 10px;">
    <div class="connector"></div>
    <div class="stepper" style="position: relative; z-index: 1;">
      <div class="step-node"><div class="circle done">1</div><div class="step-label">Validate</div></div>
      <div class="step-node"><div class="circle done">2</div><div class="step-label">Detect</div></div>
      <div class="step-node"><div class="circle done">3</div><div class="step-label">Unit</div></div>
      <div class="step-node"><div class="circle done">4</div><div class="step-label">Build</div></div>
      <div class="step-node"><div class="circle done">5</div><div class="step-label">Security</div></div>
      <div class="step-node"><div class="circle done">6</div><div class="step-label">Docker</div></div>
      <div class="step-node"><div class="circle done">7</div><div class="step-label">K8s</div></div>
      <div class="step-node"><div class="circle done">8</div><div class="step-label">Smoke</div></div>
      <div class="step-node"><div class="circle active">9</div><div class="step-label">Load (k6)</div></div>
      <div class="step-node"><div class="circle done" style="opacity: 0.5;">10</div><div class="step-label">Prometheus</div></div>
      <div class="step-node"><div class="circle done" style="opacity: 0.5;">11</div><div class="step-label">Chaos</div></div>
      <div class="step-node"><div class="circle done" style="opacity: 0.5;">12</div><div class="step-label">Grafana</div></div>
      <div class="step-node"><div class="circle done" style="opacity: 0.5;">13</div><div class="step-label">Verdict</div></div>
    </div>
  </div>
</div>
</body>
</html>"""

# 4. diagram_architecture_process_model.png
html_architecture = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 24px; background: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #24292f; }
  .arch-canvas { border: 2px solid #d0d7de; border-radius: 12px; padding: 24px; background: #f6f8fa; box-shadow: 0 10px 25px rgba(0,0,0,0.08); }
  .arch-title { font-size: 20px; font-weight: 700; text-align: center; color: #0969da; margin-bottom: 24px; }
  .grid-3 { display: grid; grid-template-columns: 280px 1fr 280px; gap: 24px; align-items: center; }
  .box { background: #fff; border: 2px solid #d0d7de; border-radius: 8px; padding: 18px; box-shadow: 0 4px 12px rgba(0,0,0,0.04); }
  .box-title { font-weight: 700; font-size: 14px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; color: #1f2328; border-bottom: 1px solid #d0d7de; padding-bottom: 6px; }
  .box-item { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 8px 12px; font-size: 12px; margin-bottom: 8px; font-weight: 500; }
  .center-engine { border: 2px solid #0969da; background: #f0f7ff; }
  .pipeline-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 12px; }
  .pipe-badge { background: #fff; border: 1px solid #0969da; border-radius: 6px; padding: 8px; font-size: 11px; text-align: center; font-weight: 600; color: #0969da; }
  .flow-arrow { text-align: center; font-size: 22px; color: #0969da; font-weight: bold; margin: 8px 0; }
</style>
</head>
<body>
<div class="arch-canvas">
  <div class="arch-title">ChaosGate: High-Level End-to-End System Architecture</div>
  <div class="grid-3">
    <!-- Left Column: Source & VCS -->
    <div class="box">
      <div class="box-title"><span>💻 Developer & VCS</span></div>
      <div class="box-item">Developer Workspace (git commit / push)</div>
      <div class="box-item">GitHub / GitLab Pull Request Opened</div>
      <div class="box-item">GitHub Webhook Event Emitted</div>
      <div class="box-item">Protected Branch (main) Policy</div>
    </div>

    <!-- Center Column: ChaosGate Core Engine -->
    <div class="box center-engine">
      <div class="box-title" style="color: #0969da;"><span>⚙️ ChaosGate Control Plane & Execution Engine</span></div>
      <div style="font-size: 12px; margin-bottom: 8px; font-weight: 600; color: #1f2328;">Flask REST API + SQLite (Encrypted Tokens at Rest) + Toolchain Prober</div>
      <div style="font-size: 11px; color: #57606a;">Automated Stack Detector (Python, Node.js, Rust, Go)</div>
      <div class="pipeline-grid">
        <div class="pipe-badge">1. Contract Validate</div>
        <div class="pipe-badge">2. Stack Detect</div>
        <div class="pipe-badge">3. Unit Tests</div>
        <div class="pipe-badge">4. Build / Package</div>
        <div class="pipe-badge">5. Secret & CVE Scan</div>
        <div class="pipe-badge">6. Docker Image</div>
        <div class="pipe-badge">7. K8s Manifest Dryrun</div>
        <div class="pipe-badge">8. Smoke Healthcheck</div>
        <div class="pipe-badge">9. k6 Load (p95 SLA)</div>
        <div class="pipe-badge">10. Prometheus Scrape</div>
        <div class="pipe-badge">11. Chaos Probes</div>
        <div class="pipe-badge">12. Grafana Metric Sync</div>
      </div>
      <div style="margin-top: 12px; padding: 8px; background: #fff; border-radius: 6px; border: 1px solid #0969da; text-align: center; font-weight: 700; font-size: 12px; color: #0969da;">
        Stage 13: Composite Verdict Aggregator (0–100 Resilience Score)
      </div>
    </div>

    <!-- Right Column: Enforcement & Rollback -->
    <div class="box">
      <div class="box-title"><span>🛡️ Gate Enforcement & Recovery</span></div>
      <div class="box-item" style="border-left: 4px solid #1a7f37;"><strong>GREEN GATE:</strong> GitHub Status Check SUCCESS ➔ Merge Button Enabled</div>
      <div class="box-item" style="border-left: 4px solid #cf222e;"><strong>RED GATE:</strong> Status Check FAILED ➔ Branch Protection Blocks Merge</div>
      <div class="box-item">Diagnostic Pull Request Comments Posted</div>
      <div class="box-item" style="border-left: 4px solid #bf8700;"><strong>Post-Merge Recovery:</strong> Automated Revert PR Generator with 3-Way Merge Conflict Detection</div>
    </div>
  </div>
</div>
</body>
</html>"""

# 5. diagram_pipeline_flowchart.png
html_flowchart = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 24px; background: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #24292f; }
  .canvas { max-width: 900px; margin: 0 auto; border: 2px solid #d0d7de; border-radius: 12px; padding: 24px; background: #f6f8fa; }
  .title { text-align: center; font-size: 20px; font-weight: 700; color: #0969da; margin-bottom: 20px; }
  .step { background: #fff; border: 2px solid #d0d7de; border-radius: 8px; padding: 12px 18px; margin: 0 auto 12px; width: 60%; text-align: center; font-weight: 600; font-size: 13px; box-shadow: 0 2px 6px rgba(0,0,0,0.04); }
  .decision { width: 50%; background: #fff8c5; border: 2px solid #9a6700; border-radius: 24px; padding: 12px; margin: 0 auto 12px; text-align: center; font-weight: 700; font-size: 13px; color: #7d4e00; }
  .arrow { text-align: center; font-size: 18px; color: #57606a; margin-bottom: 8px; }
  .branch { display: flex; justify-content: center; gap: 20px; margin-bottom: 12px; }
  .branch-node { width: 42%; padding: 14px; border-radius: 8px; text-align: center; font-weight: 700; font-size: 13px; }
  .pass-node { background: #dafbe1; border: 2px solid #1a7f37; color: #1a7f37; }
  .fail-node { background: #ffebe9; border: 2px solid #cf222e; color: #cf222e; }
</style>
</head>
<body>
<div class="canvas">
  <div class="title">ChaosGate: Pipeline Decision Logic Flowchart</div>
  <div class="step" style="background: #ddf4ff; border-color: #54aeff;">START: Pull Request Opened or Synchronized (GitHub / GitLab Webhook)</div>
  <div class="arrow">▼</div>
  <div class="step">Step 1: Automated Stack Detection (Python, Node.js, Rust, Go manifests)</div>
  <div class="arrow">▼</div>
  <div class="step">Step 2: Pre-flight Contract Validation (chaosgate.yml & Branch Protection rules)</div>
  <div class="arrow">▼</div>
  <div class="step">Step 3: Unit Tests + Static Secret Scan + OSV.dev CVE Database Audit</div>
  <div class="arrow">▼</div>
  <div class="decision">Decision 1: Unit Tests Pass & Zero Critical CVEs/Secrets?</div>
  <div class="arrow">▼ [YES]</div>
  <div class="step">Step 4: Ephemeral Docker Container Boot & Smoke Health Probe</div>
  <div class="arrow">▼</div>
  <div class="step">Step 5: k6 Synthetic Concurrency Load Test + Chaos Injection (Burst, Corrupt, Restart)</div>
  <div class="arrow">▼</div>
  <div class="decision">Decision 2: p95 Latency < Threshold & Survived Chaos Experiments?</div>
  <div class="arrow">▼</div>
  <div class="branch">
    <div class="branch-node pass-node">
      [ALL STAGES PASSED]<br>
      Set GitHub Status Check: SUCCESS<br>
      Branch Protection: ENABLE MERGE BUTTON<br>
      Exit: Deployment Ready
    </div>
    <div class="branch-node fail-node">
      [CRITERIA VIOLATED]<br>
      Set GitHub Status Check: FAILED<br>
      Branch Protection: DISABLE MERGE BUTTON<br>
      Post Detailed Failure Diagnostic PR Comment
    </div>
  </div>
  <div class="arrow">▼</div>
  <div class="step" style="background: #fff8c5; border-color: #9a6700; color: #7d4e00;">
    Post-Merge Fallback: Automated Revert PR Created with 3-Way Merge Conflict Diagnostics
  </div>
</div>
</body>
</html>"""

# 6. diagram_data_flow_dfd.png
html_dfd = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 24px; background: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #24292f; }
  .canvas { max-width: 960px; margin: 0 auto; border: 2px solid #d0d7de; border-radius: 12px; padding: 24px; background: #f6f8fa; }
  .title { text-align: center; font-size: 20px; font-weight: 700; color: #0969da; margin-bottom: 24px; }
  .entities-row { display: flex; justify-content: space-around; margin-bottom: 24px; }
  .entity { background: #fff; border: 2px solid #1f2328; padding: 12px 20px; font-weight: 700; font-size: 13px; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
  .processes-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
  .process { background: #ddf4ff; border: 2px solid #0969da; border-radius: 24px; padding: 16px; text-align: center; font-weight: 600; font-size: 12px; color: #0969da; }
  .datastores-row { display: flex; justify-content: space-around; }
  .datastore { border-top: 2px solid #1f2328; border-bottom: 2px solid #1f2328; background: #fff; padding: 10px 24px; font-weight: 700; font-size: 12px; color: #24292f; }
</style>
</head>
<body>
<div class="canvas">
  <div class="title">ChaosGate: Data Flow Diagram (DFD Level 1)</div>
  <div class="entities-row">
    <div class="entity">👤 Developer</div>
    <div class="entity">🐙 GitHub Webhook & Branch Protection API</div>
    <div class="entity">🛡️ SRE / DevOps Lead</div>
  </div>
  <div style="text-align: center; font-size: 12px; color: #57606a; margin-bottom: 12px;">▼ PR Webhook Events | Commits | Repo Manifests ▼</div>
  <div class="processes-grid">
    <div class="process"><strong>1.0 Event Ingestion & Auth</strong><br>Validate HMAC Secret & decrypt tokens</div>
    <div class="process"><strong>2.0 Stack & Toolchain Probe</strong><br>Detect Python, Node, Rust, Go manifests</div>
    <div class="process"><strong>3.0 Security & CVE Scanner</strong><br>Regex secrets + OSV.dev batch API query</div>
    <div class="process"><strong>4.0 Container & k6 Runner</strong><br>Docker boot + synthetic load generation</div>
    <div class="process"><strong>5.0 Observability Scraper</strong><br>Prometheus scrape & SLA latency evaluation</div>
    <div class="process"><strong>6.0 Verdict & Recovery Engine</strong><br>Post commit status & generate revert PR</div>
  </div>
  <div style="text-align: center; font-size: 12px; color: #57606a; margin-bottom: 12px;">▼ Query & Persist Data Stores ▼</div>
  <div class="datastores-row">
    <div class="datastore">D1: SQLite Database (Repositories & Runs)</div>
    <div class="datastore">D2: Policy Store (chaosgate.yml)</div>
    <div class="datastore">D3: OSV.dev Global Vulnerability DB</div>
  </div>
</div>
</body>
</html>"""

print("Starting diagram rendering...")
render_html_to_png(html_dashboard, "sketch_dashboard_wireframe.png", 1400, 850)
render_html_to_png(html_pr_blocked, "sketch_pr_blocked_wireframe.png", 1100, 750)
render_html_to_png(html_stepper, "sketch_pipeline_stepper.png", 1400, 450)
render_html_to_png(html_architecture, "diagram_architecture_process_model.png", 1400, 750)
render_html_to_png(html_flowchart, "diagram_pipeline_flowchart.png", 1100, 850)
render_html_to_png(html_dfd, "diagram_data_flow_dfd.png", 1100, 650)
print("Diagram generation completed.")
