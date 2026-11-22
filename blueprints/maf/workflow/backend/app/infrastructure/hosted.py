import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.domain.errors import HostedWorkflowError
from app.infrastructure.database import TokenProvider


HostedStatus = Literal["pending", "automatic", "approved", "rejected"]


def _opaque(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 512
        and all(0x21 <= ord(character) <= 0x7E for character in value)
    )


@dataclass(frozen=True)
class HostedStart:
    operation_id: str
    case_id: str
    tenant_id: str
    owner_id: str
    reviewer_id: str
    payload: dict


@dataclass(frozen=True)
class HostedResume:
    operation_id: str
    case_id: str
    execution_id: str
    request_id: str
    decision: Literal["approved", "rejected"]
    reviewer_id: str


@dataclass(frozen=True)
class HostedResult:
    operation_id: str
    execution_id: str
    status: HostedStatus
    request_id: str | None = None


class HostedWorkflowClient(Protocol):
    async def start(self, request: HostedStart) -> HostedResult: ...

    async def resume(self, request: HostedResume) -> HostedResult: ...

    async def status(self, operation_id: str) -> HostedResult: ...


class HttpHostedWorkflowClient:
    """SDK-free adapter for the Agent A hosted workflow HTTP contract."""

    def __init__(
        self,
        endpoint: str,
        scope: str,
        token_provider: TokenProvider,
        *,
        timeout_seconds: float = 10.0,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.scope = scope
        self.token_provider = token_provider
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, body: dict | None = None) -> HostedResult:
        try:
            token = self.token_provider.get_token(self.scope)
        except Exception as exc:
            raise HostedWorkflowError("The hosted caller identity is unavailable.") from exc
        encoded = (
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
            if body is not None
            else None
        )
        request = Request(
            self.endpoint + path,
            method=method,
            data=encoded,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if encoded is not None else {}),
                **(
                    {"Idempotency-Key": str(body["operation_id"])}
                    if body is not None and "operation_id" in body
                    else {}
                ),
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                value = json.loads(response.read(65_537))
        except HTTPError as exc:
            raise HostedWorkflowError(
                "The hosted workflow rejected the authenticated request."
            ) from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise HostedWorkflowError("The hosted workflow outcome is unknown.") from exc
        if not isinstance(value, dict):
            raise HostedWorkflowError("The hosted workflow returned an invalid response.")
        try:
            result = HostedResult(
                operation_id=value["operation_id"],
                execution_id=value["execution_id"],
                status=value["status"],
                request_id=value.get("request_id"),
            )
        except (KeyError, TypeError) as exc:
            raise HostedWorkflowError("The hosted workflow returned an invalid response.") from exc
        if (
            result.status not in ("pending", "automatic", "approved", "rejected")
            or not _opaque(result.operation_id)
            or not _opaque(result.execution_id)
            or (result.status == "pending" and not _opaque(result.request_id))
            or (result.status != "pending" and result.request_id is not None)
        ):
            raise HostedWorkflowError("The hosted workflow returned an invalid response.")
        return result

    async def start(self, request: HostedStart) -> HostedResult:
        return await asyncio.to_thread(self._request, "POST", "/runs", asdict(request))

    async def resume(self, request: HostedResume) -> HostedResult:
        path = f"/runs/{quote(request.execution_id, safe='')}/responses"
        return await asyncio.to_thread(self._request, "POST", path, asdict(request))

    async def status(self, operation_id: str) -> HostedResult:
        path = f"/operations/{quote(operation_id, safe='')}"
        return await asyncio.to_thread(self._request, "GET", path)
