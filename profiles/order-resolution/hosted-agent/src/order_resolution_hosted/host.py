from __future__ import annotations

import json
import os
import threading
from typing import Any
from uuid import UUID

from agent_framework.observability import enable_instrumentation
from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    ResponsesHostServer,
    WorkflowTurn,
)
from azure.ai.agentserver.core import configure_observability as configure_agentserver_observability
from azure.ai.agentserver.responses import ResponsesServerOptions

from .application import CallerContext, HostedApplication, load_application
from .observability import InvokeAgentSpanHook, sanitize_async_httpx_url, sanitize_httpx_url


_PRIVACY_ENVIRONMENT = {
    "ENABLE_SENSITIVE_DATA": "false",
    "ENABLE_MESSAGE_EVENTS": "false",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
}
_INSTRUMENTATION_OPTIONS = {
    "azure_sdk": {"enabled": True},
    "fastapi": {
        "excluded_urls": r"^https?://[^/?#]+/healthz$",
    },
    "httpx": {
        "enabled": True,
        "request_hook": sanitize_httpx_url,
        "async_request_hook": sanitize_async_httpx_url,
    },
    "openai_agents": {"enabled": False},
    "urllib": {"enabled": True},
}
_CHECKPOINT_TYPES = ("app.order_resolution.workflow:OrderResolutionDecision",)


def _configure_host_observability(
    *,
    connection_string: str | None = None,
    log_level: str | None = None,
    enable_sensitive_data: bool = False,
) -> None:
    del enable_sensitive_data
    configure_agentserver_observability(
        connection_string=connection_string,
        log_level=log_level,
        enable_sensitive_data=False,
        instrumentation_options=_INSTRUMENTATION_OPTIONS,
    )
    enable_instrumentation(
        enable_sensitive_data=False,
        enable_message_events=False,
        force=True,
    )


def _caller(request: Any) -> CallerContext:
    scope = request.scope
    return CallerContext(
        user_id=scope.user_id or "",
        session_id=scope.session_id or "",
        call_id=scope.call_id or "",
    )


def _conversation(request: Any) -> str:
    value = request.conversation_id
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise PermissionError("An explicit Foundry conversation ID is required.")
    return value


def _start_case(text: str | None) -> UUID:
    if not text:
        raise ValueError("A JSON start command is required.")
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict) or set(payload) != {"case_id"}:
            raise ValueError
        return UUID(payload["case_id"])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("The start command must contain exactly one valid case_id.") from exc


def _item_type(item: Any) -> str | None:
    return item.get("type") if isinstance(item, dict) else getattr(item, "type", None)


async def parse_turn(
    application: HostedApplication,
    request: Any,
) -> WorkflowTurn[Any]:
    caller = _caller(request)
    conversation_id = _conversation(request)
    items = await request.get_input_items()
    reply_items = [
        item
        for item in items
        if _item_type(item) in ("function_call_output", "mcp_approval_response")
    ]
    if reply_items:
        if any(_item_type(item) != "function_call_output" for item in reply_items):
            raise PermissionError("Only structured workflow decision replies are accepted.")
        responses = await request.get_workflow_responses()
        normalized = {
            request_id: application.authorize_resume(
                caller,
                conversation_id,
                request_id,
                value,
            )
            for request_id, value in responses.items()
        }
        return WorkflowTurn(responses=normalized)

    case_id = _start_case(await request.get_input_text())
    workflow_input = application.authorize_start(caller, conversation_id, case_id)
    return WorkflowTurn(input=workflow_input)


def create_responses_server(
    application: HostedApplication | None = None,
) -> ResponsesHostServer:
    os.environ.update(_PRIVACY_ENVIRONMENT)
    application_lock = threading.RLock()
    application_prepared = False

    def resolve_application() -> HostedApplication:
        nonlocal application
        if application is None:
            with application_lock:
                if application is None:
                    application = load_application()
        return application

    def configure_observability(
        *,
        connection_string: str | None = None,
        log_level: str | None = None,
        enable_sensitive_data: bool = False,
    ) -> None:
        nonlocal application_prepared
        _configure_host_observability(
            connection_string=connection_string,
            log_level=log_level,
            enable_sensitive_data=enable_sensitive_data,
        )
        with application_lock:
            if application_prepared:
                return
            resolved = resolve_application()
            prewarm = getattr(resolved, "prewarm", None)
            if callable(prewarm):
                prewarm()
            application_prepared = True

    async def parse_response(request: Any) -> WorkflowTurn[Any]:
        return await parse_turn(resolve_application(), request)

    def build_workflow(request: Any) -> Any:
        return resolve_application().build_workflow(
            _caller(request),
            _conversation(request),
        )

    return ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=list(
                application.checkpoint_types if application is not None else _CHECKPOINT_TYPES
            ),
        ),
        options=ResponsesServerOptions(
            create_span_hook=InvokeAgentSpanHook(),
            resilient_background=True,
        ),
        configure_observability=configure_observability,
    )


def run() -> None:
    create_responses_server().run()
