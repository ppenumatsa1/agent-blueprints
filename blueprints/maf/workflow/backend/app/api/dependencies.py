from contextlib import contextmanager, nullcontext
from typing import Annotated, Iterator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.errors import AuthenticationFailed
from app.infrastructure.identity import AuthenticatedRequest, IdentityProvider
from app.infrastructure.store import PostgresStore
from app.usecases.service import WorkflowService

bearer = HTTPBearer(auto_error=False)


def current_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedRequest:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationFailed("A bearer access token is required.")
    identity: IdentityProvider = request.app.state.identity
    return identity.authenticate(credentials.credentials)


def current_service_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthenticatedRequest:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationFailed("A bearer access token is required.")
    identity: IdentityProvider = request.app.state.identity
    return identity.authenticate_service(credentials.credentials)


def workflow_service(request: Request) -> WorkflowService:
    return request.app.state.service


@contextmanager
def poll_read(service: WorkflowService) -> Iterator[None]:
    gate = (
        service.store.poll_read() if isinstance(service.store, PostgresStore) else nullcontext(True)
    )
    with gate as admitted:
        if not admitted:
            raise HTTPException(status_code=503, detail="Case reads are temporarily unavailable.")
        yield
