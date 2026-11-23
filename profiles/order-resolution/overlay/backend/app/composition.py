from importlib import import_module
from typing import cast

from fastapi import FastAPI

from app.api.app import create_api_app
from app.api.routes.hosted_service import router as hosted_service_router
from app.application import ApplicationComponents
from app.config import Settings
from app.domain.errors import HostedWorkflowError
from app.domain.models import StateRepository, WorkflowHost
from app.infrastructure.delegation import OnBehalfOf
from app.infrastructure.identity import EntraIdentity, IdentityProvider
from app.infrastructure.store import PostgresStore
from app.infrastructure.telemetry import Telemetry
from app.lifecycle import create_lifespan
from app.order_resolution.host import OrderResolutionWorkflowHost
from app.order_resolution.action import RecordOrderResolutionAction
from app.order_resolution.hosted_authority import PostgresHostedAuthorityBindings
from app.order_resolution.hosted_journal import PostgresOperationJournal
from app.order_resolution.persistence import OrderResolutionStore
from app.order_resolution.rules import OrderResolutionRules
from app.order_resolution.service import OrderResolutionService
from app.usecases.service import WorkflowService
from app.workflows.host import LocalWorkflowHost


def _build_hosted_workflow_host(
    settings: Settings,
    repository: OrderResolutionStore,
) -> WorkflowHost:
    try:
        module = import_module("order_resolution_hosted.bridge")
        factory = getattr(module, "build_workflow_host")
    except (AttributeError, ImportError) as exc:
        raise HostedWorkflowError(
            "Hosted mode requires the integrated Agent A Responses workflow adapter "
            "from the generated backend."
        ) from exc
    host = factory(
        settings,
        repository,
        PostgresHostedAuthorityBindings(repository),
        PostgresOperationJournal(repository),
    )
    return cast(WorkflowHost, host)


def create_app(
    settings: Settings,
    components: ApplicationComponents,
    *,
    store: StateRepository | None = None,
    identity: IdentityProvider | None = None,
    hosted_host: WorkflowHost | None = None,
) -> FastAPI:
    order_resolution = isinstance(components.rules, OrderResolutionRules)
    repository = (
        store
        if store is not None
        else (
            OrderResolutionStore.from_settings(settings)
            if order_resolution
            else PostgresStore.from_settings(settings)
        )
    )
    identity_provider = identity if identity is not None else EntraIdentity(settings)
    telemetry = Telemetry(
        settings.telemetry_mode,
        settings.applicationinsights_connection_string,
    )
    try:
        action = (
            components.action.bind(repository)
            if order_resolution and isinstance(components.action, RecordOrderResolutionAction)
            else components.action
        )
        if settings.host_mode == "local":
            host_type = OrderResolutionWorkflowHost if order_resolution else LocalWorkflowHost
            workflow_host = host_type(
                repository,
                action,
                settings.checkpoint_root,
                components.workflow_factory,
                telemetry=telemetry,
            )
        else:
            if not isinstance(repository, OrderResolutionStore):
                raise HostedWorkflowError(
                    "Hosted mode requires the integrated Agent A Responses workflow adapter "
                    "and Order Resolution PostgreSQL persistence."
                )
            workflow_host = hosted_host or _build_hosted_workflow_host(settings, repository)
        if isinstance(repository, PostgresStore):
            repository.telemetry = telemetry
        if order_resolution:
            if not isinstance(repository, OrderResolutionStore):
                raise TypeError("The Order Resolution persistence adapter is required.")
            service = OrderResolutionService(
                repository,
                workflow_host,
                components.rules,
                components.policy,
                hosted_mode=settings.host_mode == "hosted",
            )
        else:
            service = WorkflowService(
                repository, workflow_host, components.rules, components.policy
            )
        lifespan = create_lifespan(
            repository,
            components,
            workflow_host,
            telemetry,
            close_store=store is None,
            recover_workflows=settings.host_mode == "local",
        )
        return create_api_app(
            settings,
            service,
            identity_provider,
            OnBehalfOf(settings, telemetry=telemetry),
            lifespan,
            telemetry,
            additional_routers=(hosted_service_router,),
        )
    except BaseException:
        telemetry.shutdown()
        raise
