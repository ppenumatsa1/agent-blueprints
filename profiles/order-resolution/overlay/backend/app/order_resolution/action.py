from psycopg import Connection

from app.domain.models import Case


class RecordOrderResolutionAction:
    """Record the approved synthetic outcome; no remote side effect is performed."""

    def apply(self, connection: Connection, case: Case) -> None:
        order = case.payload["order"]
        proposal = case.payload["proposal"]
        connection.execute(
            """
            INSERT INTO order_resolution_actions
                (case_id, proposal_version, order_id, action, amount, currency)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                case.id,
                proposal["version"],
                order["id"],
                proposal["action"],
                proposal.get("amount"),
                proposal.get("currency"),
            ),
        )
