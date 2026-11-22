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
from app.usecases.service import WorkflowService
from app.workflows.host import LocalWorkflowHost


def create_app(
    settings: Settings,
    components: ApplicationComponents,
    *,
    store: StateRepository | None = None,
    identity: IdentityProvider | None = None,
) -> FastAPI:
    repository = store if store is not None else PostgresStore(settings.database_url)
    identity_provider = identity if identity is not None else EntraIdentity(settings)
    telemetry = Telemetry(
        settings.telemetry_mode,
        settings.applicationinsights_connection_string,
        agent_version=settings.agent_version,
        deployment_revision=settings.deployment_revision,
    )
    try:
        workflow_host = LocalWorkflowHost(
            repository,
            components.action,
            settings.checkpoint_root,
            components.workflow_factory,
            telemetry=telemetry,
        )
        if isinstance(repository, PostgresStore):
            repository.telemetry = telemetry
        service = WorkflowService(repository, workflow_host, components.rules, components.policy)
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
