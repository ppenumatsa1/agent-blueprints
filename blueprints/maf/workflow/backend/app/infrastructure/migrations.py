"""Versioned business schema initialization and conservative baseline adoption."""

import hashlib
from pathlib import Path
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


ROOT = Path(__file__).resolve().parents[2] / "migrations"
BASELINE_HASH = "62cfe442c655d149d773b41f18d5ae43288881eb0f63236023cbbb8342c349ce"
TABLES = ("wf_cases", "wf_decisions", "wf_action_ledger", "wf_audit")


class SchemaDriftError(RuntimeError):
    """The business schema cannot safely be adopted or used."""


def _snapshot(connection, schema):
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
    return tuple(tuple(connection.exec_driver_sql(query, (schema, list(TABLES))).all()) for query in queries)


def upgrade(dsn):
    baseline = (ROOT / "baseline.sql").read_text(encoding="utf-8")
    if hashlib.sha256(baseline.encode("utf-8")).hexdigest() != BASELINE_HASH:
        raise SchemaDriftError("The immutable baseline migration has changed.")

    # Psycopg URLs are supplied by the existing application; do not log them.
    engine = create_engine("postgresql+psycopg://", creator=lambda: psycopg.connect(dsn), poolclass=NullPool)
    try:
        with engine.begin() as connection:
            schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
            if not schema:
                raise SchemaDriftError("The database search path has no current schema.")
            connection.exec_driver_sql(
                "SELECT pg_advisory_xact_lock(hashtextextended(current_database() || ':' || %s, 0))",
                (schema,),
            )
            actual = _snapshot(connection, schema)
            present = len(actual[0])
            if present not in (0, len(TABLES)):
                raise SchemaDriftError("The business schema is incomplete; restore or repair it before retrying.")

            reference = "wf_baseline_" + uuid4().hex
            quoted = connection.dialect.identifier_preparer.quote(reference)
            connection.exec_driver_sql(f"CREATE SCHEMA {quoted}")
            connection.exec_driver_sql("SELECT set_config('search_path', quote_ident(%s), true)", (reference,))
            connection.exec_driver_sql(baseline)
            expected = _snapshot(connection, reference)
            connection.exec_driver_sql(f"DROP SCHEMA {quoted} CASCADE")
            connection.exec_driver_sql("SELECT set_config('search_path', quote_ident(%s), true)", (schema,))
            if present and actual != expected:
                raise SchemaDriftError("The business schema differs from the supported baseline.")
            if not present and connection.exec_driver_sql(
                "SELECT to_regclass('alembic_version') IS NOT NULL"
            ).scalar_one():
                raise SchemaDriftError("Version metadata exists without the business schema.")

            config = Config()
            config.set_main_option("script_location", str(ROOT).replace("%", "%%"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            if _snapshot(connection, schema) != expected:
                raise SchemaDriftError("The migrated schema differs from the supported baseline.")
    finally:
        engine.dispose()
