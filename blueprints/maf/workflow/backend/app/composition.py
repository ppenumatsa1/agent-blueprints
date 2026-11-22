from fastapi import FastAPI

from app.api.app import create_api_app
from app.application import ApplicationComponents
from app.config import Settings
from app.domain.models import StateRepository
from app.infrastructure.delegation import OnBehalfOf
from app.infrastructure.database import DefaultAzureCredentialTokenProvider
from app.infrastructure.hosted import HostedWorkflowClient, HttpHostedWorkflowClient
from app.infrastructure.identity import EntraIdentity, IdentityProvider
from app.infrastructure.store import PostgresStore
from app.infrastructure.telemetry import Telemetry
from app.lifecycle import create_lifespan
from app.usecases.service import WorkflowService
from app.workflows.host import LocalWorkflowHost
from app.workflows.hosted import HostedWorkflowHost


def create_app(
    settings: Settings,
    components: ApplicationComponents,
    *,
    store: StateRepository | None = None,
    identity: IdentityProvider | None = None,
    hosted_client: HostedWorkflowClient | None = None,
) -> FastAPI:
    repository = store if store is not None else PostgresStore.from_settings(settings)
    identity_provider = identity if identity is not None else EntraIdentity(settings)
    telemetry = Telemetry(
        settings.telemetry_mode,
        settings.applicationinsights_connection_string,
    )
    try:
        if settings.host_mode == "local":
            workflow_host = LocalWorkflowHost(
                repository,
                components.action,
                settings.checkpoint_root,
                components.workflow_factory,
                telemetry=telemetry,
            )
        else:
            token_provider = DefaultAzureCredentialTokenProvider(
                settings.api_managed_identity_client_id
            )
            workflow_host = HostedWorkflowHost(
                repository,
                components.action,
                hosted_client
                or HttpHostedWorkflowClient(
                    settings.hosted_workflow_endpoint or "",
                    settings.hosted_workflow_scope or "",
                    token_provider,
                ),
                telemetry=telemetry,
            )
        if isinstance(repository, PostgresStore):
            repository.telemetry = telemetry
        service = WorkflowService(repository, workflow_host, components.rules, components.policy)
        lifespan = create_lifespan(
            repository,
            components,
            workflow_host,
            telemetry,
            close_store=store is None,
        )
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
