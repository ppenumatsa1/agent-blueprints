from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import (
    Link,
    SpanContext,
    SpanKind,
    Status,
    StatusCode,
    TraceFlags,
)


_TRACE_KEYS = frozenset({"trace_id", "span_id", "trace_flags"})
_BUSINESS_STAGES = frozenset(
    {"authorization", "policy", "proposal", "approval", "persistence", "effect"}
)
_MARKERS = frozenset({"resolution_submit", "hitl_waiting", "hitl_resume"})
_PHASES = frozenset({"start", "resume"})
_OUTCOMES = frozenset({"automatic", "approved", "rejected", "pending"})
_ERROR_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")


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


def _common_attributes(
    *,
    case_id: UUID,
    conversation_id: str,
) -> dict[str, str]:
    if not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 256:
        raise ValueError("The workflow conversation identity is invalid.")
    return {
        "blueprint.case.id": str(case_id),
        "gen_ai.conversation.id": conversation_id,
    }


@contextmanager
def _signal_span(
    name: str,
    *,
    case_id: UUID,
    conversation_id: str,
    trace_link: Any = None,
    attributes: dict[str, str | int | bool] | None = None,
    stage_name: str | None = None,
) -> Iterator[None]:
    values: dict[str, str | int | bool] = _common_attributes(
        case_id=case_id,
        conversation_id=conversation_id,
    )
    if attributes:
        values.update(attributes)
    links: list[Link] = []
    validated = _validated_link(trace_link)
    if validated is not None:
        link, link_attributes = validated
        links.append(link)
        values.update(link_attributes)
        values["blueprint.trace.restart"] = True
    tracer = trace.get_tracer("agent-blueprints.order-resolution")
    with tracer.start_as_current_span(
        name,
        kind=SpanKind.INTERNAL,
        attributes=values,
        links=links,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield
        except BaseException as exc:
            if stage_name is not None:
                span.update_name(f"workflow.stage.{stage_name}.failed")
            span.set_attribute("blueprint.workflow.status", "failed")
            error_type = type(exc).__name__
            span.set_attribute(
                "error.type",
                error_type if _ERROR_TYPE.fullmatch(error_type) else "Error",
            )
            span.set_status(Status(StatusCode.ERROR))
            raise
        else:
            if stage_name is not None:
                span.update_name(f"workflow.stage.{stage_name}.succeeded")
            span.set_attribute("blueprint.workflow.status", "succeeded")


@contextmanager
def workflow_business_stage(
    stage: str,
    *,
    case_id: UUID,
    conversation_id: str,
    outcome: str | None = None,
    approval_required: bool | None = None,
    proposal_version: int | None = None,
) -> Iterator[None]:
    if stage not in _BUSINESS_STAGES:
        raise ValueError("The workflow business stage is invalid.")
    if outcome is not None and outcome not in _OUTCOMES:
        raise ValueError("The workflow outcome is invalid.")
    if proposal_version is not None and (
        not isinstance(proposal_version, int)
        or isinstance(proposal_version, bool)
        or proposal_version < 1
    ):
        raise ValueError("The proposal version is invalid.")
    attributes: dict[str, str | int | bool] = {"blueprint.workflow.stage": stage}
    if outcome is not None:
        attributes["blueprint.workflow.outcome"] = outcome
    if approval_required is not None:
        attributes["blueprint.workflow.approval_required"] = approval_required
    if proposal_version is not None:
        attributes["blueprint.proposal.version"] = proposal_version
    with _signal_span(
        f"workflow.stage.{stage}.running",
        case_id=case_id,
        conversation_id=conversation_id,
        attributes=attributes,
        stage_name=stage,
    ):
        yield


@contextmanager
def workflow_marker_span(
    marker: str,
    *,
    case_id: UUID,
    conversation_id: str,
    trace_link: Any = None,
    outcome: str | None = None,
) -> Iterator[None]:
    if marker not in _MARKERS:
        raise ValueError("The workflow marker is invalid.")
    if outcome is not None and outcome not in _OUTCOMES:
        raise ValueError("The workflow outcome is invalid.")
    attributes: dict[str, str | int | bool] = {
        "gen_ai.operation.name": f"workflow.{marker}",
    }
    if outcome is not None:
        attributes["blueprint.workflow.outcome"] = outcome
    with _signal_span(
        f"workflow.{marker}",
        case_id=case_id,
        conversation_id=conversation_id,
        trace_link=trace_link,
        attributes=attributes,
    ):
        yield


@contextmanager
def workflow_stage_span(
    stage: str,
    *,
    case_id: UUID,
    conversation_id: str,
    trace_link: Any = None,
) -> Iterator[None]:
    if stage not in _PHASES:
        raise ValueError("The workflow stage is invalid.")
    run_attributes: dict[str, str | int | bool] = {
        "blueprint.workflow.phase": stage,
        "gen_ai.operation.name": "workflow.run",
    }
    with _signal_span(
        "workflow.run",
        case_id=case_id,
        conversation_id=conversation_id,
        trace_link=trace_link,
        attributes=run_attributes,
    ):
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
        ) as span:
            try:
                yield
            except BaseException as exc:
                error_type = type(exc).__name__
                span.set_attribute(
                    "error.type",
                    error_type if _ERROR_TYPE.fullmatch(error_type) else "Error",
                )
                span.set_status(Status(StatusCode.ERROR))
                raise
