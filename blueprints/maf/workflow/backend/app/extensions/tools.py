from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from agent_framework import FunctionTool

from app.domain.models import Principal


class ToolAuthorization(Protocol):
    def authorize_tool(
        self, principal: Principal, tool_name: str, resource_id: str | None = None
    ) -> bool: ...


class BoundToolFactory(Protocol):
    def __call__(
        self, principal: Principal, authorization: ToolAuthorization
    ) -> FunctionTool | Callable[..., object]: ...


@dataclass
class ToolRegistry:
    _factories: dict[str, BoundToolFactory] = field(default_factory=dict)

    def register(self, name: str, factory: BoundToolFactory) -> None:
        if not name or name != name.strip():
            raise ValueError("Tool names must be non-empty and whitespace-trimmed.")
        if name in self._factories:
            raise ValueError(f"Tool {name!r} is already registered.")
        self._factories[name] = factory

    def bind(
        self, principal: Principal, authorization: ToolAuthorization
    ) -> tuple[FunctionTool | Callable[..., object], ...]:
        bound_tools = []
        for name, factory in self._factories.items():
            bound_tool = factory(principal, authorization)
            bound_name = getattr(bound_tool, "name", None) or getattr(bound_tool, "__name__", None)
            if bound_name != name:
                raise ValueError(f"Tool factory {name!r} returned a tool with a different name.")
            bound_tools.append(bound_tool)
        return tuple(bound_tools)
