from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    ResponsesHostServer,
    WorkflowTurn,
)
from azure.ai.agentserver.responses import ResponsesServerOptions

from .application import CallerContext, HostedApplication, load_application


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


def create_responses_server(application: HostedApplication) -> ResponsesHostServer:
    async def parse_response(request: Any) -> WorkflowTurn[Any]:
        return await parse_turn(application, request)

    def build_workflow(request: Any) -> Any:
        return application.build_workflow(_caller(request), _conversation(request))

    return ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=list(application.checkpoint_types),
        ),
        options=ResponsesServerOptions(resilient_background=True),
    )


def run() -> None:
    create_responses_server(load_application()).run()
