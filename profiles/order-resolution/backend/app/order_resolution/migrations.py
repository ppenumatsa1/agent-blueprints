import argparse
import hashlib
import os
from pathlib import Path

import psycopg

from app.infrastructure.migrations import upgrade as upgrade_base


ROOT = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION = ROOT / "0001_order_resolution_durability.sql"
MIGRATION_SHA256 = "09cf3a6023b6070828ba82ce8ab71a7ad966933ab0414ea2980b7eb5a06c32cf"
TABLES = (
    "order_resolution_requests",
    "order_resolution_proposals",
    "order_resolution_decisions",
    "order_resolution_effects",
    "order_resolution_synthetic_effects",
    "order_resolution_actions",
    "order_resolution_audit",
)


class OrderResolutionSchemaError(RuntimeError):
    pass


def _sql() -> str:
    value = MIGRATION.read_text(encoding="utf-8")
    if hashlib.sha256(value.encode("utf-8")).hexdigest() != MIGRATION_SHA256:
        raise OrderResolutionSchemaError("The Order Resolution migration has changed.")
    return value


def validate_connection(connection) -> None:
    missing = []
    for table in TABLES:
        row = connection.execute("SELECT to_regclass(%s) AS relation", (table,)).fetchone()
        relation = row["relation"] if isinstance(row, dict) else row[0]
        if relation is None:
            missing.append(table)
    if missing:
        raise OrderResolutionSchemaError(
            "The Order Resolution schema is not migrated: " + ", ".join(missing)
        )


def upgrade(dsn: str) -> None:
    upgrade_base(dsn)
    with psycopg.connect(dsn) as connection:
        schema = connection.execute("SELECT current_schema()").fetchone()[0]
        if not schema:
            raise OrderResolutionSchemaError("The database search path has no current schema.")
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(current_database() || ':' || %s, 1))",
            (schema,),
        )
        connection.execute(_sql())
        validate_connection(connection)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("upgrade",))
    parser.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL is required.")
    upgrade(dsn)


if __name__ == "__main__":
    main()
