from typing import Protocol

from app.domain.models import Principal


class ToolAuthorization(Protocol):
    def authorize_tool(
        self, principal: Principal, tool_name: str, resource_id: str | None = None
    ) -> bool: ...
