import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from threading import BoundedSemaphore
from typing import Annotated, TypeVar
from uuid import UUID

import httpx
import jwt
import psycopg
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import bearer
from app.domain.errors import (
    AccessDenied,
    AuthenticationFailed,
    AuthenticationUnavailable,
    BlueprintError,
    NotFound,
)
from app.domain.policy import CaseAccessPolicy
from app.infrastructure.database import DatabaseConnector
from app.infrastructure.identity import AuthenticatedRequest, EntraIdentity, signing_key_id
from app.infrastructure.store import PostgresStore
from app.usecases.history import decode_activity_cursor
from app.usecases.service import WorkflowService

router = APIRouter(tags=["cases"])

STREAM_SECONDS = 30
HEARTBEAT_SECONDS = 5
ACTIVITY_STREAM_WORKERS = 4
MAX_CONCURRENT_ACTIVITY_STREAMS = 32
IO_SECONDS = 5
_T = TypeVar("_T")


class ActivityStreamCapacityError(Exception):
    pass


class ActivityStreamRuntime:
    """Bound cancellable async stream I/O independently of synchronous API workers."""

    def __init__(
        self,
        *,
        workers: int = ACTIVITY_STREAM_WORKERS,
        max_streams: int = MAX_CONCURRENT_ACTIVITY_STREAMS,
    ):
        self._worker_slots = BoundedSemaphore(workers)
        self._stream_slots = BoundedSemaphore(max_streams)

    def try_acquire_stream(self) -> bool:
        return self._stream_slots.acquire(blocking=False)

    def release_stream(self) -> None:
        self._stream_slots.release()

    async def call(
        self,
        function: Callable[..., Awaitable[_T]],
        *args: object,
        timeout: float,
        **kwargs: object,
    ) -> _T:
        if not self._worker_slots.acquire(blocking=False):
            raise ActivityStreamCapacityError()
        try:
            async with asyncio.timeout(min(timeout, IO_SECONDS)):
                return await function(*args, **kwargs)
        finally:
            self._worker_slots.release()


_activity_stream_runtime = ActivityStreamRuntime()


def stream_store(service: WorkflowService) -> PostgresStore:
    store = service.store
    if (
        type(service) is not WorkflowService
        or not isinstance(store, PostgresStore)
        or type(store).connect is not PostgresStore.connect
        or type(store).get is not PostgresStore.get
        or type(store).list_activity is not PostgresStore.list_activity
        or type(store).get_for_activity_stream is not PostgresStore.get_for_activity_stream
        or type(store._connector) is not DatabaseConnector
        or store._connector.options.auth_mode != "password"
        or type(service.policy) is not CaseAccessPolicy
    ):
        raise ActivityStreamCapacityError()
    return store


class StreamSigningKeys:
    def __init__(self, value: dict):
        self.keys = jwt.PyJWKSet.from_dict(value)

    def get_signing_key_from_jwt(self, token: str):
        kid = jwt.get_unverified_header(token).get("kid")
        for key in self.keys.keys:
            if key.key_id == kid and key.public_key_use in (None, "sig"):
                return key
        raise jwt.PyJWKClientError("Unknown signing key.")

    def has_key(self, kid: str) -> bool:
        return any(
            key.key_id == kid and key.public_key_use in (None, "sig") for key in self.keys.keys
        )


class StreamSigningKeyCache:
    def __init__(self, identity: EntraIdentity):
        self.identity = identity
        self.keys: StreamSigningKeys | None = None
        self.expires_at = 0.0
        self.refresh_after = 0.0
        self._refresh_slot = BoundedSemaphore(1)

    async def get(self, kid: str) -> StreamSigningKeys:
        now = time.monotonic()
        cached = self.keys
        if cached is not None and now < self.expires_at:
            if cached.has_key(kid) or now < self.refresh_after:
                return cached
        elif now < self.refresh_after:
            raise AuthenticationUnavailable("Signing keys are temporarily unavailable.")
        if not self._refresh_slot.acquire(blocking=False):
            raise AuthenticationUnavailable("Signing keys are temporarily unavailable.")
        try:
            # Unknown kids and failed fetches cannot cause unbounded refresh traffic.
            self.refresh_after = now + 30
            keys = await stream_signing_keys(self.identity)
            self.keys = keys
            self.expires_at = time.monotonic() + 300
            return keys
        finally:
            self._refresh_slot.release()


async def stream_signing_keys(identity: EntraIdentity) -> StreamSigningKeys:
    url = f"https://login.microsoftonline.com/{identity.settings.tenant_id}/discovery/v2.0/keys"
    try:
        async with httpx.AsyncClient(timeout=IO_SECONDS, trust_env=False) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 262_144:
                        raise ValueError("Signing key response is too large.")
        value = json.loads(body)
        if not isinstance(value, dict):
            raise ValueError("Invalid signing key response.")
        return StreamSigningKeys(value)
    except (httpx.HTTPError, ValueError, jwt.PyJWTError, KeyError, TypeError) as exc:
        raise AuthenticationUnavailable("Signing keys are temporarily unavailable.") from exc


async def stream_authenticate(request: Request, token: str) -> AuthenticatedRequest:
    identity = request.app.state.identity
    if type(identity) is not EntraIdentity:
        raise ActivityStreamCapacityError()
    kid = signing_key_id(token)
    cache = getattr(request.app.state, "activity_stream_keys", None)
    if not isinstance(cache, StreamSigningKeyCache) or cache.identity is not identity:
        cache = StreamSigningKeyCache(identity)
        request.app.state.activity_stream_keys = cache
    keys = await cache.get(kid)
    return EntraIdentity(identity.settings, keys).authenticate(token)


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
            stream_store(request.app.state.service)
            actor = await _activity_stream_runtime.call(
                stream_authenticate,
                request,
                credentials.credentials,
                timeout=STREAM_SECONDS,
            )
        except (ActivityStreamCapacityError, TimeoutError, psycopg.Error) as exc:
            raise HTTPException(
                status_code=503,
                detail="Activity streaming is temporarily unavailable.",
            ) from exc
        yield actor
    finally:
        _activity_stream_runtime.release_stream()


async def activity_stream_service(request: Request) -> WorkflowService:
    return request.app.state.service


async def stream_activity(
    service: WorkflowService, actor: AuthenticatedRequest, case_id: UUID
) -> None:
    case = await stream_store(service).get_for_activity_stream(case_id)
    service.policy.authorize_read(actor.principal, case)


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
    except (ActivityStreamCapacityError, TimeoutError, psycopg.Error) as exc:
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
            except (ActivityStreamCapacityError, TimeoutError, psycopg.Error):
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
