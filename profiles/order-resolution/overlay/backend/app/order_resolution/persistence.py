from uuid import UUID

from app.domain.errors import ActionError, Conflict, NotFound
from app.domain.models import TransactionalAction
from app.infrastructure.store import PostgresStore, _case


_CASE_FOR_UPDATE = """
    SELECT c.*, d.decision
    FROM wf_cases AS c
    LEFT JOIN wf_decisions AS d ON d.case_id = c.id
    WHERE c.id = %s
    FOR UPDATE OF c
"""


def _action_key(case) -> str:
    proposal = case.payload["proposal"]
    return (
        f"case:{case.id}:proposal:{proposal['version']}:"
        f"action:{proposal['action']}:order:{case.payload['order']['id']}"
    )


class OrderResolutionStore(PostgresStore):
    """Baseline application persistence layered on the copied PostgreSQL store."""

    def fail_resolution(self, case_id: UUID, code: str) -> None:
        if code not in (
            "policy_evidence_missing",
            "policy_evidence_conflict",
            "policy_evidence_invalid",
        ):
            raise ValueError("Unknown Order Resolution failure code.")
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE wf_cases SET status = 'failed', execution_complete = TRUE,
                    failure_code = %s, updated_at = now()
                WHERE id = %s AND status = 'created'
                """,
                (code, case_id),
            )
            if result.rowcount != 1:
                raise Conflict("The record is not ready for resolution failure.")
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'resolution_failed')",
                (case_id,),
            )

    def apply_automatic(self, case_id: UUID, action: TransactionalAction) -> None:
        with self.connect() as connection:
            row = connection.execute(_CASE_FOR_UPDATE, (case_id,)).fetchone()
            if row is None:
                raise NotFound("Record not found.")
            case = _case(row)
            proposal = case.payload.get("proposal", {})
            if proposal.get("approval_required") is not False:
                raise Conflict("The proposal requires a human decision.")
            ledger = connection.execute(
                "SELECT action_key FROM wf_action_ledger WHERE case_id = %s", (case_id,)
            ).fetchone()
            if ledger:
                if case.status != "completed":
                    raise Conflict("The action ledger and record state are inconsistent.")
                return
            if case.status != "created":
                raise Conflict("The record is not ready for automatic resolution.")
            try:
                action.apply(connection, case)
            except Exception as exc:
                raise ActionError("The configured action failed.") from exc
            connection.execute(
                "INSERT INTO wf_action_ledger (case_id, action_key) VALUES (%s, %s)",
                (case_id, _action_key(case)),
            )
            connection.execute(
                """
                UPDATE wf_cases SET status = 'completed', failure_code = NULL, updated_at = now()
                WHERE id = %s
                """,
                (case_id,),
            )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'automatic_action_applied')",
                (case_id,),
            )

    def apply_once(self, case_id: UUID, approved: bool, action: TransactionalAction) -> None:
        with self.connect() as connection:
            row = connection.execute(_CASE_FOR_UPDATE, (case_id,)).fetchone()
            if row is None:
                raise NotFound("Record not found.")
            case = _case(row)
            expected = "approved" if approved else "rejected"
            if case.decision != expected:
                raise Conflict("The workflow response does not match the recorded decision.")
            if not approved:
                if case.status != "rejected":
                    raise Conflict("The rejected record has an inconsistent state.")
                return
            if case.payload.get("proposal", {}).get("approval_required") is not True:
                raise Conflict("The proposal does not accept a human decision.")
            ledger = connection.execute(
                "SELECT action_key FROM wf_action_ledger WHERE case_id = %s", (case_id,)
            ).fetchone()
            if ledger:
                if case.status != "completed":
                    raise Conflict("The action ledger and record state are inconsistent.")
                return
            if case.status not in ("approved", "failed"):
                raise Conflict("The record is not ready for its action.")
            try:
                action.apply(connection, case)
            except Exception as exc:
                raise ActionError("The configured action failed.") from exc
            connection.execute(
                "INSERT INTO wf_action_ledger (case_id, action_key) VALUES (%s, %s)",
                (case_id, _action_key(case)),
            )
            connection.execute(
                """
                UPDATE wf_cases SET status = 'completed', failure_code = NULL, updated_at = now()
                WHERE id = %s
                """,
                (case_id,),
            )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'action_applied')",
                (case_id,),
            )

    def finish_automatic(self, case_id: UUID, terminal_checkpoint_id: str) -> None:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE wf_cases SET execution_complete = TRUE, terminal_checkpoint_id = %s,
                    failure_code = NULL, updated_at = now()
                WHERE id = %s AND status = 'completed'
                    AND NOT EXISTS (SELECT 1 FROM wf_decisions WHERE case_id = %s)
                """,
                (terminal_checkpoint_id, case_id, case_id),
            )
            if result.rowcount != 1:
                raise Conflict(
                    "The automatic workflow finished without a matching business outcome."
                )
            connection.execute(
                "INSERT INTO wf_audit (case_id, event) VALUES (%s, 'workflow_finished')",
                (case_id,),
            )
