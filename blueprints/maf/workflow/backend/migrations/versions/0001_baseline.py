"""Adopt the original business schema without touching existing rows."""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = (Path(__file__).resolve().parents[1] / "baseline.sql").read_text(encoding="utf-8")
    op.get_bind().exec_driver_sql(sql)


def downgrade():
    raise RuntimeError("The baseline has no safe automatic downgrade; restore a verified backup.")
