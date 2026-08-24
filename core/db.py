from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker

from core.settings import DATA_DIR, DATABASE_URL

log = logging.getLogger("chaosgate.db")


class Base(DeclarativeBase):
    pass


DATA_DIR.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
)


def _sqlite_type(column) -> str:
    try:
        return column.type.compile(dialect=engine.dialect)
    except Exception:  # noqa: BLE001
        return "TEXT"


def _default_clause(column) -> str:
    default = column.default
    if default is None or getattr(default, "is_callable", False):
        return ""
    arg = getattr(default, "arg", None)
    if arg is None or callable(arg):
        return ""
    if isinstance(arg, bool):
        return f" DEFAULT {1 if arg else 0}"
    if isinstance(arg, (int, float)):
        return f" DEFAULT {arg}"
    if isinstance(arg, str):
        return f" DEFAULT '{arg}'"
    return ""


def migrate() -> None:
    """Additive schema migration.

    ChaosGate ships without Alembic on purpose — the schema only ever grows,
    so new nullable columns are added in place and existing local databases
    keep working across upgrades.
    """
    from core import models  # noqa: F401

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            current = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in current:
                    continue
                if not column.nullable and column.default is None and not column.primary_key:
                    # Cannot add a NOT NULL column without a default to a populated table.
                    log.warning("skipping non-nullable column %s.%s", table.name, column.name)
                    continue
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {_sqlite_type(column)}'
                ddl += _default_clause(column)
                try:
                    conn.execute(text(ddl))
                    log.info("migrated: added %s.%s", table.name, column.name)
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not add %s.%s: %s", table.name, column.name, exc)


def init_db() -> None:
    from core import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate()


def get_session():
    return SessionLocal()
