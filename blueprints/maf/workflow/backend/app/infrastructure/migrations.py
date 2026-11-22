"""Versioned business schema initialization and conservative baseline adoption."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


ROOT = Path(__file__).resolve().parents[2] / "migrations"
BASELINE_HASH = "62cfe442c655d149d773b41f18d5ae43288881eb0f63236023cbbb8342c349ce"


class SchemaDriftError(RuntimeError):
    """The business schema cannot safely be adopted or used."""


def _snapshot(connection, schema, tables):
    connection.exec_driver_sql("SELECT set_config('search_path', quote_ident(%s), true)", (schema,))
    queries = (
        """SELECT c.relname, c.relkind, c.relpersistence, c.relrowsecurity, c.relforcerowsecurity,
                  c.relispartition, c.relreplident, c.reloptions
           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=%s AND c.relname = ANY(%s) ORDER BY 1""",
        """SELECT c.relname, a.attnum, a.attname, format_type(a.atttypid,a.atttypmod),
                  a.attnotnull, a.attidentity, a.attgenerated,
                  pg_get_expr(d.adbin,d.adrelid), a.attcollation::regcollation::text
           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           JOIN pg_attribute a ON a.attrelid=c.oid
           LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
           WHERE n.nspname=%s AND c.relname = ANY(%s) AND a.attnum>0 AND NOT a.attisdropped
           ORDER BY 1,2""",
        """SELECT c.relname, k.conname, k.contype, k.convalidated, pg_get_constraintdef(k.oid)
           FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=%s AND c.relname = ANY(%s) ORDER BY 1,2""",
        """SELECT c.relname, i.relname, x.indisvalid, x.indisready,
                  replace(pg_get_indexdef(i.oid), quote_ident(n.nspname) || '.', '')
           FROM pg_index x JOIN pg_class c ON c.oid=x.indrelid JOIN pg_class i ON i.oid=x.indexrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=%s AND c.relname = ANY(%s) ORDER BY 1,2""",
        """SELECT c.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid)
           FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=%s AND c.relname = ANY(%s) AND NOT t.tgisinternal ORDER BY 1,2""",
        """SELECT c.relname, p.polname, p.polcmd, p.polpermissive, p.polroles::text,
                  pg_get_expr(p.polqual,p.polrelid), pg_get_expr(p.polwithcheck,p.polrelid)
           FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=%s AND c.relname = ANY(%s) ORDER BY 1,2""",
        """SELECT c.relname, r.rulename, r.ev_enabled, pg_get_ruledef(r.oid)
           FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=%s AND c.relname = ANY(%s) ORDER BY 1,2""",
        """SELECT c.relname, parent.oid::regclass::text
           FROM pg_inherits h JOIN pg_class c ON c.oid=h.inhrelid
           JOIN pg_class parent ON parent.oid=h.inhparent
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=%s AND c.relname = ANY(%s) ORDER BY 1,2""",
        """SELECT c.relname, child.oid::regclass::text
           FROM pg_inherits h JOIN pg_class c ON c.oid=h.inhparent
           JOIN pg_class child ON child.oid=h.inhrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=%s AND c.relname = ANY(%s) ORDER BY 1,2""",
        """SELECT c.relname, a.attname, s.seqtypid::regtype::text, s.seqstart,
                  s.seqincrement, s.seqmax, s.seqmin, s.seqcache, s.seqcycle
           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           JOIN pg_attribute a ON a.attrelid=c.oid AND a.attidentity <> ''
           JOIN pg_depend d ON d.refobjid=c.oid AND d.refobjsubid=a.attnum
                           AND d.classid='pg_class'::regclass AND d.deptype='i'
           JOIN pg_sequence s ON s.seqrelid=d.objid
           WHERE n.nspname=%s AND c.relname = ANY(%s) ORDER BY 1,2""",
    )
    return [
        [list(row) for row in connection.exec_driver_sql(query, (schema, list(tables))).all()]
        for query in queries
    ]


def _manifest(root, revision):
    text = (root / "manifests" / f"{revision.revision}.json").read_text(encoding="utf-8")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != revision.module.schema_manifest_sha256:
        raise SchemaDriftError(f"The manifest for revision {revision.revision} has changed.")
    manifest = json.loads(text)
    if not manifest["tables"] or len(set(manifest["tables"])) != len(manifest["tables"]):
        raise SchemaDriftError("Invalid migration manifest table list.")
    return manifest


def _config(root, connection):
    config = Config()
    config.set_main_option("script_location", str(root).replace("%", "%%"))
    config.attributes["connection"] = connection
    return config


def _check_baseline(root):
    baseline = (root / "baseline.sql").read_text(encoding="utf-8")
    if hashlib.sha256(baseline.encode("utf-8")).hexdigest() != BASELINE_HASH:
        raise SchemaDriftError("The immutable baseline migration has changed.")


def _run(dsn, root, migrate):
    _check_baseline(root)
    engine = create_engine(
        "postgresql+psycopg://", creator=lambda: psycopg.connect(dsn), poolclass=NullPool
    )
    try:
        with engine.begin() as connection:
            schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
            if not schema:
                raise SchemaDriftError("The database search path has no current schema.")
            lock = "pg_advisory_xact_lock" if migrate else "pg_advisory_xact_lock_shared"
            connection.exec_driver_sql(
                f"SELECT {lock}(hashtextextended(current_database() || ':' || %s, 0))", (schema,)
            )
            connection.exec_driver_sql(
                "SELECT set_config('search_path', quote_ident(%s), true)", (schema,)
            )
            config = _config(root, connection)
            scripts = ScriptDirectory.from_config(config)
            head = scripts.get_current_head()
            if not head:
                raise SchemaDriftError("No migration head is configured.")
            manifests = {
                revision.revision: _manifest(root, revision)
                for revision in scripts.walk_revisions()
            }
            owned_tables = {
                table for manifest in manifests.values() for table in manifest["tables"]
            }
            version_exists = connection.exec_driver_sql(
                "SELECT to_regclass('alembic_version') IS NOT NULL"
            ).scalar_one()
            if version_exists:
                versions = (
                    connection.exec_driver_sql("SELECT version_num FROM alembic_version")
                    .scalars()
                    .all()
                )
                if len(versions) != 1:
                    raise SchemaDriftError(
                        "Migration version metadata must contain exactly one revision."
                    )
                current = versions[0]
                revision = scripts.get_revision(current)
                if revision is None:
                    raise SchemaDriftError("Unknown migration revision.")
                manifest = manifests[revision.revision]
                adopt_baseline = False
                if _snapshot(connection, schema, manifest["tables"]) != manifest["snapshot"]:
                    raise SchemaDriftError(f"The business schema differs from revision {current}.")
            else:
                current = None
                baseline = manifests["0001"]
                actual = _snapshot(connection, schema, baseline["tables"])
                if actual[0] and actual != baseline["snapshot"]:
                    raise SchemaDriftError(
                        "The unversioned business schema differs from the supported baseline."
                    )
                manifest = baseline
                adopt_baseline = bool(actual[0])
            unexpected = owned_tables.difference(manifest["tables"])
            if unexpected and _snapshot(connection, schema, sorted(unexpected))[0]:
                raise SchemaDriftError("A table owned by another revision already exists.")
            if not migrate:
                if current != head:
                    raise SchemaDriftError(
                        "Database is not at the required migration head; run the migration job."
                    )
                return
            if adopt_baseline:
                command.stamp(config, "0001")
                current = "0001"
            if current != head:
                command.upgrade(config, "head")
            expected = manifests[head]
            if _snapshot(connection, schema, expected["tables"]) != expected["snapshot"]:
                raise SchemaDriftError(f"The migrated schema differs from revision {head}.")
    finally:
        engine.dispose()


def upgrade(dsn, *, root=ROOT):
    """Run migrations explicitly using a schema-owner identity."""
    _run(dsn, root, True)


def validate(dsn, *, root=ROOT):
    """Validate the current head without schema or version-table writes."""
    _run(dsn, root, False)


def main():
    parser = argparse.ArgumentParser(
        description="Upgrade the business database to the reviewed migration head."
    )
    parser.add_argument("action", choices=("upgrade",))
    parser.parse_args()
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL is required.")
    upgrade(dsn)


if __name__ == "__main__":
    main()
