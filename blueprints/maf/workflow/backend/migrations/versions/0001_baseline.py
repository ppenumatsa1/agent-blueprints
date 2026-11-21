"""Adopt the original business schema without touching existing rows."""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
schema_manifest_sha256 = "706771476076cb44546c7761fabfcb0282b85cbd823d2b28b894032628f8bd70"


def upgrade():
    sql = (Path(__file__).resolve().parents[1] / "baseline.sql").read_text(encoding="utf-8")
    op.get_bind().exec_driver_sql(sql)


def downgrade():
    raise RuntimeError("The baseline has no safe automatic downgrade; restore a verified backup.")
