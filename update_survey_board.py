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

html_survey_detailed = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  .card { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  h3 { margin-top: 0; color: #0969da; border-bottom: 2px solid #0969da; padding-bottom: 6px; font-size: 16px; display: flex; justify-content: space-between; }
  .charts-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 10px; }
  .chart-box { border: 1px solid #d0d7de; border-radius: 6px; padding: 10px; text-align: center; background: #f6f8fa; }
  .chart-title { font-size: 11px; font-weight: 700; color: #1f2328; margin-bottom: 8px; height: 32px; line-height: 1.2; }
  .pie { width: 80px; height: 80px; border-radius: 50%; margin: 0 auto 8px; }
  .pie1 { background: conic-gradient(#0969da 0% 82.4%, #2da44e 82.4% 94.2%, #cf222e 94.2% 100%); }
  .pie2 { background: conic-gradient(#0969da 0% 35.3%, #2da44e 35.3% 58.8%, #bf8700 58.8% 76.4%, #cf222e 76.4% 88.2%, #8250df 88.2% 100%); }
  .pie3 { background: conic-gradient(#cf222e 0% 41.2%, #bf8700 41.2% 53.0%, #2da44e 53.0% 82.4%, #0969da 82.4% 100%); }
  .pie4 { background: conic-gradient(#0969da 0% 41.2%, #2da44e 41.2% 76.5%, #cf222e 76.5% 88.3%, #bf8700 88.3% 100%); }
  .legend { font-size: 9.5px; text-align: left; line-height: 1.35; color: #57606a; margin-top: 6px; }
  .badge-row { margin-top: 10px; background: #ddf4ff; border: 1px solid #54aeff; border-radius: 6px; padding: 8px; font-size: 11px; text-align: center; font-weight: 600; color: #0969da; }
</style>
</head>
<body>
<div class="card">
  <h3>
    <span>PRIMARY RESEARCH: DEVOPS, SECURITY & RESILIENCE SURVEY</span>
    <span style="font-size: 12px; color: #57606a;">Google Forms · 17 Verified Industry Respondents</span>
  </h3>
  <div class="charts-grid">
    <div class="chart-box">
      <div class="chart-title">1. CI/CD Tools Adopted</div>
      <div class="pie pie1"></div>
      <div class="legend">
        <div>🔵 GitHub Actions: 82.4% (14)</div>
        <div>🟢 GitLab CI/CD: 41.2% (7)</div>
        <div>🔴 Jenkins: 17.6% (3)</div>
        <div>⚪ Manual Deploy: 11.8% (2)</div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">2. When Security Testing is Done</div>
      <div class="pie pie2"></div>
      <div class="legend">
        <div>🔵 During Coding: 35.3% (6)</div>
        <div>🟢 CI/CD Build: 23.5% (4)</div>
        <div>🟡 Threat Model: 17.6% (3)</div>
        <div>🔴 No Automation: 11.8% (2)</div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">3. Monthly Deployment Failures</div>
      <div class="pie pie3"></div>
      <div class="legend">
        <div>🔴 Monthly/Frequent: 41.2% (7)</div>
        <div>🟡 Quarterly: 11.8% (2)</div>
        <div>🟢 Rarely: 29.4% (5)</div>
        <div>🔵 Never: 17.6% (3)</div>
      </div>
    </div>
    <div class="chart-box">
      <div class="chart-title">4. Resilience Validation Practice</div>
      <div class="pie pie4"></div>
      <div class="legend">
        <div>🔵 Manual Restarts: 41.2% (7)</div>
        <div>🟢 Automated Chaos: 35.3% (6)</div>
        <div>🔴 No Resilience Test: 11.8% (2)</div>
        <div>🟡 User Bug Reports: 11.8% (2)</div>
      </div>
    </div>
  </div>
  <div class="badge-row">
    🎯 Key Discovery: 0% Opposed an Enforced Resilience Gate | 47.1% Chose Docker/Compose Staging as Safest Environment
  </div>
</div>
</body>
</html>"""

render_board_card(html_survey_detailed, "board1_google_form_survey_charts.png", 1000, 380)
print("Updated survey charts card.")
