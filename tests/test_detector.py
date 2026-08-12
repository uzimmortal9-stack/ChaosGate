from pathlib import Path

from core.config_parser import parse_config
from core.detector import detect_app


def test_detects_python_api():
    root = Path("samples/atlas-api")
    cfg, _ = parse_config(root)
    detected = detect_app(root, cfg)
    assert detected["language"] == "python"
    assert "flask" in detected["frameworks"]
    assert detected["test_command"]


def test_detects_js_storefront():
    root = Path("samples/nova-web")
    cfg, _ = parse_config(root)
    detected = detect_app(root, cfg)
    assert detected["language"] == "javascript"
    assert "node --test" in detected["test_command"]
