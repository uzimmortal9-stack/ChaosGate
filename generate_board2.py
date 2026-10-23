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

# Panel 9: board2_ideation.png
html_ideation = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 8px; }
  .item { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 10px; font-size: 12px; }
  .item strong { color: #0969da; display: block; margin-bottom: 4px; }
</style>
</head>
<body>
<div class="card">
  <h3>IDEATION: MAPPING RESEARCH GAPS TO ARCHITECTURE</h3>
  <div class="grid">
    <div class="item">
      <strong>Gap 1: Developers believe GitHub blocks broken code</strong>
      <em>Ideation:</em> Build a native Commit Status check that ties directly into GitHub Branch Protection rules.
    </div>
    <div class="item">
      <strong>Gap 2: Committed secrets in .env and git history</strong>
      <em>Ideation:</em> Built-in static regex scanner + OSV.dev CVE batch scanner during PR creation.
    </div>
    <div class="item">
      <strong>Gap 3: CI/CD configuration seen as intimidating</strong>
      <em>Ideation:</em> Zero-configuration automatic stack detection (Python, Node, Rust, Go) with optional contract YAML.
    </div>
    <div class="item">
      <strong>Gap 4: No recourse once bad code is on main</strong>
      <em>Ideation:</em> Post-merge recovery engine that prepares clean revert PRs with 3-way merge conflict detection.
    </div>
  </div>
</div>
</body>
</html>"""

# Panel 10: board2_exploration.png
html_exploration = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }
  th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }
  th { background: #f6f8fa; }
  .selected { background: #dafbe1; font-weight: 700; color: #1a7f37; }
</style>
</head>
<body>
<div class="card">
  <h3>EXPLORATION: TECHNICAL STACK & RUNTIME EVALUATION</h3>
  <table>
    <tr><th>Engineering Dimension</th><th>Options Explored</th><th>Final Selection & Justification</th></tr>
    <tr><td>Synthetic Load Testing</td><td>Apache JMeter, Locust, k6</td><td class="selected">Grafana k6 (Headless, JS-scripted, microsecond thresholds)</td></tr>
    <tr><td>Vulnerability Auditing</td><td>Snyk CLI, SonarQube, OSV.dev</td><td class="selected">OSV.dev API (Open source, zero paid keys, multi-ecosystem)</td></tr>
    <tr><td>Isolation Strategy</td><td>Host processes vs Containers</td><td class="selected">Docker & K8s (Prevents host pollution during destructive load)</td></tr>
    <tr><td>Credential Security</td><td>Plaintext SQLite vs AES CTR</td><td class="selected">AES/CTR + HMAC-SHA256 (PBKDF2 key derivation from secret)</td></tr>
  </table>
</div>
</body>
</html>"""

# Panel 11: board2_methodology.png
html_methodology = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; text-align: center; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  .stepper { display: flex; justify-content: space-around; margin-top: 14px; }
  .step-box { background: #f0f7ff; border: 2px solid #0969da; border-radius: 8px; padding: 12px; width: 16%; }
  .step-num { font-size: 18px; font-weight: 800; color: #0969da; margin-bottom: 4px; }
  .step-title { font-size: 12px; font-weight: 700; color: #1f2328; margin-bottom: 4px; }
  .step-desc { font-size: 10px; color: #57606a; line-height: 1.3; }
</style>
</head>
<body>
<div class="card">
  <h3>DESIGN THINKING METHODOLOGY WORKFLOW</h3>
  <div class="stepper">
    <div class="step-box">
      <div class="step-num">01</div>
      <div class="step-title">EMPATHIZE</div>
      <div class="step-desc">Surveyed 17 developers; uncovered $11.4k/yr incumbent tax and 41% monthly failure rates.</div>
    </div>
    <div class="step-box">
      <div class="step-num">02</div>
      <div class="step-title">DEFINE</div>
      <div class="step-desc">Formulated core brief: "Git accepts any commit; a gate that lies is worse than no gate."</div>
    </div>
    <div class="step-box">
      <div class="step-num">03</div>
      <div class="step-title">IDEATE</div>
      <div class="step-desc">Filtered 9 divergent concepts; engineered the 13-stage deterministic admission gate.</div>
    </div>
    <div class="step-box">
      <div class="step-num">04</div>
      <div class="step-title">PROTOTYPE</div>
      <div class="step-desc">Implemented Flask control plane, k6 runner, OSV scanner, and GitHub Actions engine.</div>
    </div>
    <div class="step-box">
      <div class="step-num">05</div>
      <div class="step-title">TEST & VERIFY</div>
      <div class="step-desc">181 automated tests passing; verified across Python, Node.js, React, Rust, and Go apps.</div>
    </div>
  </div>
</div>
</body>
</html>"""

# Panel 12: board2_finalized_concept_architecture.png
html_final_concept = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  .stage-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 10px; font-size: 11px; }
  .stage-card { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 8px; text-align: center; font-weight: 600; }
  .stage-card strong { display: block; color: #0969da; font-size: 12px; margin-bottom: 2px; }
</style>
</head>
<body>
<div class="card">
  <h3>FINALIZED CONCEPT: THE 13-STAGE VERIFICATION PIPELINE</h3>
  <div class="stage-grid">
    <div class="stage-card"><strong>1. Validate</strong>Contract & branch rules</div>
    <div class="stage-card"><strong>2. Detect</strong>Stack auto-probing</div>
    <div class="stage-card"><strong>3. Unit</strong>pytest / npm test</div>
    <div class="stage-card"><strong>4. Build</strong>Compile / bundle</div>
    <div class="stage-card"><strong>5. Security</strong>Secrets & OSV.dev CVEs</div>
    <div class="stage-card"><strong>6. Docker</strong>Image build & tags</div>
    <div class="stage-card"><strong>7. K8s</strong>Kubernetes manifest check</div>
    <div class="stage-card"><strong>8. Smoke</strong>Endpoint healthcheck</div>
    <div class="stage-card"><strong>9. Load (k6)</strong>p95 latency threshold</div>
    <div class="stage-card"><strong>10. Prometheus</strong>Metrics harvest</div>
    <div class="stage-card"><strong>11. Chaos</strong>Restart & traffic burst</div>
    <div class="stage-card"><strong>12. Grafana</strong>Dashboard registration</div>
  </div>
  <div style="margin-top: 10px; background: #dafbe1; border: 2px solid #1a7f37; border-radius: 6px; padding: 10px; text-align: center; font-weight: 700; color: #1a7f37; font-size: 13px;">
    Stage 13: Composite Verdict Aggregator ➔ Branch Protection Locks or Enables GitHub Merge
  </div>
</div>
</body>
</html>"""

# Panel 13: board2_verification_load_chaos.png
html_load_chaos = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: 'Arial', sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 18px; }
  table { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 8px; }
  th, td { border: 1px solid #d0d7de; padding: 6px 8px; text-align: center; }
  th { background: #f6f8fa; }
  .pass { color: #1a7f37; font-weight: 700; }
  .fail { color: #cf222e; font-weight: 700; }
</style>
</head>
<body>
<div class="card">
  <h3>STRUCTURE UNDER TEST: RESULTS MATRIX (LOAD & CHAOS VALIDATION)</h3>
  <table>
    <tr><th>Target Application</th><th>Stack</th><th>Unit Tests</th><th>Secret / CVE</th><th>k6 Load (p95 SLA)</th><th>Chaos Injection</th><th>Verdict</th></tr>
    <tr><td><strong>atlas-shop/atlas-api</strong></td><td>Python/Flask</td><td class="pass">42/42 Pass</td><td class="pass">Clean</td><td class="pass">187ms (<300ms)</td><td class="pass">Survived</td><td class="pass">PASS (Merge Enabled)</td></tr>
    <tr><td><strong>nova-labs/nova-web</strong></td><td>Node/React</td><td class="pass">28/28 Pass</td><td class="pass">Clean</td><td class="pass">95ms (<300ms)</td><td class="pass">Survived</td><td class="pass">PASS (Merge Enabled)</td></tr>
    <tr><td><strong>mercury-pay/checkout</strong></td><td>Python/FastAPI</td><td class="fail">2 Failed</td><td class="fail">1 AWS Key</td><td class="fail">487ms (>300ms)</td><td class="fail">Crashed</td><td class="fail">FAIL (Merge Blocked)</td></tr>
    <tr><td><strong>helios-fin/legacy-bill</strong></td><td>Python/Django</td><td class="pass">15/15 Pass</td><td class="fail">Committed .env</td><td class="pass">210ms (<300ms)</td><td class="pass">Survived</td><td class="fail">FAIL (Merge Blocked)</td></tr>
  </table>
  <div style="margin-top: 8px; font-size: 11px; color: #57606a;">
    * Verified via 181 automated tests. Failures automatically trigger diagnostic PR comments and block the merge button.
  </div>
</div>
</body>
</html>"""

# Render Board 2 cards
print("Rendering Board 2 cards...")
render_board_card(html_ideation, "board2_ideation.png", 900, 360)
render_board_card(html_exploration, "board2_exploration.png", 900, 360)
render_board_card(html_methodology, "board2_methodology.png", 1000, 300)
render_board_card(html_final_concept, "board2_finalized_concept_architecture.png", 900, 360)
render_board_card(html_load_chaos, "board2_verification_load_chaos.png", 900, 340)
print("Board 2 rendering finished.")
