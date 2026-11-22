import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("blueprint.api")


def install_request_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def safe_errors(request: Request, call_next):
        request_id = str(uuid4())
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("Request %s failed (%s).", request_id, type(exc).__name__)
            response = JSONResponse(status_code=500, content={"detail": "Internal server error."})
        response.headers["X-Correlation-ID"] = request_id
        return response
