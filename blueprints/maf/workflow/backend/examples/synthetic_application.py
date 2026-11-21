import os

from psycopg import Connection

from app.application import ApplicationComponents
from app.domain.models import Case, StateRepository
from app.domain.policy import CaseAccessPolicy, JsonObjectRules


class SyntheticAction:
    def apply(self, connection: Connection, case: Case) -> None:
        connection.execute("INSERT INTO synthetic_effects (case_id) VALUES (%s)", (case.id,))


def prepare(store: StateRepository) -> None:
    with store.connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS synthetic_effects (
                case_id UUID PRIMARY KEY REFERENCES wf_cases(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def initialize(store: StateRepository) -> None:
    with store.connect() as connection:
        if connection.execute("SELECT to_regclass('synthetic_effects') AS name").fetchone()["name"] is None:
            raise RuntimeError("The synthetic example table is missing; run its preparation step.")


def build_application() -> ApplicationComponents:
    return ApplicationComponents(JsonObjectRules(), CaseAccessPolicy(), SyntheticAction(), initialize)


if __name__ == "__main__":
    from app.infrastructure.store import PostgresStore

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required.")
    prepare(PostgresStore(database_url))
