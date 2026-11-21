import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.application import ApplicationComponents
from app.domain.errors import ActionError, BlueprintError, Conflict
from app.domain.models import StateRepository, WorkflowHost

logger = logging.getLogger("blueprint.lifecycle")


def create_lifespan(
    store: StateRepository,
    components: ApplicationComponents,
    host: WorkflowHost,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        store.initialize()
        components.initialize(store)
        for case_id, status in store.recoverable():
            try:
                if status == "created":
                    await host.start(case_id)
                else:
                    await host.resume(case_id)
            except Conflict:
                logger.warning("Recovery is already in progress for case %s.", case_id)
            except ActionError:
                logger.error("The configured action failed during recovery for case %s.", case_id)
            except BlueprintError as exc:
                store.mark_recovery_failed(case_id, "recovery_failed")
                logger.error("Recovery failed for case %s (%s).", case_id, type(exc).__name__)
        yield

    return lifespan
