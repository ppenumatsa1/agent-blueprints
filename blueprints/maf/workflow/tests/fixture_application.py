from psycopg import Connection

from app.models import Case


class FixtureAction:
    """A synthetic database-only effect, committed with the action ledger."""

    def __init__(self, fail: bool = False):
        self.fail = fail

    def apply(self, connection: Connection, case: Case) -> None:
        if self.fail:
            raise RuntimeError("Synthetic action failure.")
        connection.execute("INSERT INTO wf_fixture_effects (case_id) VALUES (%s)", (case.id,))


def initialize_fixture(store) -> None:
    with store.connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS wf_fixture_effects (
                case_id UUID PRIMARY KEY REFERENCES wf_cases(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def action_count(store, case_id) -> int:
    with store.connect() as connection:
        return connection.execute(
            "SELECT count(*) AS count FROM wf_fixture_effects WHERE case_id = %s", (case_id,)
        ).fetchone()["count"]
