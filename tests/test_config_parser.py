from pathlib import Path

from core.config_parser import parse_config, summarize_config


def test_parses_atlas_contract():
    cfg, errors = parse_config(Path("samples/atlas-api"))
    assert errors == []
    assert cfg is not None
    assert cfg["app"]["name"] == "atlas-api"
    assert cfg["chaos"]["enabled"] is True
    summary = summarize_config(cfg)
    assert summary["present"] is True
    assert "api" in summary["services"]


def test_missing_config():
    cfg, errors = parse_config(Path("tests"))
    assert cfg is None
    assert errors == []
