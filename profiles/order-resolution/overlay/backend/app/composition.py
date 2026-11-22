from fastapi import FastAPI

from app.api.app import create_api_app
from app.application import ApplicationComponents
from app.config import Settings
from app.domain.models import StateRepository
from app.infrastructure.delegation import OnBehalfOf
from app.infrastructure.identity import EntraIdentity, IdentityProvider
from app.infrastructure.store import PostgresStore
from app.infrastructure.telemetry import Telemetry
from app.lifecycle import create_lifespan
from app.order_resolution.host import OrderResolutionWorkflowHost
from app.order_resolution.persistence import OrderResolutionStore
from app.order_resolution.rules import OrderResolutionRules
from app.order_resolution.service import OrderResolutionService
from app.usecases.service import WorkflowService
from app.workflows.host import LocalWorkflowHost


def create_app(
    settings: Settings,
    components: ApplicationComponents,
    *,
    store: StateRepository | None = None,
    identity: IdentityProvider | None = None,
) -> FastAPI:
    order_resolution = isinstance(components.rules, OrderResolutionRules)
    repository = (
        store
        if store is not None
        else (
            OrderResolutionStore(settings.database_url)
            if order_resolution
            else PostgresStore(settings.database_url)
        )
    )
    identity_provider = identity if identity is not None else EntraIdentity(settings)
    telemetry = Telemetry(
        settings.telemetry_mode,
        settings.applicationinsights_connection_string,
    )
    try:
        host_type = OrderResolutionWorkflowHost if order_resolution else LocalWorkflowHost
        workflow_host = host_type(
            repository,
            components.action,
            settings.checkpoint_root,
            components.workflow_factory,
            telemetry=telemetry,
        )
        if isinstance(repository, PostgresStore):
            repository.telemetry = telemetry
        if order_resolution:
            if not isinstance(repository, OrderResolutionStore):
                raise TypeError("The Order Resolution persistence adapter is required.")
            service = OrderResolutionService(
                repository, workflow_host, components.rules, components.policy
            )
        else:
            service = WorkflowService(
                repository, workflow_host, components.rules, components.policy
            )
        lifespan = create_lifespan(repository, components, workflow_host, telemetry)
        return create_api_app(
            settings,
            service,
            identity_provider,
            OnBehalfOf(settings, telemetry=telemetry),
            lifespan,
            telemetry,
        )
    except BaseException:
        telemetry.shutdown()
        raise
