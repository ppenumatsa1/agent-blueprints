import asyncio
import unittest
from unittest.mock import patch
from uuid import UUID

from opentelemetry import context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    StatusCode,
    TraceFlags,
    TraceState,
)

from app.order_resolution.observability import (
    capture_trace_link,
    workflow_business_stage,
    workflow_marker_span,
    workflow_stage_span,
)
from order_resolution_hosted.observability import InvokeAgentSpanHook


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.provider = TracerProvider()
        self.exporter = InMemorySpanExporter()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("test")
        self.case_id = UUID("20000000-0000-4000-8000-000000000002")

    def tearDown(self):
        self.provider.shutdown()

    def _remote_parent(self, trace_id: int, span_id: int):
        return trace.set_span_in_context(
            NonRecordingSpan(
                SpanContext(
                    trace_id=trace_id,
                    span_id=span_id,
                    is_remote=True,
                    trace_flags=TraceFlags(TraceFlags.SAMPLED),
                    trace_state=TraceState(),
                )
            )
        )

    def test_responses_hook_creates_one_privacy_safe_root_and_parents_children(self):
        remote_trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        remote_span_id = 0x1234567890ABCDEF
        hook = InvokeAgentSpanHook(
            {
                "SOURCE_REVISION": "a" * 40,
                "DEPLOYMENT_REVISION": "b" * 40,
            }
        )
        remote_token = context.attach(self._remote_parent(remote_trace_id, remote_span_id))
        try:
            with patch(
                "order_resolution_hosted.observability.trace.get_tracer",
                return_value=self.tracer,
            ):
                hook.on_span_start(
                    "create_response",
                    {
                        "gen_ai.operation.name": "invoke_agent",
                        "gen_ai.provider.name": "microsoft",
                        "gen_ai.input.messages": "private input",
                        "tool.arguments": "private tool arguments",
                    },
                )
                with self.tracer.start_as_current_span("invoke_workflow"):
                    pass
                hook.on_span_end(
                    "create_response",
                    {
                        "gen_ai.operation.name": "invoke_agent",
                        "gen_ai.agent.name": "order-resolution",
                        "gen_ai.agent.version": "5",
                        "gen_ai.conversation.id": "conversation-1",
                        "gen_ai.response.id": "response-1",
                        "microsoft.foundry": "true",
                        "gen_ai.output.messages": "private output",
                    },
                    None,
                )
        finally:
            context.detach(remote_token)

        spans = {item.name: item for item in self.exporter.get_finished_spans()}
        anchor = spans["invoke_agent"]
        child = spans["invoke_workflow"]
        self.assertEqual(anchor.context.trace_id, remote_trace_id)
        self.assertEqual(anchor.parent.span_id, remote_span_id)
        self.assertTrue(anchor.parent.is_remote)
        self.assertEqual(child.parent.span_id, anchor.context.span_id)
        self.assertEqual(
            anchor.attributes["blueprint.trace.anchor.type"],
            "app-owned-invoke-agent",
        )
        self.assertEqual(
            anchor.attributes["blueprint.trace.anchor.source"],
            "azure.ai.agentserver.responses.create_span_hook",
        )
        self.assertTrue(anchor.attributes["blueprint.trace.parent.remote"])
        self.assertEqual(anchor.attributes["blueprint.agent.version"], "5")
        self.assertEqual(anchor.attributes["blueprint.source.revision"], "a" * 40)
        self.assertEqual(anchor.attributes["blueprint.deployment.revision"], "b" * 40)
        self.assertEqual(anchor.status.status_code, StatusCode.UNSET)
        self.assertNotIn("private input", anchor.to_json())
        self.assertNotIn("private tool arguments", anchor.to_json())
        self.assertNotIn("private output", anchor.to_json())

    def test_responses_hook_marks_errors_without_recording_exception_content(self):
        hook = InvokeAgentSpanHook({})
        with patch(
            "order_resolution_hosted.observability.trace.get_tracer",
            return_value=self.tracer,
        ):
            hook.on_span_start(
                "create_response",
                {"gen_ai.operation.name": "invoke_agent"},
            )
            hook.on_span_end(
                "create_response",
                {"gen_ai.operation.name": "invoke_agent"},
                RuntimeError("private payload"),
            )
        anchor = self.exporter.get_finished_spans()[-1]
        self.assertEqual(anchor.status.status_code, StatusCode.ERROR)
        self.assertEqual(anchor.attributes["error.type"], "RuntimeError")
        self.assertNotIn("private payload", anchor.to_json())

    def test_responses_hook_isolates_concurrent_request_contexts(self):
        hook = InvokeAgentSpanHook({})

        async def invoke(trace_id: int, parent_id: int, conversation_id: str):
            token = context.attach(self._remote_parent(trace_id, parent_id))
            try:
                hook.on_span_start(
                    "create_response",
                    {"gen_ai.conversation.id": conversation_id},
                )
                await asyncio.sleep(0)
                with self.tracer.start_as_current_span(f"child-{conversation_id}"):
                    await asyncio.sleep(0)
                hook.on_span_end(
                    "create_response",
                    {"gen_ai.conversation.id": conversation_id},
                    None,
                )
            finally:
                context.detach(token)

        async def run_concurrently():
            await asyncio.gather(
                invoke(0x1 << 64, 0x101, "conversation-1"),
                invoke(0x2 << 64, 0x202, "conversation-2"),
            )

        with patch(
            "order_resolution_hosted.observability.trace.get_tracer",
            return_value=self.tracer,
        ):
            asyncio.run(run_concurrently())
        spans = list(self.exporter.get_finished_spans())
        anchors = {
            item.attributes["gen_ai.conversation.id"]: item
            for item in spans
            if item.name == "invoke_agent"
        }
        for conversation_id, parent_id in (
            ("conversation-1", 0x101),
            ("conversation-2", 0x202),
        ):
            anchor = anchors[conversation_id]
            child = next(item for item in spans if item.name == f"child-{conversation_id}")
            self.assertEqual(anchor.parent.span_id, parent_id)
            self.assertEqual(child.parent.span_id, anchor.context.span_id)

    def test_responses_hook_ends_before_supported_provider_flush(self):
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter, schedule_delay_millis=60_000))
        hook = InvokeAgentSpanHook({})
        try:
            with patch(
                "order_resolution_hosted.observability.trace.get_tracer",
                return_value=provider.get_tracer("test-batch"),
            ):
                hook.on_span_start(
                    "create_response",
                    {"gen_ai.operation.name": "invoke_agent"},
                )
                hook.on_span_end(
                    "create_response",
                    {"gen_ai.operation.name": "invoke_agent"},
                    None,
                )
            self.assertTrue(provider.force_flush())
            self.assertEqual(
                [item.name for item in exporter.get_finished_spans()],
                ["invoke_agent"],
            )
        finally:
            provider.shutdown()

    def test_durable_resume_uses_real_link_instead_of_parent_fabrication(self):
        with self.tracer.start_as_current_span("invoke_agent start") as start:
            captured = capture_trace_link()
            start_trace_id = start.get_span_context().trace_id
            start_span_id = start.get_span_context().span_id
        with (
            self.tracer.start_as_current_span("invoke_agent resume") as resume_root,
            patch(
                "app.order_resolution.observability.trace.get_tracer",
                return_value=self.tracer,
            ),
        ):
            resume_trace_id = resume_root.get_span_context().trace_id
            with workflow_stage_span(
                "resume",
                case_id=self.case_id,
                conversation_id="conversation-1",
                trace_link=captured,
            ):
                pass

        spans = self.exporter.get_finished_spans()
        span = next(
            item
            for item in spans
            if item.name == "order_resolution.workflow.resume"
        )
        run = next(item for item in spans if item.name == "workflow.run")
        self.assertEqual(span.context.trace_id, resume_trace_id)
        self.assertNotEqual(span.context.trace_id, start_trace_id)
        self.assertEqual(span.parent.span_id, run.context.span_id)
        self.assertEqual(run.parent.span_id, resume_root.get_span_context().span_id)
        self.assertEqual(len(span.links), 1)
        self.assertEqual(len(run.links), 1)
        self.assertEqual(span.links[0].context.trace_id, start_trace_id)
        self.assertEqual(span.links[0].context.span_id, start_span_id)
        self.assertEqual(run.links[0].context.trace_id, start_trace_id)
        self.assertTrue(span.attributes["blueprint.trace.restart"])
        self.assertEqual(
            span.attributes["blueprint.trace.link.trace_id"],
            f"{start_trace_id:032x}",
        )

    def test_invalid_link_is_ignored_without_recording_payload(self):
        with patch(
            "app.order_resolution.observability.trace.get_tracer",
            return_value=self.tracer,
        ):
            with workflow_stage_span(
                "resume",
                case_id=self.case_id,
                conversation_id="conversation-1",
                trace_link={"payload": "private-content"},
            ):
                pass
        span = self.exporter.get_finished_spans()[-1]
        self.assertFalse(span.links)
        self.assertNotIn("private-content", span.to_json())

    def test_business_stage_names_status_and_attributes_are_bounded(self):
        with patch(
            "app.order_resolution.observability.trace.get_tracer",
            return_value=self.tracer,
        ):
            with workflow_business_stage(
                "proposal",
                case_id=self.case_id,
                conversation_id="conversation-1",
                outcome="pending",
                approval_required=True,
                proposal_version=1,
            ):
                pass
            with self.assertRaisesRegex(RuntimeError, "private payload"):
                with workflow_business_stage(
                    "effect",
                    case_id=self.case_id,
                    conversation_id="conversation-1",
                    outcome="approved",
                ):
                    raise RuntimeError("private payload")

        spans = {item.name: item for item in self.exporter.get_finished_spans()}
        proposal = spans["workflow.stage.proposal.succeeded"]
        failed = spans["workflow.stage.effect.failed"]
        self.assertEqual(proposal.attributes["blueprint.workflow.status"], "succeeded")
        self.assertTrue(proposal.attributes["blueprint.workflow.approval_required"])
        self.assertEqual(proposal.attributes["blueprint.proposal.version"], 1)
        self.assertEqual(failed.status.status_code, StatusCode.ERROR)
        self.assertEqual(failed.attributes["error.type"], "RuntimeError")
        self.assertFalse(failed.events)
        self.assertNotIn("private payload", failed.to_json())
        for invalid in ("private-stage", "", "authorization.failed"):
            with self.subTest(stage=invalid), self.assertRaises(ValueError):
                with workflow_business_stage(
                    invalid,
                    case_id=self.case_id,
                    conversation_id="conversation-1",
                ):
                    pass

    def test_hitl_marker_preserves_durable_link_without_content(self):
        with self.tracer.start_as_current_span("start") as start:
            captured = capture_trace_link()
            trace_id = start.get_span_context().trace_id
        with patch(
            "app.order_resolution.observability.trace.get_tracer",
            return_value=self.tracer,
        ):
            with workflow_marker_span(
                "hitl_resume",
                case_id=self.case_id,
                conversation_id="conversation-1",
                trace_link=captured,
                outcome="approved",
            ):
                pass
        span = self.exporter.get_finished_spans()[-1]
        self.assertEqual(span.name, "workflow.hitl_resume")
        self.assertEqual(span.links[0].context.trace_id, trace_id)
        self.assertEqual(span.attributes["blueprint.workflow.outcome"], "approved")


if __name__ == "__main__":
    unittest.main()
