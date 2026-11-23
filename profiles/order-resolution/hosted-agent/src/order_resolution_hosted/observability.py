"""Privacy-safe OpenTelemetry bridge for the AgentServer Responses root."""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Mapping

from opentelemetry import context, trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

_INSTRUMENTATION_SCOPE = "agent-blueprints.order-resolution.hosted"
_ANCHOR_TYPE = "app-owned-invoke-agent"
_ANCHOR_SOURCE = "azure.ai.agentserver.responses.create_span_hook"
_MAX_ATTRIBUTE_LENGTH = 1024
_ALLOWED_TAGS = frozenset(
    {
        "azure.ai.agentserver.responses.conversation_id",
        "azure.ai.agentserver.responses.response_id",
        "azure.ai.agentserver.responses.streaming",
        "gen_ai.agent.id",
        "gen_ai.agent.name",
        "gen_ai.agent.version",
        "gen_ai.conversation.id",
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
        "gen_ai.response.id",
        "gen_ai.system",
        "microsoft.foundry",
        "microsoft.foundry.project.id",
        "request.id",
        "service.name",
    }
)


@dataclass
class _ActiveAnchor:
    span: Span
    context_token: object | None = None


class InvokeAgentSpanHook:
    """Bridge the supported Responses create-span lifecycle to OpenTelemetry."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ
        self._active: ContextVar[tuple[_ActiveAnchor, ...]] = ContextVar(
            "order_resolution_invoke_agent_anchors",
            default=(),
        )

    def on_span_start(self, name: str, tags: dict[str, Any]) -> None:
        parent = trace.get_current_span().get_span_context()
        attributes = self._safe_attributes(tags)
        attributes.update(
            {
                "blueprint.trace.anchor.type": _ANCHOR_TYPE,
                "blueprint.trace.anchor.source": _ANCHOR_SOURCE,
                "blueprint.trace.parent.remote": bool(parent.is_remote),
            }
        )
        for environment_name, attribute_name in (
            ("SOURCE_REVISION", "blueprint.source.revision"),
            ("DEPLOYMENT_REVISION", "blueprint.deployment.revision"),
        ):
            value = self._safe_text(self._environ.get(environment_name))
            if value is not None:
                attributes[attribute_name] = value
        tracer = trace.get_tracer(_INSTRUMENTATION_SCOPE)
        span = tracer.start_span(
            "invoke_agent",
            context=context.get_current(),
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        )
        active = _ActiveAnchor(span=span)
        current = self._active.get()
        self._active.set((*current, active))
        active.context_token = context.attach(trace.set_span_in_context(span))

    def on_span_end(
        self,
        name: str,
        tags: dict[str, Any],
        error: BaseException | None,
    ) -> None:
        current = self._active.get()
        if not current:
            return
        active = current[-1]
        for key, value in self._safe_attributes(tags).items():
            active.span.set_attribute(key, value)
        agent_version = self._safe_text(tags.get("gen_ai.agent.version"))
        if agent_version is not None:
            active.span.set_attribute("blueprint.agent.version", agent_version)
        if error is not None:
            active.span.set_attribute("error.type", type(error).__name__)
            active.span.set_status(Status(StatusCode.ERROR))
        if active.context_token is not None:
            context.detach(active.context_token)
        self._active.set(current[:-1])
        active.span.end()

    @classmethod
    def _safe_attributes(cls, tags: Mapping[str, Any]) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        for key in _ALLOWED_TAGS:
            value = tags.get(key)
            if isinstance(value, bool):
                attributes[key] = value
            elif isinstance(value, (int, float)):
                attributes[key] = value
            else:
                text = cls._safe_text(value)
                if text is not None:
                    attributes[key] = text
        return attributes

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text or len(text) > _MAX_ATTRIBUTE_LENGTH:
            return None
        return text
