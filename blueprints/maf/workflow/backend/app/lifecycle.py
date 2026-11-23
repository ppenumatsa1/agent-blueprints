import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.application import ApplicationComponents
from app.domain.errors import ActionError, BlueprintError, Conflict, HostedWorkflowError
from app.domain.models import StateRepository, WorkflowHost
from app.infrastructure.telemetry import Telemetry, _emit

logger = logging.getLogger("blueprint.lifecycle")


def create_lifespan(
    store: StateRepository,
    components: ApplicationComponents,
    host: WorkflowHost,
    telemetry: Telemetry | None = None,
    *,
    close_store: bool = True,
    recover_workflows: bool = True,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            store.initialize()
            components.initialize(store)
            initializer = getattr(type(host), "initialize", None)
            if callable(initializer):
                initializer(host)
            recoverable = store.recoverable() if recover_workflows else ()
            for case_id, status in recoverable:
                try:
                    if status == "created":
                        await host.start(case_id)
                    else:
                        await host.resume(case_id)
                except Conflict:
                    _emit("recovery", outcome="conflict")
                    logger.warning("Recovery is already in progress.")
                except ActionError:
                    _emit("recovery", outcome="action_failure")
                    logger.error("The configured action failed during recovery.")
                except HostedWorkflowError:
                    _emit("recovery", outcome="hosted_unknown")
                    logger.error("Hosted workflow recovery remains unresolved.")
                except BlueprintError as exc:
                    store.mark_recovery_failed(case_id, "recovery_failed")
                    _emit("recovery", outcome="failure")
                    logger.error("Recovery failed (%s).", type(exc).__name__)
            yield
        finally:
            if close_store:
                close = getattr(store, "close", None)
                if callable(close):
                    close()
            if telemetry is not None:
                telemetry.shutdown()

    return lifespan
