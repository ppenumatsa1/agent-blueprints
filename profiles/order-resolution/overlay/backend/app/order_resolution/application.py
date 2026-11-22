from app.application import ApplicationComponents
from app.domain.policy import CaseAccessPolicy
from app.order_resolution.action import RecordOrderResolutionAction
from app.order_resolution.rules import OrderResolutionRules
from app.order_resolution.workflow import build_order_resolution_workflow


def initialize(store) -> None:
    with store.connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS order_resolution_actions (
                case_id UUID PRIMARY KEY REFERENCES wf_cases(id),
                proposal_version INTEGER NOT NULL,
                order_id TEXT NOT NULL,
                action TEXT NOT NULL,
                amount NUMERIC(18, 2),
                currency TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def build_application() -> ApplicationComponents:
    return ApplicationComponents(
        rules=OrderResolutionRules(),
        policy=CaseAccessPolicy(),
        action=RecordOrderResolutionAction(),
        initialize=initialize,
        workflow_factory=build_order_resolution_workflow,
    )
