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


def test_detects_rust_stack(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "my-crate"\nversion = "0.1.0"\n')
    detected = detect_app(tmp_path)
    assert detected["language"] == "rust"
    assert detected["test_command"] == "cargo test"
    assert detected["build_command"] == "cargo build --release"


def test_detects_go_stack(tmp_path):
    (tmp_path / "go.mod").write_text('module myapp\ngo 1.21\n')
    detected = detect_app(tmp_path)
    assert detected["language"] == "go"
    assert detected["test_command"] == "go test ./..."
    assert detected["build_command"] == "go build ./..."
