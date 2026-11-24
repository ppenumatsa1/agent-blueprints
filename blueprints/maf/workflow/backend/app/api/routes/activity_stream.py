import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.api.dependencies import current_identity, workflow_service
from app.domain.errors import AccessDenied, AuthenticationFailed, BlueprintError, NotFound
from app.infrastructure.identity import AuthenticatedRequest
from app.usecases.history import decode_activity_cursor
from app.usecases.service import WorkflowService

router = APIRouter(tags=["cases"])

STREAM_SECONDS = 30
HEARTBEAT_SECONDS = 5


@router.get("/cases/{case_id}/activity/stream")
async def activity_stream(
    case_id: UUID,
    request: Request,
    actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    service: Annotated[WorkflowService, Depends(workflow_service)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID", max_length=512)] = None,
) -> StreamingResponse:
    # A previous pagination cursor is never a commit watermark: reconnects rescan.
    decode_activity_cursor(last_event_id)
    await run_in_threadpool(service.activity, actor.principal, case_id, cursor=None, limit=1)

    async def events() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STREAM_SECONDS
        for _ in range(int(STREAM_SECONDS / HEARTBEAT_SECONDS)):
            try:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return
                current = await asyncio.wait_for(
                    run_in_threadpool(request.app.state.identity.authenticate, actor.access_token),
                    timeout=remaining,
                )
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return
                await asyncio.wait_for(
                    run_in_threadpool(
                        service.activity, current.principal, case_id, cursor=None, limit=1
                    ),
                    timeout=remaining,
                )
            except TimeoutError:
                yield "event: retry\ndata: {}\n\n"
                return
            except (AccessDenied, AuthenticationFailed, NotFound):
                yield "event: unavailable\ndata: {}\n\n"
                return
            except BlueprintError:
                yield "event: retry\ndata: {}\n\n"
                return
            yield "event: activity.refresh\ndata: {}\n\n: heartbeat\n\n"
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(HEARTBEAT_SECONDS, remaining))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
