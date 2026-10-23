import os
import subprocess

BOARD_DIR = r"C:\Users\Mayuresh Thakur\Downloads\ChaosGate\app\screenshots\board_assets"
os.makedirs(BOARD_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def render_card(html_content, output_name, width=600, height=450):
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
        print(f"Generated: {output_name} ({os.path.getsize(dest_png)} bytes)")

# 1. Individual Card 1: CI/CD Tools
html_c1 = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 12px; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  .card { border: 2px solid #0969da; border-radius: 8px; padding: 14px; background: #fff; text-align: center; }
  .title { font-size: 13px; font-weight: 700; color: #1f2328; margin-bottom: 8px; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; }
  .pie { width: 110px; height: 110px; border-radius: 50%; margin: 0 auto 10px; background: conic-gradient(#0969da 0% 82.4%, #2da44e 82.4% 94.2%, #cf222e 94.2% 100%); }
  .legend { font-size: 11px; text-align: left; line-height: 1.5; color: #57606a; margin-top: 6px; }
  .bold { font-weight: 700; color: #24292f; }
</style>
</head>
<body>
<div class="card">
  <div class="title">1. CI/CD Tools Adopted (17 Responses)</div>
  <div class="pie"></div>
  <div class="legend">
    <div>🔵 <span class="bold">GitHub Actions:</span> 82.4% (14)</div>
    <div>🟢 <span class="bold">GitLab CI/CD:</span> 41.2% (7)</div>
    <div>🔴 <span class="bold">Jenkins:</span> 17.6% (3)</div>
    <div>⚪ <span class="bold">Manual Deployment:</span> 11.8% (2)</div>
  </div>
</div>
</body>
</html>"""

# 2. Individual Card 2: Deployment Failures
html_c2 = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 12px; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  .card { border: 2px solid #cf222e; border-radius: 8px; padding: 14px; background: #fff; text-align: center; }
  .title { font-size: 13px; font-weight: 700; color: #1f2328; margin-bottom: 8px; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; }
  .pie { width: 110px; height: 110px; border-radius: 50%; margin: 0 auto 10px; background: conic-gradient(#cf222e 0% 41.2%, #bf8700 41.2% 53.0%, #2da44e 53.0% 82.4%, #0969da 82.4% 100%); }
  .legend { font-size: 11px; text-align: left; line-height: 1.5; color: #57606a; margin-top: 6px; }
  .bold { font-weight: 700; color: #24292f; }
</style>
</head>
<body>
<div class="card">
  <div class="title">2. Deployment Failure Rate (17 Responses)</div>
  <div class="pie"></div>
  <div class="legend">
    <div>🔴 <span class="bold">Monthly / Weekly Outages:</span> 41.2% (7)</div>
    <div>🟡 <span class="bold">Quarterly:</span> 11.8% (2)</div>
    <div>🟢 <span class="bold">Rarely (Yearly or less):</span> 29.4% (5)</div>
    <div>🔵 <span class="bold">Never:</span> 17.6% (3)</div>
  </div>
</div>
</body>
</html>"""

# 3. Individual Card 3: Resilience Validation
html_c3 = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 12px; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  .card { border: 2px solid #d4a72c; border-radius: 8px; padding: 14px; background: #fff; text-align: center; }
  .title { font-size: 13px; font-weight: 700; color: #1f2328; margin-bottom: 8px; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; }
  .pie { width: 110px; height: 110px; border-radius: 50%; margin: 0 auto 10px; background: conic-gradient(#0969da 0% 41.2%, #2da44e 41.2% 76.5%, #cf222e 76.5% 88.3%, #bf8700 88.3% 100%); }
  .legend { font-size: 11px; text-align: left; line-height: 1.5; color: #57606a; margin-top: 6px; }
  .bold { font-weight: 700; color: #24292f; }
</style>
</head>
<body>
<div class="card">
  <div class="title">3. Resilience Validation Method (17 Responses)</div>
  <div class="pie"></div>
  <div class="legend">
    <div>🔵 <span class="bold">Manual Restarts in Staging:</span> 41.2% (7)</div>
    <div>🟢 <span class="bold">Automated Chaos Tools:</span> 35.3% (6)</div>
    <div>🔴 <span class="bold">No Resilience Testing:</span> 11.8% (2)</div>
    <div>🟡 <span class="bold">Wait for User Bug Reports:</span> 11.8% (2)</div>
  </div>
</div>
</body>
</html>"""

# 4. Individual Card 4: Reaction to Simulated Outage Gate
html_c4 = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 12px; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  .card { border: 2px solid #2da44e; border-radius: 8px; padding: 14px; background: #fff; text-align: center; }
  .title { font-size: 13px; font-weight: 700; color: #1f2328; margin-bottom: 8px; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; }
  .pie { width: 110px; height: 110px; border-radius: 50%; margin: 0 auto 10px; background: conic-gradient(#2da44e 0% 64.7%, #bf8700 64.7% 100%); }
  .legend { font-size: 11px; text-align: left; line-height: 1.5; color: #57606a; margin-top: 6px; }
  .bold { font-weight: 700; color: #24292f; }
  .highlight { color: #1a7f37; font-weight: 800; font-size: 12px; margin-top: 4px; }
</style>
</head>
<body>
<div class="card">
  <div class="title">4. Acceptance of Enforced Gate (17 Responses)</div>
  <div class="pie"></div>
  <div class="legend">
    <div>🟢 <span class="bold">Strongly Support / Support:</span> 64.7% (11)</div>
    <div>🟡 <span class="bold">Neutral:</span> 35.3% (6)</div>
    <div>🔴 <span class="bold">Oppose:</span> <span class="highlight">0% (ZERO Opposed)</span></div>
  </div>
</div>
</body>
</html>"""

# 5. Survey Center Header Box
html_header = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 10px; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; text-align: center; }
  .box { border: 3px solid #0969da; border-radius: 8px; padding: 16px; background: #ddf4ff; }
  .main { font-size: 18px; font-weight: 800; color: #0969da; letter-spacing: 0.5px; }
  .sub { font-size: 12px; color: #57606a; font-weight: 600; margin-top: 4px; }
</style>
</head>
<body>
<div class="box">
  <div class="main">GOOGLE FORM</div>
  <div class="sub">DevOps, Security & System Resilience Survey (17 Verified Responses)</div>
</div>
</body>
</html>"""

# 6. Unified 4-Chart Poster Panel (matching sample layout in media_1791233983626.jpg)
html_unified_board = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 16px; background: #fff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  .container { border: 2px solid #1f2328; border-radius: 8px; padding: 16px; background: #fff; }
  .center-header { text-align: center; margin-bottom: 12px; }
  .tag { background: #ddf4ff; border: 2px solid #0969da; color: #0969da; font-weight: 800; font-size: 15px; padding: 6px 20px; border-radius: 6px; display: inline-block; }
  .grid-2x2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-top: 10px; }
  .c-box { border: 1px solid #d0d7de; border-radius: 6px; padding: 10px; background: #f6f8fa; text-align: center; }
  .c-title { font-size: 11px; font-weight: 700; color: #1f2328; margin-bottom: 6px; border-bottom: 1px solid #d0d7de; padding-bottom: 3px; }
  .pie { width: 80px; height: 80px; border-radius: 50%; margin: 0 auto 6px; }
  .pie1 { background: conic-gradient(#0969da 0% 82.4%, #2da44e 82.4% 94.2%, #cf222e 94.2% 100%); }
  .pie2 { background: conic-gradient(#cf222e 0% 41.2%, #bf8700 41.2% 53.0%, #2da44e 53.0% 82.4%, #0969da 82.4% 100%); }
  .pie3 { background: conic-gradient(#0969da 0% 41.2%, #2da44e 41.2% 76.5%, #cf222e 76.5% 100%); }
  .pie4 { background: conic-gradient(#2da44e 0% 64.7%, #bf8700 64.7% 100%); }
  .legend { font-size: 10px; text-align: left; line-height: 1.4; color: #57606a; }
  .bold { font-weight: 700; color: #1f2328; }
</style>
</head>
<body>
<div class="container">
  <div class="center-header">
    <div class="tag">GOOGLE FORM: KEY SURVEY FINDINGS</div>
  </div>
  <div class="grid-2x2">
    <div class="c-box">
      <div class="c-title">1. CI/CD Tools Adopted</div>
      <div class="pie pie1"></div>
      <div class="legend">
        <div>🔵 <span class="bold">GitHub Actions:</span> 82.4% (14)</div>
        <div>🟢 <span class="bold">GitLab CI/CD:</span> 41.2% (7)</div>
        <div>🔴 <span class="bold">Jenkins:</span> 17.6% (3)</div>
      </div>
    </div>
    <div class="c-box">
      <div class="c-title">2. Deployment Failure Rate</div>
      <div class="pie pie2"></div>
      <div class="legend">
        <div>🔴 <span class="bold">Monthly / Weekly:</span> 41.2% (7)</div>
        <div>🟢 <span class="bold">Rarely (Yearly):</span> 29.4% (5)</div>
        <div>🔵 <span class="bold">Never:</span> 17.6% (3)</div>
      </div>
    </div>
    <div class="c-box">
      <div class="c-title">3. Resilience Testing Practice</div>
      <div class="pie pie3"></div>
      <div class="legend">
        <div>🔵 <span class="bold">Manual Staging Restarts:</span> 41.2% (7)</div>
        <div>🟢 <span class="bold">Automated Chaos:</span> 35.3% (6)</div>
        <div>🔴 <span class="bold">No Resilience Tests:</span> 23.5% (4)</div>
      </div>
    </div>
    <div class="c-box">
      <div class="c-title">4. Enforced Outage Gate Acceptance</div>
      <div class="pie pie4"></div>
      <div class="legend">
        <div>🟢 <span class="bold">Support:</span> 64.7% (11)</div>
        <div>🟡 <span class="bold">Neutral:</span> 35.3% (6)</div>
        <div>🔴 <span class="bold">Oppose:</span> 0% (ZERO Opposed)</div>
      </div>
    </div>
  </div>
</div>
</body>
</html>"""

render_card(html_c1, "survey_card1_cicd.png", 350, 320)
render_card(html_c2, "survey_card2_failures.png", 350, 320)
render_card(html_c3, "survey_card3_resilience.png", 350, 320)
render_card(html_c4, "survey_card4_reaction.png", 350, 320)
render_card(html_header, "survey_header_google_form.png", 420, 140)
render_card(html_unified_board, "board1_google_form_survey_charts.png", 700, 480)
print("Survey cards generated.")
