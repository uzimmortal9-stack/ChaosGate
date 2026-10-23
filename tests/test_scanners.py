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


def test_ai_keys_detected(tmp_path):
    src = tmp_path / "app.py"
    groq = "gsk_" + "aBcDeFgHiJkLmNoPqRsTuVwXyZ12345678901234567890123456"
    nvidia = "nvapi-" + "abcdef1234567890abcdef1234567890"
    openrouter = "sk-or-" + "v1-" + "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    gemini = "sk-" + "124587614577865"
    google = "AIza" + "SyD1234567890abcdefghijklmnopqrstuv"
    src.write_text(
        f'GROQ_KEY = "{groq}"\n'
        f'NVIDIA_KEY = "{nvidia}"\n'
        f'OPENROUTER_KEY = "{openrouter}"\n'
        f'GEMINI_KEY = "{gemini}"\n'
        f'GOOGLE_KEY = "{google}"\n'
    )
    findings = scan_secrets(tmp_path)
    titles = [f["title"] for f in findings]
    assert any("Groq API key" in t for t in titles)
    assert any("NVIDIA NIM API key" in t for t in titles)
    assert any("OpenRouter API key" in t for t in titles)
    assert any("Hardcoded API key" in t or "OpenAI" in t for t in titles)
    assert any("Google API key" in t for t in titles)
