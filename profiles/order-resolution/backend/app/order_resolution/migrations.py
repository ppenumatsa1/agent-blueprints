import argparse
import hashlib
import os
from pathlib import Path

import psycopg

from app.infrastructure.migrations import upgrade as upgrade_base


ROOT = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION = ROOT / "0001_order_resolution_durability.sql"
MIGRATION_SHA256 = "09cf3a6023b6070828ba82ce8ab71a7ad966933ab0414ea2980b7eb5a06c32cf"
HOSTED_MIGRATION = ROOT / "0002_order_resolution_hosted_identity.sql"
HOSTED_MIGRATION_SHA256 = "b68932f657dc13a771a399acecedac7840378b3e8bf1c51c13a8f58db9415b6f"
TABLES = (
    "order_resolution_requests",
    "order_resolution_proposals",
    "order_resolution_decisions",
    "order_resolution_effects",
    "order_resolution_synthetic_effects",
    "order_resolution_actions",
    "order_resolution_audit",
    "order_resolution_hosted_operations",
    "order_resolution_hosted_bindings",
)


class OrderResolutionSchemaError(RuntimeError):
    pass


def _sql() -> str:
    value = MIGRATION.read_text(encoding="utf-8")
    if hashlib.sha256(value.encode("utf-8")).hexdigest() != MIGRATION_SHA256:
        raise OrderResolutionSchemaError("The Order Resolution migration has changed.")
    return value


def _hosted_sql() -> str:
    value = HOSTED_MIGRATION.read_text(encoding="utf-8")
    if hashlib.sha256(value.encode("utf-8")).hexdigest() != HOSTED_MIGRATION_SHA256:
        raise OrderResolutionSchemaError("The hosted identity migration has changed.")
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


def upgrade(dsn: str, *, connect=None) -> None:
    upgrade_base(dsn, connect=connect)
    with (connect or (lambda: psycopg.connect(dsn)))() as connection:
        schema = connection.execute("SELECT current_schema()").fetchone()[0]
        if not schema:
            raise OrderResolutionSchemaError("The database search path has no current schema.")
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(current_database() || ':' || %s, 1))",
            (schema,),
        )
        connection.execute(_sql())
        connection.execute(_hosted_sql())
        validate_connection(connection)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("upgrade",))
    parser.parse_args()
    dsn = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("MIGRATION_DATABASE_URL or DATABASE_URL is required.")
    from app.infrastructure.database import connector_from_environment

    connector = connector_from_environment(dsn)
    upgrade(dsn, connect=lambda: connector.connect(dict_rows=False))


if __name__ == "__main__":
    main()
