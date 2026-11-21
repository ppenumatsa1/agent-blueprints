import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent_framework import Agent, FunctionTool, tool
from psycopg import Connection

from app.application import ApplicationComponents
from app.domain.errors import AccessDenied
from app.domain.models import Case, Principal, StateRepository
from app.domain.policy import CaseAccessPolicy, JsonObjectRules
from app.extensions.agents import AgentDefinition, build_chat_agent
from app.extensions.model import (
    ModelClientFactory,
    ModelSelection,
    select_chat_client,
)
from app.extensions.prompts import load_prompt_asset
from app.extensions.tools import ToolAuthorization, ToolRegistry
from app.workflows.workflow import create_workflow


PROMPT_PATH = Path(__file__).parent / "prompts" / "synthetic-review.v1.md"
SYNTHETIC_AGENT = AgentDefinition(
    name="synthetic-review",
    description="Reviews synthetic case data and returns findings for a human.",
    prompt_name="synthetic-review",
    prompt_version="v1",
)
SYNTHETIC_TOOL_NAME = "inspect_synthetic_case"


class SyntheticAction:
    def apply(self, connection: Connection, case: Case) -> None:
        connection.execute("INSERT INTO synthetic_effects (case_id) VALUES (%s)", (case.id,))


def prepare(store: StateRepository) -> None:
    with store.connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS synthetic_effects (
                case_id UUID PRIMARY KEY REFERENCES wf_cases(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def initialize(store: StateRepository) -> None:
    with store.connect() as connection:
        if (
            connection.execute("SELECT to_regclass('synthetic_effects') AS name").fetchone()["name"]
            is None
        ):
            raise RuntimeError("The synthetic example table is missing; run its preparation step.")


class SyntheticToolAuthorization:
    def authorize_tool(
        self, principal: Principal, tool_name: str, resource_id: str | None = None
    ) -> None:
        if (
            tool_name != SYNTHETIC_TOOL_NAME
            or "workflow.read" not in principal.scopes
            or resource_id != "synthetic-case"
        ):
            raise AccessDenied()


async def _inspect_synthetic_case(
    principal: Principal,
    authorization: ToolAuthorization,
    case_id: str,
) -> str:
    authorization.authorize_tool(principal, SYNTHETIC_TOOL_NAME, case_id)
    return f"Synthetic case reference: {case_id}"


def build_synthetic_tools(
    principal: Principal, authorization: ToolAuthorization
) -> tuple[FunctionTool | Callable[..., Any], ...]:
    registry = ToolRegistry()

    def bind_inspector(
        bound_principal: Principal, bound_authorization: ToolAuthorization
    ) -> FunctionTool | Callable[..., object]:
        @tool(
            name=SYNTHETIC_TOOL_NAME,
            description="Read an application-authorized synthetic case reference.",
        )
        async def inspect_synthetic_case(case_id: str) -> str:
            return await _inspect_synthetic_case(bound_principal, bound_authorization, case_id)

        return inspect_synthetic_case

    registry.register(SYNTHETIC_TOOL_NAME, bind_inspector)
    return registry.bind(principal, authorization)


def build_synthetic_agent(
    selection: ModelSelection,
    providers: Mapping[str, ModelClientFactory],
    principal: Principal,
    authorization: ToolAuthorization,
) -> Agent:
    """Build a request-scoped agent; do not share its principal-bound tools."""
    client = select_chat_client(selection, providers)
    prompt = load_prompt_asset("synthetic-review", "v1", PROMPT_PATH)
    tools = build_synthetic_tools(principal, authorization)
    return build_chat_agent(SYNTHETIC_AGENT, client, prompt, tools)


def build_application() -> ApplicationComponents:
    return ApplicationComponents(
        JsonObjectRules(),
        CaseAccessPolicy(),
        SyntheticAction(),
        initialize,
        workflow_factory=create_workflow,
    )


if __name__ == "__main__":
    from app.infrastructure.store import PostgresStore

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required.")
    prepare(PostgresStore(database_url))
