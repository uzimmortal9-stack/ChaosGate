import html
import os
import subprocess

files_to_render = [
    ('pipeline/workflows/chaosgate.yml', 'code_workflow_yaml.png', 'GitHub Actions Workflow (chaosgate.yml)'),
    ('docs/chaosgate.example.yml', 'code_chaosgate_yml.png', 'ChaosGate Contract Specification (chaosgate.yml)'),
    ('core/pipeline_service.py', 'code_pipeline_service.png', 'Pipeline Execution Engine (core/pipeline_service.py)'),
    ('core/supply_chain.py', 'code_supply_chain.png', 'Supply Chain Vulnerability Scanner (core/supply_chain.py)'),
    ('core/recovery.py', 'code_recovery.png', 'Automated Revert & Rollback Engine (core/recovery.py)'),
    ('k8s/chaosgate-deployment.yaml', 'code_k8s_deployment.png', 'Kubernetes Deployment Manifest (k8s/chaosgate-deployment.yaml)')
]

os.makedirs('screenshots', exist_ok=True)

html_template = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {
    margin: 0; padding: 24px; background: #0f141c;
    font-family: 'Consolas', 'Courier New', monospace;
  }
  .window {
    background: #161d27; border-radius: 8px; border: 1px solid #283344;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5); overflow: hidden;
  }
  .header {
    background: #111721; padding: 12px 16px; border-bottom: 1px solid #283344;
    display: flex; align-items: center; gap: 8px;
  }
  .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
  .dot.red { background: #ff5f56; }
  .dot.yellow { background: #ffbd2e; }
  .dot.green { background: #27c93f; }
  .title { color: #8b9eb5; font-size: 13px; font-weight: 600; margin-left: 12px; }
  pre {
    margin: 0; padding: 20px; color: #d6e2f0; font-size: 13px; line-height: 1.5;
    white-space: pre-wrap; word-break: break-all;
  }
  .comment { color: #627289; font-style: italic; }
  .key { color: #79c0ff; font-weight: 600; }
  .string { color: #8fe587; }
</style>
</head>
<body>
<div class="window">
  <div class="header">
    <span class="dot red"></span>
    <span class="dot yellow"></span>
    <span class="dot green"></span>
    <span class="title">__TITLE__</span>
  </div>
  <pre>__CODE__</pre>
</div>
</body>
</html>"""

for src_path, out_png, title in files_to_render:
    if not os.path.exists(src_path):
        print(f"Skipping missing {src_path}")
        continue
    with open(src_path, "r", encoding="utf-8") as f:
        code_lines = f.readlines()[:48]
    raw_text = "".join(code_lines)
    escaped = html.escape(raw_text)

    lines = []
    for line in escaped.splitlines():
        trimmed = line.strip()
        if trimmed.startswith(("#", "//")):
            lines.append(f'<span class="comment">{line}</span>')
        elif ":" in line and not trimmed.startswith("-"):
            parts = line.split(":", 1)
            lines.append(f'<span class="key">{parts[0]}</span>:<span class="string">{parts[1]}</span>')
        else:
            lines.append(line)
    colored = "\n".join(lines)

    rendered_html = html_template.replace("__TITLE__", title).replace("__CODE__", colored)
    temp_html = os.path.abspath(f"screenshots/temp_{out_png}.html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    dest_png = os.path.abspath(f"screenshots/{out_png}")
    file_url = "file:///" + temp_html.replace("\\", "/")
    cmd = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--screenshot={dest_png}",
        "--window-size=1200,800",
        file_url
    ]
    subprocess.run(cmd, capture_output=True, timeout=15)
    if os.path.exists(temp_html):
        os.remove(temp_html)
    if os.path.exists(dest_png):
        print(f"Generated code screenshot: {out_png} ({os.path.getsize(dest_png)} bytes)")
