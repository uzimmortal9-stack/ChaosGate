"""Test bootstrap.

Environment is set before any `core` module is imported so the settings module
picks up a throwaway database and workspace root on first import. Reloading
SQLAlchemy models mid-session would re-register the tables, so the app is
built exactly once.
"""

from __future__ import annotations

import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="chaosgate_tests_")

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("WORKSPACES_DIR", f"{_TMP}/workspaces")
os.environ.setdefault("ARTIFACTS_DIR", f"{_TMP}/artifacts")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("GITHUB_CLIENT_ID", "")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "")
os.environ.setdefault("PROMETHEUS_URL", "")
os.environ.setdefault("GRAFANA_URL", "")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def flask_app():
    import app as app_mod

    application = app_mod.create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(flask_app):
    with flask_app.test_client() as c:
        yield c


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
