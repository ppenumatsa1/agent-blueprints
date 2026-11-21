"""Test-only second revision; never installed in the production migration path."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
schema_manifest_sha256 = "b331649821f422b30f06a4356de9cdcd49459bc20c79432bf1f50019c7c37419"


def upgrade():
    op.execute("ALTER TABLE wf_cases ADD COLUMN migration_marker text")
    op.execute("CREATE TABLE wf_future_fixture (id integer PRIMARY KEY)")


def downgrade():
    raise RuntimeError("The test revision has no automatic downgrade.")
