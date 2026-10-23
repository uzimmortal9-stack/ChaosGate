import os
import subprocess

BOARD_DIR = r"C:\Users\Mayuresh Thakur\Downloads\ChaosGate\app\screenshots\board_assets"
os.makedirs(BOARD_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def render_board_card(html_content, output_name, width=1200, height=800):
    temp_html = os.path.join(BOARD_DIR, f"temp_{output_name}.html")
    dest_png = os.path.join(BOARD_DIR, output_name)
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
        print(f"Generated board panel: {output_name} ({os.path.getsize(dest_png)} bytes)")
    else:
        print(f"Failed board panel: {output_name}")

# Panel 1: board1_title_header.png
html_title = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 20px; background: #fff; font-family: 'Arial', sans-serif; text-align: center; }
  .card { border: 4px solid #0969da; border-radius: 12px; padding: 24px; background: #f0f7ff; }
  h1 { font-size: 32px; color: #0969da; margin: 0 0 10px 0; letter-spacing: 1px; font-weight: 800; }
  h2 { font-size: 18px; color: #24292f; margin: 0 0 16px 0; font-weight: 600; }
  .authors { font-size: 14px; color: #57606a; margin-bottom: 12px; font-weight: 600; }
  .credits { font-size: 13px; color: #1f2328; font-weight: 500; display: flex; justify-content: space-around; border-top: 1px solid #d0d7de; padding-top: 12px; }
</style>
</head>
<body>
<div class="card">
  <h1>CHAOSGATE: A UNIFIED DEVSECOPS RELEASE GATE & CONTROL PLANE</h1>
  <h2>Continuous Resilience, Secret Auditing & Policy Enforcement for Pull Requests</h2>
  <div class="authors">
    Mayuresh Thakur (B53) | Sarvesh Shinde (B17) | Dhruv Patil (B10) | Pranush Mali (A24) | Sahil Kamble (A52)
  </div>
  <div class="credits">
    <span><strong>Department:</strong> Computer Science & Engineering (AI&ML)</span>
    <span><strong>Guide:</strong> Prof. Pooja Lokhande</span>
    <span><strong>HoD:</strong> Dr. D. K. Chitre</span>
    <span><strong>Principal:</strong> Dr. S. B. Kadam</span>
  </div>
</div>
</body>
</html>"""

# Panel 2: board1_introduction.png
html_intro = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 20px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  p { font-size: 14px; line-height: 1.6; color: #24292f; margin: 8px 0; }
  .highlight { background: #fff8c5; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
</style>
</head>
<body>
<div class="card">
  <h3>INTRODUCTION</h3>
  <p>In modern software engineering, rapid continuous deployments frequently bypass thorough security and resilience validation. Standard CI/CD systems only check if code compiles and basic unit tests pass (the "happy path").</p>
  <p><span class="highlight">The Problem:</span> Fragile code, leaked credentials, and performance bottlenecks slip onto the production branch, leading to outages costing over $4M per incident.</p>
  <p><span class="highlight">ChaosGate Solution:</span> A lightweight, self-hosted admission gate and control plane that intercepts Pull Requests, runs a 13-stage verification pipeline (unit tests, static secret scanning, CVE checks, containerized k6 load tests, and chaos injection), and physically blocks merging if policies are violated.</p>
</div>
</body>
</html>"""

# Panel 3: board1_literature_survey_table.png
html_lit_table = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 10px; }
  th, td { border: 1px solid #d0d7de; padding: 8px 10px; text-align: left; }
  th { background: #f6f8fa; font-weight: 700; color: #24292f; }
  .green { color: #1a7f37; font-weight: 700; }
  .red { color: #cf222e; }
</style>
</head>
<body>
<div class="card">
  <h3>LITERATURE SURVEY & INCUMBENT TOOL TEARDOWN</h3>
  <table>
    <thead>
      <tr>
        <th>Tool / Platform</th>
        <th>Primary Purpose</th>
        <th>Cost (10 Devs)</th>
        <th>Merge Blocking</th>
        <th>Resilience / Load</th>
        <th>Limitations Identified</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>GitHub Actions</strong></td>
        <td>CI/CD Runner</td>
        <td>Free / Minutes</td>
        <td>Status check</td>
        <td>Manual workflow</td>
        <td>No native load/chaos tests; silent pass on failures</td>
      </tr>
      <tr>
        <td><strong>GitLab Ultimate</strong></td>
        <td>DevSecOps Suite</td>
        <td>$99/dev/mo ($11.8k/yr)</td>
        <td>Configurable</td>
        <td>External tool</td>
        <td>Very high cost; requires enterprise hosting</td>
      </tr>
      <tr>
        <td><strong>Snyk Team</strong></td>
        <td>Security & CVEs</td>
        <td>$300/dev/yr ($3.0k/yr)</td>
        <td>PR Check</td>
        <td>None</td>
        <td>Security-only; assumes scanner is always available</td>
      </tr>
      <tr>
        <td><strong>ChaosGate (Ours)</strong></td>
        <td>Release Gate & Control Plane</td>
        <td><strong>$0 (Self-Hosted)</strong></td>
        <td class="green">Physical (Branch Protection)</td>
        <td class="green">k6 + Chaos Probes</td>
        <td>Zero-config stack detection, honest degradation, post-merge revert</td>
      </tr>
    </tbody>
  </table>
</div>
</body>
</html>"""

# Panel 4: board1_google_form_survey_charts.png
html_survey_charts = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  .charts-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px; }
  .chart-box { border: 1px solid #d0d7de; border-radius: 8px; padding: 14px; text-align: center; background: #f6f8fa; }
  .chart-title { font-size: 12px; font-weight: 700; color: #24292f; margin-bottom: 12px; height: 32px; }
  .pie { width: 100px; height: 100px; border-radius: 50%; margin: 0 auto 12px; }
  .pie1 { background: conic-gradient(#0969da 0% 82.4%, #2da44e 82.4% 94.2%, #cf222e 94.2% 100%); }
  .pie2 { background: conic-gradient(#cf222e 0% 35.3%, #bf8700 35.3% 58.8%, #1a7f37 58.8% 70.6%, #54aeff 70.6% 100%); }
  .pie3 { background: conic-gradient(#cf222e 0% 41.2%, #bf8700 41.2% 82.4%, #1a7f37 82.4% 100%); }
  .legend { font-size: 11px; text-align: left; line-height: 1.5; color: #57606a; }
</style>
</head>
<body>
<div class="card">
  <h3>PRIMARY RESEARCH: SURVEY FINDINGS (17 PRACTITIONERS)</h3>
  <div class="charts-grid">
    <div class="chart-box">
      <div class="chart-title">1. CI/CD Tools Currently Used</div>
      <div class="pie pie1"></div>
      <div class="legend">
        <div>🔵 GitHub Actions: 82.4%</div>
        <div>🟢 GitLab CI: 41.2%</div>
        <div>🔴 Jenkins: 17.6%</div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">2. When Security Testing is Performed</div>
      <div class="pie pie2"></div>
      <div class="legend">
        <div>🔴 No Automated Security: 35.3%</div>
        <div>🟡 Post-Production Only: 23.5%</div>
        <div>🟢 During CI/CD: 11.8%</div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">3. Monthly Deployment Failure Rate</div>
      <div class="pie pie3"></div>
      <div class="legend">
        <div>🔴 Monthly/Frequent Failures: 41.2%</div>
        <div>🟡 Occasional Failures: 41.2%</div>
        <div>🟢 Never: 17.6%</div>
      </div>
    </div>
  </div>
</div>
</body>
</html>"""

# Panel 5: board1_project_brief.png
html_brief = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  .brief-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 10px; }
  .b-item { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 10px; }
  .b-label { font-size: 11px; font-weight: 700; color: #0969da; text-transform: uppercase; margin-bottom: 4px; }
  .b-val { font-size: 12px; color: #24292f; line-height: 1.4; }
  .core-principle { grid-column: span 2; background: #fff8c5; border: 1px solid #d4a72c; text-align: center; font-weight: 700; color: #7d4e00; padding: 8px; font-size: 13px; border-radius: 6px; }
</style>
</head>
<body>
<div class="card">
  <h3>PROJECT BRIEF</h3>
  <div class="brief-grid">
    <div class="b-item">
      <div class="b-label">Problem</div>
      <div class="b-val">Git accepts any commit. Bad code passes basic linting and breaks production.</div>
    </div>
    <div class="b-item">
      <div class="b-label">Target Users</div>
      <div class="b-val">Startups (2–15 devs), student project teams, and SMEs without dedicated DevOps hires.</div>
    </div>
    <div class="b-item">
      <div class="b-label">Solution</div>
      <div class="b-val">Self-hosted 13-stage gate posting verdicts to GitHub Branch Protection checks.</div>
    </div>
    <div class="b-item">
      <div class="b-label">Constraints</div>
      <div class="b-val">$0 cost, runs on a laptop with Python & git, zero paid API keys, single-tenant.</div>
    </div>
    <div class="core-principle">
      CORE DESIGN PRINCIPLE: "A gate that lies is worse than no gate."
    </div>
  </div>
</div>
</body>
</html>"""

# Panel 6: board1_specifications_table.png
html_specs = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }
  th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }
  th { background: #f6f8fa; font-weight: 700; }
</style>
</head>
<body>
<div class="card">
  <h3>SYSTEM SPECIFICATIONS</h3>
  <table>
    <tr><th>Component</th><th>Technology Specification</th></tr>
    <tr><td>Control Plane Server</td><td>Python 3.11, Flask REST API, SQLite (Thread-safe)</td></tr>
    <tr><td>Credential Security</td><td>AES/CTR + HMAC-SHA256 Encrypted Tokens at Rest (PBKDF2)</td></tr>
    <tr><td>Stack Detection Engine</td><td>Zero-config auto-probing: Python, Node.js, Rust, Go</td></tr>
    <tr><td>Supply Chain Scanner</td><td>High-entropy Regex + OSV.dev batch API (PyPI, npm, crates, Go)</td></tr>
    <tr><td>Synthetic Load Engine</td><td>Grafana k6 (configurable VUs, duration, p95/p99 latency)</td></tr>
    <tr><td>Chaos Engineering</td><td>Process kill, traffic burst load, corrupt HTTP request fuzzing</td></tr>
    <tr><td>VCS Integration</td><td>GitHub Webhooks & Status Check API, GitLab Webhooks</td></tr>
    <tr><td>Enforcement Mechanism</td><td>GitHub Branch Protection (Physically locks merge button)</td></tr>
  </table>
</div>
</body>
</html>"""

# Panel 7: board1_brainstorming_diagram.png
html_brainstorm = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }
  .node { border-radius: 6px; padding: 10px; font-size: 12px; border: 1px solid; }
  .rejected { background: #ffebe9; border-color: #cf222e; color: #cf222e; }
  .selected { background: #dafbe1; border-color: #1a7f37; color: #1a7f37; font-weight: 700; }
  .modified { background: #fff8c5; border-color: #9a6700; color: #7d4e00; font-weight: 700; }
  .label { font-size: 10px; text-transform: uppercase; font-weight: 700; margin-bottom: 4px; }
</style>
</head>
<body>
<div class="card">
  <h3>BRAINSTORMING: FROM 9 IDEAS TO ONE ARCHITECTURE</h3>
  <div class="grid">
    <div class="node rejected"><div class="label">REJECTED</div><strong>VS Code Extension</strong><br>Easily ignored or disabled; advisory only.</div>
    <div class="node rejected"><div class="label">REJECTED</div><strong>Git Pre-commit Hook</strong><br>Runs on dev machine; bypassed with <code>--no-verify</code>.</div>
    <div class="node rejected"><div class="label">REJECTED</div><strong>Slack / Discord Bot</strong><br>Notification ≠ Enforcement.</div>
    <div class="node rejected"><div class="label">REJECTED</div><strong>AI Code Reviewer</strong><br>Probabilistic; gates must be deterministic.</div>
    <div class="node selected"><div class="label">SELECTED</div><strong>GitHub Commit Status Check</strong><br>Physical merge-blocking enforcement.</div>
    <div class="node selected"><div class="label">SELECTED</div><strong>Web Control Plane Dashboard</strong><br>Real-time visibility, policy editor & trigger.</div>
    <div class="node modified"><div class="label">MODIFIED</div><strong>Auto-Revert Broken Commits</strong><br>Never force-push. Modified to safe PR revert.</div>
    <div class="node selected"><div class="label">SELECTED</div><strong>Resilience Score (0–100)</strong><br>Composite metric for repository quality.</div>
    <div class="node selected"><div class="label">SELECTED</div><strong>Ephemeral Containers</strong><br>Zero host contamination during load tests.</div>
  </div>
</div>
</body>
</html>"""

# Panel 8: board1_product_analysis_market_research.png
html_product_market = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  .market-stats { display: flex; justify-content: space-around; margin: 12px 0; background: #ddf4ff; padding: 12px; border-radius: 6px; border: 1px solid #54aeff; }
  .stat-col { text-align: center; }
  .stat-num { font-size: 20px; font-weight: 800; color: #0969da; }
  .stat-lbl { font-size: 11px; color: #57606a; text-transform: uppercase; }
  .comp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .comp-table th, .comp-table td { border: 1px solid #d0d7de; padding: 6px 10px; }
  .comp-table th { background: #f6f8fa; }
</style>
</head>
<body>
<div class="card">
  <h3>PRODUCT ANALYSIS & MARKET RESEARCH FOR BUSINESS POTENTIAL</h3>
  <div class="market-stats">
    <div class="stat-col"><div class="stat-num">$10.8 Bn ➔ $29.5 Bn</div><div class="stat-lbl">Global DevSecOps TAM (2026–2031)</div></div>
    <div class="stat-col"><div class="stat-num">$1,140 / dev / yr</div><div class="stat-lbl">Incumbent Enterprise Stack Cost</div></div>
    <div class="stat-col"><div class="stat-num">$0</div><div class="stat-lbl">ChaosGate Self-Hosted Cost</div></div>
  </div>
  <table class="comp-table">
    <tr><th>Target Segment</th><th>Why They Choose ChaosGate</th><th>Monetization Path</th></tr>
    <tr><td><strong>Student & Academic Teams</strong></td><td>Free, 5-minute setup, teaches real DevSecOps practice</td><td>Community Adoption & Brand</td></tr>
    <tr><td><strong>Startups (2–15 Devs)</strong></td><td>Avoids $11k/yr toolchain tax; no dedicated SRE hire</td><td>Open-Core Cloud Hosting</td></tr>
    <tr><td><strong>Regulated SMEs</strong></td><td>Self-hosted — source code never leaves their VPC</td><td>Paid Enterprise Tier (SSO & Audit logs)</td></tr>
  </table>
</div>
</body>
</html>"""

# Render all Board 1 cards
print("Rendering Board 1 cards...")
render_board_card(html_title, "board1_title_header.png", 1200, 260)
render_board_card(html_intro, "board1_introduction.png", 600, 360)
render_board_card(html_lit_table, "board1_literature_survey_table.png", 900, 380)
render_board_card(html_survey_charts, "board1_google_form_survey_charts.png", 900, 360)
render_board_card(html_brief, "board1_project_brief.png", 600, 360)
render_board_card(html_specs, "board1_specifications_table.png", 600, 360)
render_board_card(html_brainstorm, "board1_brainstorming_diagram.png", 900, 360)
render_board_card(html_product_market, "board1_product_analysis_market_research.png", 900, 360)
print("Board 1 rendering finished.")
