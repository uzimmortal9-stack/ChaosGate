import subprocess
from pathlib import Path

from core import pipeline_service


def test_run_cmd_quotes_python_executable(monkeypatch, tmp_path: Path):
    executable = r"C:\Program Files\ChaosGate\.venv\Scripts\python.exe"
    captured = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        return Result()

    monkeypatch.setattr(pipeline_service.sys, "executable", executable)
    monkeypatch.setattr(pipeline_service.subprocess, "run", fake_run)

    code, output = pipeline_service._run_cmd("python -m pytest -q", tmp_path)

    assert code == 0
    assert output == "ok"
    assert captured["command"] == f'{subprocess.list2cmdline([executable])} -m pytest -q'
