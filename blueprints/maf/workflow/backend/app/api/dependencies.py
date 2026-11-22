from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.errors import AuthenticationFailed
from app.infrastructure.identity import AuthenticatedRequest, IdentityProvider
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


def workflow_service(request: Request) -> WorkflowService:
    return request.app.state.service
