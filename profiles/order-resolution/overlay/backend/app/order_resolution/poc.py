import os
from uuid import UUID

from azure.identity import ManagedIdentityCredential
from psycopg import Connection

from app.domain.models import Principal


class ManagedIdentityOnly:
    def __init__(self, client_id: str) -> None:
        if not (os.environ.get("IDENTITY_ENDPOINT") and os.environ.get("IDENTITY_HEADER")):
            raise ValueError("POC self-decisions require the Container Apps MI endpoint.")
        self._credential = ManagedIdentityCredential(client_id=client_id)

    def get_token(self, scope: str) -> str:
        return self._credential.get_token(scope).token


def has_operator_entitlements(actor: Principal) -> bool:
    return {"Acceptance.Operator", "Workflow.Approver"} <= actor.roles and {
        "workflow.write",
        "workflow.approve",
    } <= actor.scopes


def operator_allowed(connection: Connection, actor: Principal) -> bool:
    if not has_operator_entitlements(actor):
        return False
    row = connection.execute(
        "SELECT ors_poc.operator_allowed(%s, %s, %s) AS permitted",
        (actor.tenant_id, actor.subject, connection.info.host),
    ).fetchone()
    return row is not None and row["permitted"] is True


def decision_allowed(
    connection: Connection,
    case_id: UUID,
    tenant_id: str,
    actor_id: str,
    decision: str,
    *,
    require_audit: bool,
) -> bool:
    row = connection.execute(
        "SELECT ors_poc.decision_allowed(%s, %s, %s, %s, %s, %s) AS permitted",
        (case_id, tenant_id, actor_id, decision, require_audit, connection.info.host),
    ).fetchone()
    return row is not None and row["permitted"] is True
