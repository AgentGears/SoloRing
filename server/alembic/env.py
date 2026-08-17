"""Alembic environment (plan §103).

Migrations run synchronously; the async aiosqlite URL is converted to a sync
sqlite URL. ``render_as_batch=True`` gives safe SQLite structural changes, and
the target metadata uses the project naming convention so generated constraint
names are predictable.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import event, engine_from_config, pool

# Ensure the package is importable when alembic runs from server/.
from soloring.db.base import Base  # noqa: F401
from soloring.db import models  # noqa: F401  (registers tables on Base.metadata)
from soloring.db.sqlite import attach_sqlite_pragmas
from soloring.settings import get_settings

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: without this, fileConfig silently
    # disables every logger that existed before the migration ran — including
    # SoloRing application loggers when migrations execute in-process (tests,
    # programmatic upgrades). That would mute integrity/repair logging for the
    # rest of the process lifetime.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

log = logging.getLogger("alembic.env")

_settings = get_settings()
# Async URL -> sync URL for migration execution.
sync_url = _settings.resolved_database_url().replace("sqlite+aiosqlite", "sqlite")
config.set_main_option("sqlalchemy.url", sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # plan §103
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Apply the SAME SQLite configuration the application uses (plan §15), so
    # a freshly-migrated database is already WAL and the migration connection
    # has busy_timeout/synchronous set during batch operations.
    attach_sqlite_pragmas(connectable)

    # Foreign-key enforcement is DISABLED for the migration connection:
    # batch structural migrations (0007+) must be able to drop/recreate FK
    # parent tables. PRAGMA foreign_keys only takes effect OUTSIDE a
    # transaction, so it is overridden on the RAW DBAPI connection at
    # connect time (the same mechanism the shared hook uses) — executing it
    # on the SQLAlchemy connection before run_migrations would open a
    # transaction Alembic does not own and the migration DDL would roll
    # back. After every migration run, a full PRAGMA foreign_key_check audit
    # must come back clean or the migration FAILS — integrity loss on a
    # SUCCESSFUL run cannot hide. (A failing non-transactional DDL migration
    # is NOT atomic; migrations that can hit data-dependent DDL failures
    # must preflight representability before any DDL, as 0007's downgrade
    # does.)
    @event.listens_for(connectable, "connect")
    def _migrations_disable_fk(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=OFF")
        finally:
            cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # plan §103
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        violations = connection.exec_driver_sql(
            "PRAGMA foreign_key_check"
        ).fetchall()
    if violations:
        raise RuntimeError(
            f"migration left foreign-key violations: {violations!r}"
        )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
