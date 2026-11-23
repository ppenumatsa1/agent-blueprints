from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import Link, SpanContext, SpanKind, TraceFlags


_TRACE_KEYS = frozenset({"trace_id", "span_id", "trace_flags"})


def capture_trace_link() -> dict[str, str] | None:
    """Capture only the W3C identifiers needed to link a later durable resume."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return {
        "trace_id": f"{context.trace_id:032x}",
        "span_id": f"{context.span_id:016x}",
        "trace_flags": f"{int(context.trace_flags):02x}",
    }


def _validated_link(value: Any) -> tuple[Link, dict[str, str]] | None:
    if not isinstance(value, dict) or set(value) != _TRACE_KEYS:
        return None
    trace_id = value.get("trace_id")
    span_id = value.get("span_id")
    trace_flags = value.get("trace_flags")
    if not all(isinstance(item, str) for item in (trace_id, span_id, trace_flags)):
        return None
    try:
        if len(trace_id) != 32 or len(span_id) != 16 or len(trace_flags) != 2:
            return None
        context = SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=True,
            trace_flags=TraceFlags(int(trace_flags, 16)),
        )
    except ValueError:
        return None
    if not context.is_valid:
        return None
    attributes = {
        "blueprint.trace.link.kind": "hitl.start",
        "blueprint.trace.link.trace_id": trace_id.lower(),
        "blueprint.trace.link.span_id": span_id.lower(),
    }
    return Link(context, attributes=attributes), attributes


@contextmanager
def workflow_stage_span(
    stage: str,
    *,
    case_id: UUID,
    conversation_id: str,
    trace_link: Any = None,
) -> Iterator[None]:
    if stage not in {"start", "resume"}:
        raise ValueError("The workflow stage is invalid.")
    if not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 256:
        raise ValueError("The workflow conversation identity is invalid.")
    attributes: dict[str, str | bool] = {
        "blueprint.case.id": str(case_id),
        "blueprint.workflow.stage": stage,
        "gen_ai.conversation.id": conversation_id,
        "gen_ai.operation.name": f"workflow.{stage}",
    }
    links: list[Link] = []
    validated = _validated_link(trace_link)
    if validated is not None:
        link, link_attributes = validated
        links.append(link)
        attributes.update(link_attributes)
        attributes["blueprint.trace.restart"] = True
    tracer = trace.get_tracer("agent-blueprints.order-resolution")
    with tracer.start_as_current_span(
        f"order_resolution.workflow.{stage}",
        kind=SpanKind.INTERNAL,
        attributes=attributes,
        links=links,
        record_exception=False,
        set_status_on_exception=False,
    ):
        yield
