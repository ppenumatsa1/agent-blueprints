from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_exception_handlers
from app.api.middleware import install_request_middleware
from app.api.routes.cases import router as cases_router
from app.api.routes.health import router as health_router
from app.config import Settings
from app.infrastructure.delegation import OnBehalfOf
from app.infrastructure.identity import IdentityProvider
from app.infrastructure.telemetry import Telemetry
from app.usecases.service import WorkflowService

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_api_app(
    settings: Settings,
    service: WorkflowService,
    identity: IdentityProvider,
    obo: OnBehalfOf,
    lifespan: Lifespan,
    telemetry: Telemetry,
) -> FastAPI:
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.state.identity = identity
    app.state.obo = obo
    app.state.telemetry = telemetry

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "traceparent"],
            expose_headers=["X-Correlation-ID"],
        )

    install_request_middleware(app, telemetry)
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(cases_router, prefix="/api")
    return app
