from psycopg import Connection

from app.application import ApplicationComponents
from app.domain.models import Case, StateRepository
from app.domain.policy import CaseAccessPolicy, JsonObjectRules


class SyntheticAction:
    def apply(self, connection: Connection, case: Case) -> None:
        connection.execute("INSERT INTO synthetic_effects (case_id) VALUES (%s)", (case.id,))


def initialize(store: StateRepository) -> None:
    with store.connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS synthetic_effects (
                case_id UUID PRIMARY KEY REFERENCES wf_cases(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def build_application() -> ApplicationComponents:
    return ApplicationComponents(JsonObjectRules(), CaseAccessPolicy(), SyntheticAction(), initialize)
