from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(tags=["health"])


@router.get("/healthz", status_code=204)
def health() -> Response:
    return Response(status_code=204)
