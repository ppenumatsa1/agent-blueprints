from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import (
    AccessDenied,
    ActionError,
    AuthenticationFailed,
    AuthenticationUnavailable,
    CheckpointError,
    Conflict,
    HostedWorkflowError,
    InvalidInput,
    NotFound,
)


def install_exception_handlers(app: FastAPI) -> None:
    def register(
        error_type: type[Exception],
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        async def handler(_: Request, __: Exception) -> JSONResponse:
            return JSONResponse(
                status_code=status_code, content={"detail": detail}, headers=headers
            )

        app.add_exception_handler(error_type, handler)

    register(AuthenticationFailed, 401, "Authentication failed.", {"WWW-Authenticate": "Bearer"})
    register(AuthenticationUnavailable, 503, "Authentication is temporarily unavailable.")
    register(AccessDenied, 403, "Access denied.")
    register(NotFound, 404, "Record not found.")
    register(Conflict, 409, "The request conflicts with the current record.")
    register(CheckpointError, 503, "Workflow recovery is unavailable.")
    register(HostedWorkflowError, 503, "Hosted workflow execution is unavailable.")
    register(ActionError, 503, "The configured action failed.")
    register(InvalidInput, 422, "Invalid request.")
    register(RequestValidationError, 422, "Invalid request.")
