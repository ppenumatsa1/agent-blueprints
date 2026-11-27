from psycopg import Connection

from app.domain.errors import Conflict
from app.domain.models import Case
from app.order_resolution.effects import EffectCoordinator, EffectRequest
from app.order_resolution.persistence import (
    OrderResolutionStore,
    PostgresSyntheticDestination,
)


class RecordOrderResolutionAction:
    """Reconcile one synthetic effect, then project its verified business outcome."""

    def __init__(
        self,
        store: OrderResolutionStore | None = None,
        destination: PostgresSyntheticDestination | None = None,
    ):
        self.store = store
        self.destination = destination

    def bind(self, store: OrderResolutionStore) -> "RecordOrderResolutionAction":
        return RecordOrderResolutionAction(store, PostgresSyntheticDestination(store))

    def apply(self, connection: Connection, case: Case) -> None:
        if self.store is None or self.destination is None:
            raise RuntimeError("The Order Resolution action is not bound to persistence.")
        proposal = self.store.get_current_proposal(str(case.id))
        decision = self.store.get_decision(case.id)
        self_review = case.owner_id == case.reviewer_id or proposal.owner_id == proposal.reviewer_id
        protected_self_decision = (
            self_review
            and decision is not None
            and type(self.destination) is PostgresSyntheticDestination
            and self.store.permits_poc_effect(connection, decision)
        )
        if self_review and not protected_self_decision:
            raise Conflict("A protected approval is required for a POC self-reviewed effect.")
        payload = {
            "order_id": case.payload["order"]["id"],
            "action": proposal.action,
            "amount": case.payload["proposal"].get("amount"),
            "currency": case.payload["proposal"].get("currency"),
        }
        request = EffectCoordinator(self.store, self.destination).apply(
            proposal,
            self.store.get_current_proposal(str(case.id)),
            decision,
            payload,
            protected_self_decision=protected_self_decision,
        )
        self._project(connection, case, request)

    @staticmethod
    def _project(connection: Connection, case: Case, request: EffectRequest) -> None:
        order = case.payload["order"]
        proposal = case.payload["proposal"]
        connection.execute(
            """
            INSERT INTO order_resolution_actions
                (case_id, proposal_version, order_id, action, destination_id,
                 effect_key, amount, currency)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                case.id,
                proposal["version"],
                order["id"],
                proposal["action"],
                proposal["destination_id"],
                request.key,
                proposal.get("amount"),
                proposal.get("currency"),
            ),
        )
        row = connection.execute(
            """
            SELECT order_id, effect_key, amount::text, currency
            FROM order_resolution_actions
            WHERE case_id = %s AND proposal_version = %s
                AND action = %s AND destination_id = %s
            """,
            (
                case.id,
                proposal["version"],
                proposal["action"],
                proposal["destination_id"],
            ),
        ).fetchone()
        expected_amount = proposal.get("amount")
        if row is None or (
            row["order_id"],
            row["effect_key"],
            row["amount"],
            row["currency"],
        ) != (order["id"], request.key, expected_amount, proposal.get("currency")):
            raise Conflict("The verified action projection conflicts with the proposal.")
