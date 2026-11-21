from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from .application import ApplicationComponents
from .config import Settings
from app.infrastructure.delegation import OnBehalfOf
from app.domain.errors import (
    AccessDenied,
    ActionError,
    AuthenticationFailed,
    AuthenticationUnavailable,
    BlueprintError,
    CheckpointError,
    Conflict,
    InvalidInput,
    NotFound,
)
from app.workflows.host import LocalWorkflowHost
from app.infrastructure.identity import AuthenticatedRequest, EntraIdentity, IdentityProvider
from app.domain.models import Case, StateRepository
from app.usecases.service import WorkflowService
from app.infrastructure.store import PostgresStore
from app.infrastructure.telemetry import Telemetry, _emit
from opentelemetry.trace import SpanKind, Status, StatusCode


bearer = HTTPBearer(auto_error=False)


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: UUID
    payload: dict[str, Any]


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]


class CaseOutput(BaseModel):
    id: UUID
    correlation_id: UUID
    status: str
    decision: Literal["pending", "approved", "rejected"]
    payload: dict[str, Any]
    execution_complete: bool
    failure_code: str | None


def _output(case: Case) -> CaseOutput:
    return CaseOutput(
        id=case.id,
        correlation_id=case.id,
        status=case.status,
        decision=case.decision or "pending",
        payload=case.payload,
        execution_complete=case.execution_complete,
        failure_code=case.failure_code,
    )


def create_app(
    settings: Settings,
    components: ApplicationComponents,
    *,
    store: StateRepository | None = None,
    identity: IdentityProvider | None = None,
) -> FastAPI:
    store = store if store is not None else PostgresStore(settings.database_url)
    identity = identity if identity is not None else EntraIdentity(settings)
    telemetry = Telemetry(settings.telemetry_mode, settings.applicationinsights_connection_string)
    try:
        return _create_app(settings, components, store, identity, telemetry)
    except BaseException:
        telemetry.shutdown()
        raise


def _create_app(settings, components, store, identity, telemetry) -> FastAPI:
    host = LocalWorkflowHost(
        store,
        components.action,
        settings.checkpoint_root,
        components.workflow_factory,
        telemetry=telemetry,
    )
    if isinstance(store, PostgresStore):
        store.telemetry = telemetry
    service = WorkflowService(store, host, components.rules, components.policy)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
                except ActionError:
                    _emit("recovery", outcome="action_failure")
                except BlueprintError:
                    store.mark_recovery_failed(case_id, "recovery_failed")
                    _emit("recovery", outcome="failure")
            yield
        finally:
            telemetry.shutdown()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.state.telemetry = telemetry
    app.state.obo = OnBehalfOf(settings, telemetry=telemetry)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "traceparent"],
            expose_headers=["X-Correlation-ID"],
        )

    @app.middleware("http")
    async def safe_errors(request: Request, call_next):
        request_id = str(uuid4())
        with telemetry.operation(
            "http.request",
            kind=SpanKind.SERVER,
            parent=telemetry.parent_from_headers(request.headers),
            correlation_id=request_id,
        ) as span:
            try:
                response = await call_next(request)
            except Exception:
                response = JSONResponse(
                    status_code=500, content={"detail": "Internal server error."}
                )
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
        response.headers["X-Correlation-ID"] = request_id
        return response

    def register_error(error_type, status_code: int, detail: str, headers=None):
        async def handler(request: Request, exc: Exception):
            return JSONResponse(
                status_code=status_code, content={"detail": detail}, headers=headers
            )

        app.add_exception_handler(error_type, handler)

    register_error(
        AuthenticationFailed, 401, "Authentication failed.", {"WWW-Authenticate": "Bearer"}
    )
    register_error(AuthenticationUnavailable, 503, "Authentication is temporarily unavailable.")
    register_error(AccessDenied, 403, "Access denied.")
    register_error(NotFound, 404, "Record not found.")
    register_error(Conflict, 409, "The request conflicts with the current record.")
    register_error(CheckpointError, 503, "Workflow recovery is unavailable.")
    register_error(ActionError, 503, "The configured action failed.")
    register_error(InvalidInput, 422, "Invalid request.")
    register_error(RequestValidationError, 422, "Invalid request.")

    def current_identity(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> AuthenticatedRequest:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise AuthenticationFailed("A bearer access token is required.")
        return identity.authenticate(credentials.credentials)

    @app.get("/healthz", status_code=204)
    def health() -> Response:
        return Response(status_code=204)

    @app.post("/api/cases", response_model=CaseOutput)
    async def submit(
        body: Submission,
        actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
        ],
    ) -> CaseOutput:
        case = await service.submit(
            actor.principal, str(body.reviewer_id), body.payload, idempotency_key
        )
        return _output(case)

    @app.get("/api/cases/{case_id}", response_model=CaseOutput)
    def read(
        case_id: UUID, actor: Annotated[AuthenticatedRequest, Depends(current_identity)]
    ) -> CaseOutput:
        return _output(service.read(actor.principal, case_id))

    @app.post("/api/cases/{case_id}/decision", response_model=CaseOutput)
    async def decide(
        case_id: UUID,
        body: DecisionInput,
        actor: Annotated[AuthenticatedRequest, Depends(current_identity)],
    ) -> CaseOutput:
        return _output(await service.decide(actor.principal, case_id, body.decision))

    return app
