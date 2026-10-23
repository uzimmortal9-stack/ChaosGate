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


def test_start_target_live_url(monkeypatch, tmp_path: Path):
    class DummyRes:
        status_code = 200

    monkeypatch.setattr(pipeline_service.httpx, "get", lambda url, **kw: DummyRes())
    cfg = {"services": {"api": {"url": "http://127.0.0.1:9099", "health": "/health"}}}
    target = pipeline_service._start_target(tmp_path, {}, cfg, None, lambda m: None)
    assert target is not None
    assert target["kind"] == "live_service"
    assert target["health"] == "http://127.0.0.1:9099/health"


def test_stage_chaos_traffic_burst(monkeypatch):
    class DummyRes:
        status_code = 200

    monkeypatch.setattr(pipeline_service.httpx, "get", lambda url, **kw: DummyRes())

    recorded_stages = []
    monkeypatch.setattr(pipeline_service, "_begin", lambda s, r, n: None)
    monkeypatch.setattr(
        pipeline_service,
        "_end",
        lambda s, r, st, status, summary, metrics=None: recorded_stages.append((status, summary, metrics)),
    )
    monkeypatch.setattr(pipeline_service, "_logger", lambda s, r, n: (lambda m: None))

    cfg = {"chaos": {"enabled": True, "experiments": ["traffic_burst"]}}
    runtime = {"health": "http://127.0.0.1:8000/health"}

    pipeline_service._stage_chaos(None, None, runtime, cfg, "test/repo")
    assert len(recorded_stages) == 1
    status, summary, metrics = recorded_stages[0]
    assert status == "passed"
    assert "Recovered from 1 experiment(s)" in summary
    assert metrics["experiments"][0]["experiment"] == "traffic_burst"


def test_stage_chaos_corrupt_requests(monkeypatch):
    class DummyRes:
        status_code = 200

    monkeypatch.setattr(pipeline_service.httpx, "get", lambda url, **kw: DummyRes())
    monkeypatch.setattr(pipeline_service.httpx, "post", lambda url, **kw: DummyRes())

    recorded_stages = []
    monkeypatch.setattr(pipeline_service, "_begin", lambda s, r, n: None)
    monkeypatch.setattr(
        pipeline_service,
        "_end",
        lambda s, r, st, status, summary, metrics=None: recorded_stages.append((status, summary, metrics)),
    )
    monkeypatch.setattr(pipeline_service, "_logger", lambda s, r, n: (lambda m: None))

    cfg = {"chaos": {"enabled": True, "experiments": ["corrupt_requests"]}}
    runtime = {"health": "http://127.0.0.1:8000/health"}

    pipeline_service._stage_chaos(None, None, runtime, cfg, "test/repo")
    assert len(recorded_stages) == 1
    status, summary, metrics = recorded_stages[0]
    assert status == "passed"
    assert metrics["experiments"][0]["experiment"] == "corrupt_requests"
