import asyncio
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import bearer
from app.domain.errors import AccessDenied, AuthenticationFailed, BlueprintError, NotFound
from app.infrastructure.database import BoundedConnectionPool
from app.infrastructure.identity import AuthenticatedRequest
from app.infrastructure.store import PostgresStore
from app.usecases.history import decode_activity_cursor
from app.usecases.service import WorkflowService

router = APIRouter(tags=["cases"])

STREAM_SECONDS = 30
HEARTBEAT_SECONDS = 5
ACTIVITY_STREAM_WORKERS = 4
MAX_CONCURRENT_ACTIVITY_STREAMS = 32
_T = TypeVar("_T")


class ActivityStreamCapacityError(Exception):
    pass


class ActivityStreamRuntime:
    """Keep synchronous stream work isolated and bounded from API request workers."""

    def __init__(
        self,
        *,
        workers: int = ACTIVITY_STREAM_WORKERS,
        max_streams: int = MAX_CONCURRENT_ACTIVITY_STREAMS,
    ):
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="activity-stream",
        )
        self._worker_slots = BoundedSemaphore(workers)
        self._stream_slots = BoundedSemaphore(max_streams)

    def try_acquire_stream(self) -> bool:
        return self._stream_slots.acquire(blocking=False)

    def release_stream(self) -> None:
        self._stream_slots.release()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)

    async def call(
        self,
        function: Callable[..., _T],
        *args: object,
        timeout: float,
        **kwargs: object,
    ) -> _T:
        if not self._worker_slots.acquire(blocking=False):
            raise ActivityStreamCapacityError()
        try:
            future: Future[_T] = self._executor.submit(function, *args, **kwargs)
        except BaseException:
            self._worker_slots.release()
            raise

        def release_worker(completed: Future[_T]) -> None:
            self._worker_slots.release()
            try:
                completed.exception()
            except BaseException:
                pass

        future.add_done_callback(release_worker)
        wrapped = asyncio.wrap_future(future)
        return await asyncio.wait_for(wrapped, timeout=timeout)


_activity_stream_runtime = ActivityStreamRuntime()


def stream_pool(service: WorkflowService) -> BoundedConnectionPool:
    store = service.store
    if (
        type(service) is not WorkflowService
        or not isinstance(store, PostgresStore)
        or type(store).connect is not PostgresStore.connect
        or type(store).get is not PostgresStore.get
        or type(store).list_activity is not PostgresStore.list_activity
        or type(store._pool) is not BoundedConnectionPool
    ):
        raise ActivityStreamCapacityError()
    return store._pool


def stream_authenticate(request: Request, token: str) -> AuthenticatedRequest:
    with stream_pool(request.app.state.service).stream_work():
        return request.app.state.identity.authenticate(token)


async def activity_stream_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AsyncIterator[AuthenticatedRequest]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationFailed("A bearer access token is required.")
    if not _activity_stream_runtime.try_acquire_stream():
        raise HTTPException(
            status_code=503, detail="Activity streaming is temporarily unavailable."
        )
    try:
        try:
            actor = await _activity_stream_runtime.call(
                stream_authenticate,
                request,
                credentials.credentials,
                timeout=STREAM_SECONDS,
            )
        except (ActivityStreamCapacityError, TimeoutError) as exc:
            raise HTTPException(
                status_code=503,
                detail="Activity streaming is temporarily unavailable.",
            ) from exc
        yield actor
    finally:
        _activity_stream_runtime.release_stream()


async def activity_stream_service(request: Request) -> WorkflowService:
    return request.app.state.service


def stream_activity(service: WorkflowService, actor: AuthenticatedRequest, case_id: UUID) -> None:
    with stream_pool(service).stream_work():
        service.activity(actor.principal, case_id, cursor=None, limit=1)


@router.get("/cases/{case_id}/activity/stream")
async def activity_stream(
    case_id: UUID,
    request: Request,
    actor: Annotated[AuthenticatedRequest, Depends(activity_stream_identity)],
    service: Annotated[WorkflowService, Depends(activity_stream_service)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID", max_length=512)] = None,
) -> StreamingResponse:
    # A previous pagination cursor is never a commit watermark: reconnects rescan.
    decode_activity_cursor(last_event_id)
    try:
        await _activity_stream_runtime.call(
            stream_activity,
            service,
            actor,
            case_id,
            timeout=STREAM_SECONDS,
        )
    except (ActivityStreamCapacityError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Activity streaming is temporarily unavailable.",
        ) from exc

    async def events() -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STREAM_SECONDS
        for _ in range(int(STREAM_SECONDS / HEARTBEAT_SECONDS)):
            try:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return
                current = await _activity_stream_runtime.call(
                    stream_authenticate,
                    request,
                    actor.access_token,
                    timeout=remaining,
                )
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return
                await _activity_stream_runtime.call(
                    stream_activity,
                    service,
                    current,
                    case_id,
                    timeout=remaining,
                )
            except (ActivityStreamCapacityError, TimeoutError):
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
