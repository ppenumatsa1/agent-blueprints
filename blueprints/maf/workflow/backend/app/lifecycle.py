import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.application import ApplicationComponents
from app.domain.errors import ActionError, BlueprintError, Conflict
from app.domain.models import StateRepository, WorkflowHost
from app.infrastructure.telemetry import Telemetry, _emit

logger = logging.getLogger("blueprint.lifecycle")


def create_lifespan(
    store: StateRepository,
    components: ApplicationComponents,
    host: WorkflowHost,
    telemetry: Telemetry | None = None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            store.initialize()
            components.initialize(store)
            for case_id, status in store.recoverable():
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
                except BlueprintError as exc:
                    store.mark_recovery_failed(case_id, "recovery_failed")
                    _emit("recovery", outcome="failure")
                    logger.error("Recovery failed (%s).", type(exc).__name__)
            yield
        finally:
            if telemetry is not None:
                telemetry.shutdown()

    return lifespan
