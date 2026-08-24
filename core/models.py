from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


def utcnow() -> datetime:
    """Naive UTC.

    The DateTime columns are timezone-less, so SQLite hands back naive values.
    Mixing those with aware ones raises at subtraction time, so every timestamp
    the app writes is normalised to naive UTC here and re-stamped as UTC when
    it is serialised out.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(20), default="demo")
    github_login: Mapped[str | None] = mapped_column(String(120), nullable=True)
    github_avatar: Mapped[str | None] = mapped_column(String(400), nullable=True)
    github_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    github_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_scopes: Mapped[str | None] = mapped_column(String(400), nullable=True)
    auth_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # oauth | pat
    policy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    repos: Mapped[list["Repository"]] = relationship(back_populates="workspace")


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"))
    owner: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(320))
    html_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    clone_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(120), default="main")
    language: Mapped[str | None] = mapped_column(String(60), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    # Local working copy
    workspace_cloned: Mapped[bool] = mapped_column(Boolean, default=False)
    workspace_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    workspace_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workspace_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Automation
    webhook_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workflow_installed: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_run_on_push: Mapped[bool] = mapped_column(Boolean, default=True)

    last_status: Mapped[str] = mapped_column(String(20), default="idle")
    last_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="repos")
    runs: Mapped[list["PipelineRun"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )
    pushes: Mapped[list["PushRecord"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan", order_by="PushRecord.created_at.desc()"
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    conclusion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trigger: Mapped[str] = mapped_column(String(40), default="manual")
    engine: Mapped[str] = mapped_column(String(40), default="local")
    branch: Mapped[str] = mapped_column(String(200), default="main")
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Post-merge recovery: set when a run fails on the default branch.
    recovery_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    incident_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    incident_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reverted_by: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    repo: Mapped[Repository] = relationship(back_populates="runs")
    stages: Mapped[list["Stage"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Stage.index"
    )
    events: Mapped[list["RunEvent"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunEvent.id"
    )


class Stage(Base):
    __tablename__ = "stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"))
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[str] = mapped_column(Text, default="")
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped[PipelineRun] = relationship(back_populates="stages")


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"))
    kind: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[PipelineRun] = relationship(back_populates="events")


class PushRecord(Base):
    """A commit ChaosGate pushed on the user's behalf from the folder editor."""

    __tablename__ = "push_records"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"))
    branch: Mapped[str] = mapped_column(String(200))
    base_branch: Mapped[str] = mapped_column(String(200), default="main")
    sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    files_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    strategy: Mapped[str] = mapped_column(String(20), default="branch_pr")
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pushed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    repo: Mapped[Repository] = relationship(back_populates="pushes")


class WebhookEvent(Base):
    """Inbound GitHub deliveries, so 'push activates the pipeline' is auditable."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event: Mapped[str] = mapped_column(String(60))
    repo_full_name: Mapped[str | None] = mapped_column(String(320), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(60), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
