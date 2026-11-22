from app.application import ApplicationComponents
from app.domain.policy import CaseAccessPolicy
from app.order_resolution.action import RecordOrderResolutionAction
from app.order_resolution.migrations import validate_connection
from app.order_resolution.rules import OrderResolutionRules
from app.order_resolution.workflow import build_order_resolution_workflow


def initialize(store) -> None:
    with store.connect() as connection:
        validate_connection(connection)


def build_application() -> ApplicationComponents:
    return ApplicationComponents(
        rules=OrderResolutionRules(),
        policy=CaseAccessPolicy(),
        action=RecordOrderResolutionAction(),
        initialize=initialize,
        workflow_factory=build_order_resolution_workflow,
    )
