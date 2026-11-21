import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from opentelemetry.trace import SpanKind, Status, StatusCode

from app.infrastructure.telemetry import Telemetry

logger = logging.getLogger("blueprint.api")


def install_request_middleware(app: FastAPI, telemetry: Telemetry) -> None:
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
                logger.error("Request %s failed.", request_id)
                response = JSONResponse(
                    status_code=500, content={"detail": "Internal server error."}
                )
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
        response.headers["X-Correlation-ID"] = request_id
        return response
