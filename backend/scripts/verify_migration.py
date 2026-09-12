"""Verify a migration is reversible, on SQLite and on Postgres (CLAUDE.md §9.1).

Runs `upgrade → downgrade → upgrade` against a throwaway database of each dialect and compares
schema snapshots, so an asymmetric or lossy migration fails here rather than on a developer's
database. SQLite alone is not enough: it does not enforce VARCHAR lengths, has no native ENUM,
and rewrites tables for `batch_alter_table` — the differences that have already hidden one defect.

Usage, from the repository root:

    backend/.venv/Scripts/python.exe backend/scripts/verify_migration.py
    ... --seed backend/scripts/seeds/0012_website_integrations.py   # rows that exist pre-migration
    ... --revision head --dialect both

A seed module exposes `seed(connection)` and is applied at the *previous* revision, so backfills
run against real rows. Write one whenever a migration backfills or alters existing data.

Postgres requires a `fussion_migcheck` role (`LOGIN CREATEDB`, not superuser) whose password is in
libpq's password file. This script never reads `backend/.env`, never touches `fussion_db`, and
never prints a connection string.
"""

import argparse
import asyncio
import importlib.util
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    # psycopg's async path cannot run on the Proactor loop, and alembic's env.py calls asyncio.run.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
PG_ROLE = "fussion_migcheck"
PG_HOST = "localhost"
PG_PORT = 5432


def _pg_url(database: str) -> str:
    """SQLAlchemy URL for the scratch database. The psycopg dialect serves both the async engine
    alembic uses and the sync engine the snapshots use, so one form covers both. The password
    comes from libpq's password file and never appears here."""
    return f"postgresql+psycopg://{PG_ROLE}@{PG_HOST}:{PG_PORT}/{database}"


def _snapshot(engine: sa.Engine) -> dict[str, Any]:
    """Schema plus row counts, in a form two runs can be compared field by field."""
    inspector = sa.inspect(engine)
    snapshot: dict[str, Any] = {}
    with engine.connect() as conn:
        for table in sorted(inspector.get_table_names()):
            if table == "alembic_version":
                continue
            columns = {
                column["name"]: {
                    "type": str(column["type"]),
                    "nullable": bool(column["nullable"]),
                }
                for column in inspector.get_columns(table)
            }
            indexes = {
                index["name"]: {
                    "columns": list(index["column_names"]),
                    "unique": bool(index.get("unique")),
                }
                for index in inspector.get_indexes(table)
            }
            uniques = {
                constraint.get("name"): sorted(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(table)
            }
            snapshot[table] = {
                "columns": columns,
                "indexes": indexes,
                "unique_constraints": uniques,
                "rows": conn.execute(sa.text(f'SELECT count(*) FROM "{table}"')).scalar_one(),
            }
    return snapshot


def _differences(expected: dict[str, Any], actual: dict[str, Any], path: str = "") -> list[str]:
    if expected == actual:
        return []
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        return [f"{path}: expected {expected!r}, found {actual!r}"]
    found: list[str] = []
    for key in sorted(set(expected) | set(actual)):
        where = f"{path}.{key}" if path else str(key)
        if key not in expected:
            found.append(f"{where}: unexpectedly present ({actual[key]!r})")
        elif key not in actual:
            found.append(f"{where}: missing (was {expected[key]!r})")
        else:
            found.extend(_differences(expected[key], actual[key], where))
    return found


def _load_seed(path: Path):
    spec = importlib.util.spec_from_file_location("migration_seed", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load seed module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "seed"):
        raise SystemExit(f"Seed module {path} must define seed(connection)")
    return module.seed


def _alembic_config(async_url: str):
    from alembic.config import Config

    os.environ["APP_ENV"] = "development"
    os.environ["DATABASE_URL"] = async_url
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.attributes["configure_logger"] = False
    return config


def _previous_revision(config, revision: str) -> str:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    head = script.get_revision(revision)
    if head is None or not head.down_revision:
        raise SystemExit(f"{revision} has no previous revision to downgrade to")
    down = head.down_revision
    return down if isinstance(down, str) else down[0]


def verify(dialect: str, async_url: str, sync_url: str, revision: str, seed: Any) -> None:
    from alembic import command

    config = _alembic_config(async_url)
    previous = _previous_revision(config, revision)
    print(f"[{dialect}] previous revision: {previous}", flush=True)

    engine = sa.create_engine(sync_url)
    try:
        command.upgrade(config, previous)
        if seed is not None:
            with engine.begin() as conn:
                seed(conn)
            print(f"[{dialect}] seeded rows at {previous}", flush=True)
        before = _snapshot(engine)

        command.upgrade(config, revision)
        after_first = _snapshot(engine)
        if after_first == before:
            raise SystemExit(f"[{dialect}] FAIL: upgrading to {revision} changed nothing")

        command.downgrade(config, previous)
        reverted = _snapshot(engine)
        if diffs := _differences(before, reverted):
            raise SystemExit(
                f"[{dialect}] FAIL: downgrade did not restore {previous}:\n  "
                + "\n  ".join(diffs)
            )

        command.upgrade(config, revision)
        if diffs := _differences(after_first, _snapshot(engine)):
            raise SystemExit(
                f"[{dialect}] FAIL: re-upgrade differs from the first upgrade:\n  "
                + "\n  ".join(diffs)
            )
    finally:
        engine.dispose()
    print(f"[{dialect}] OK: upgrade -> downgrade -> upgrade is reversible and repeatable", flush=True)


def _run_worker(dialect: str, async_url: str, sync_url: str, revision: str, seed: Path | None) -> None:
    """Run one dialect in a fresh interpreter.

    `app.core.config` builds its Settings at import and alembic's env.py reads it, so a second
    dialect in the same process would silently migrate the first dialect's database.
    """
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        dialect,
        async_url,
        sync_url,
        "--revision",
        revision,
    ]
    if seed is not None:
        command += ["--seed", str(seed)]
    # check=False: the worker's own message is the useful output, so exit with its status rather
    # than raising CalledProcessError over it.
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def verify_sqlite(revision: str, seed: Path | None) -> None:
    directory = Path(tempfile.mkdtemp(prefix="fussion-migcheck-"))
    database = (directory / "migcheck.db").as_posix()
    try:
        _run_worker(
            "sqlite", f"sqlite+aiosqlite:///{database}", f"sqlite:///{database}", revision, seed
        )
    finally:
        for leftover in directory.glob("*"):
            leftover.unlink(missing_ok=True)
        directory.rmdir()


def verify_postgres(revision: str, seed: Path | None) -> None:
    import psycopg
    from psycopg import sql

    database = f"fussion_migcheck_{secrets.token_hex(4)}"
    admin = f"postgresql://{PG_ROLE}@{PG_HOST}:{PG_PORT}/postgres"
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=10) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    except psycopg.OperationalError as exc:
        raise SystemExit(
            f"Cannot reach Postgres as {PG_ROLE}: {exc}\n"
            f"Expected a {PG_ROLE} role (LOGIN CREATEDB) with its password in libpq's password "
            "file. Run with --dialect sqlite to skip Postgres, and say so in the tracker entry."
        ) from None

    print(f"[postgres] scratch database {database}", flush=True)
    try:
        _run_worker("postgres", _pg_url(database), _pg_url(database), revision, seed)
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(
                sql.SQL("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = {}")
                .format(sql.Literal(database))
            )
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
        print(f"[postgres] dropped {database}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="head", help="revision to verify (default: head)")
    parser.add_argument("--dialect", choices=("both", "sqlite", "postgres"), default="both")
    parser.add_argument("--seed", type=Path, help="module defining seed(connection)")
    parser.add_argument(
        "--worker",
        nargs=3,
        metavar=("DIALECT", "ASYNC_URL", "SYNC_URL"),
        help=argparse.SUPPRESS,  # internal: one dialect, in its own interpreter
    )
    args = parser.parse_args()

    os.chdir(REPO_ROOT)  # Settings load .env from the cwd; the repository root has none.
    sys.path.insert(0, str(BACKEND))

    if args.worker:
        dialect, async_url, sync_url = args.worker
        verify(dialect, async_url, sync_url, args.revision, _load_seed(args.seed) if args.seed else None)
        return

    if args.dialect in ("both", "sqlite"):
        verify_sqlite(args.revision, args.seed)
    if args.dialect in ("both", "postgres"):
        verify_postgres(args.revision, args.seed)
    print("\nAll requested dialects verified.")


if __name__ == "__main__":
    main()
