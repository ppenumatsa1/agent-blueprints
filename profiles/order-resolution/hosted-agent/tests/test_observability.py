import unittest
from unittest.mock import patch
from uuid import UUID

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.order_resolution.observability import capture_trace_link, workflow_stage_span


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.provider = TracerProvider()
        self.exporter = InMemorySpanExporter()
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = self.provider.get_tracer("test")
        self.case_id = UUID("20000000-0000-4000-8000-000000000002")

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

        span = next(
            item
            for item in self.exporter.get_finished_spans()
            if item.name == "order_resolution.workflow.resume"
        )
        self.assertEqual(span.context.trace_id, resume_trace_id)
        self.assertNotEqual(span.context.trace_id, start_trace_id)
        self.assertEqual(span.parent.span_id, resume_root.get_span_context().span_id)
        self.assertEqual(len(span.links), 1)
        self.assertEqual(span.links[0].context.trace_id, start_trace_id)
        self.assertEqual(span.links[0].context.span_id, start_span_id)
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


if __name__ == "__main__":
    unittest.main()
