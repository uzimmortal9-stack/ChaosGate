from pathlib import Path

from core.scanners import scan_dependencies, scan_secrets


def test_checkout_has_committed_secret():
    findings = scan_secrets(Path("samples/checkout-service"))
    titles = " ".join(f["title"] for f in findings)
    assert "API key" in titles or "password" in titles


def test_atlas_is_clean():
    findings = scan_secrets(Path("samples/atlas-api"))
    assert findings == []


def test_unpinned_python_deps():
    findings = scan_dependencies(Path("samples/checkout-service"))
    assert any("Unpinned" in f["title"] for f in findings)
