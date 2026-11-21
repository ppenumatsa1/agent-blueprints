from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agent_framework import Agent, FunctionTool, SupportsChatGetResponse

from app.extensions.prompts import PromptAsset


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    prompt_name: str
    prompt_version: str


def build_chat_agent(
    definition: AgentDefinition,
    client: SupportsChatGetResponse,
    prompt: PromptAsset,
    tools: Sequence[FunctionTool | Callable[..., Any]] = (),
) -> Agent:
    if (
        not definition.name
        or definition.name != definition.name.strip()
        or not definition.description
        or definition.description != definition.description.strip()
    ):
        raise ValueError("Agent names and descriptions must be non-empty and whitespace-trimmed.")
    if (definition.prompt_name, definition.prompt_version) != (prompt.name, prompt.version):
        raise ValueError("The agent prompt reference does not match the loaded asset.")
    return Agent(
        client=client,
        name=definition.name,
        description=definition.description,
        instructions=prompt.instructions,
        tools=list(tools),
    )
