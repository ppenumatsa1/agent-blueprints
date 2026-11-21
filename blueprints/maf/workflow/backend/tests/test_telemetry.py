import asyncio
import json
import logging
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricExportResult
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.api import create_app
from app.config import Settings
from app.infrastructure.telemetry import SafeExporter, SafeMetricExporter, Telemetry, instrumented
from app.infrastructure.delegation import OnBehalfOf
from app.infrastructure.identity import AuthenticatedRequest
from app.infrastructure.store import PostgresStore
from app.domain.errors import DelegationError


CANARY = "secret-canary-prompt-token-tool-result-sql-identifier"


def fake_metric_exporter():
    exporter = Mock()
    exporter._preferred_temporality = None
    exporter._preferred_aggregation = None
    exporter.force_flush.return_value = True
    exporter.export.return_value = MetricExportResult.SUCCESS
    return exporter


class TelemetryTests(unittest.TestCase):
    def app(self, *, store=None, components=None):
        checkpoint_dir = tempfile.TemporaryDirectory(dir=".")
        self.addCleanup(checkpoint_dir.cleanup)
        store = store if store is not None else Mock()
        store.recoverable.return_value = []
        components = components if components is not None else Mock()
        settings = Settings(
            "10000000-0000-4000-8000-000000000001",
            "20000000-0000-4000-8000-000000000002",
            "postgresql://localhost/test",
            Path(checkpoint_dir.name),
        )
        return create_app(settings, components, store=store, identity=Mock())

    def test_request_correlation_privacy_and_error(self):
        app = self.app()
        exporter = InMemorySpanExporter()
        app.state.telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))

        @app.get("/test-error")
        async def fail():
            raise RuntimeError(CANARY)

        trace_id = "1234567890abcdef1234567890abcdef"
        with self.assertLogs("blueprint.telemetry", level="INFO") as logs:
            with TestClient(app) as client:
                response = client.get(
                    "/test-error?" + CANARY,
                    headers={
                        "traceparent": f"00-{trace_id}-1234567890abcdef-01",
                        "tracestate": "secret=" + CANARY,
                        "baggage": "secret=" + CANARY,
                        "Authorization": "Bearer " + CANARY,
                    },
                )
                self.assertEqual(response.status_code, 500)
                correlation = response.headers["X-Correlation-ID"]
                UUID(correlation)

                # The nested operation inherits the server span's context.
                @app.get("/test-child")
                async def child():
                    with app.state.telemetry.operation("workflow.resume"):
                        pass
                    return {"ok": True}

                child_response = client.get(
                    "/test-child",
                    headers={
                        "traceparent": f"00-{trace_id}-1234567890abcdef-01",
                    },
                )
                self.assertEqual(child_response.status_code, 200)
                unsampled = client.get(
                    "/healthz",
                    headers={
                        "traceparent": f"00-{trace_id}-1234567890abcdef-00",
                    },
                )
                self.assertEqual(unsampled.status_code, 204)
                unsampled_error = client.get(
                    "/test-error",
                    headers={
                        "traceparent": f"00-{trace_id}-1234567890abcdef-00",
                    },
                )
                self.assertEqual(unsampled_error.status_code, 500)
                denied = client.get("/api/cases/30000000-0000-4000-8000-000000000003")
                self.assertEqual(denied.status_code, 401)

        records = [json.loads(line.split(":", 2)[2]) for line in logs.output]
        request = next(r for r in records if r.get("correlation_id") == correlation)
        self.assertEqual(request["trace_id"], trace_id)
        self.assertEqual(request["outcome"], "error")
        denied_log = next(
            r for r in records if r.get("correlation_id") == denied.headers["X-Correlation-ID"]
        )
        self.assertEqual(
            (denied_log["outcome"], denied_log["http_status_code"]), ("client_error", 401)
        )
        unsampled_log = next(
            r
            for r in records
            if r.get("correlation_id") == unsampled_error.headers["X-Correlation-ID"]
        )
        self.assertEqual(
            (unsampled_log["outcome"], unsampled_log["http_status_code"]), ("error", 500)
        )
        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 4)
        error = next(s for s in spans if s.status.status_code == StatusCode.ERROR)
        self.assertFalse(error.events)
        child = next(s for s in spans if s.name == "workflow.resume")
        self.assertEqual(child.context.trace_id, int(trace_id, 16))
        self.assertTrue(any(s.context.span_id == child.parent.span_id for s in spans))
        self.assertNotIn(CANARY, str(records) + repr(spans) + "".join(s.to_json() for s in spans))

    def test_bad_trace_context_and_export_failures_are_safe(self):
        fake = Mock()
        fake.export.side_effect = RuntimeError(CANARY)
        fake.force_flush.side_effect = RuntimeError(CANARY)
        fake.shutdown.side_effect = RuntimeError(CANARY)
        safe = SafeExporter(fake)
        with self.assertLogs("blueprint.telemetry", level="INFO") as logs:
            self.assertEqual(safe.export(()), SpanExportResult.FAILURE)
            self.assertFalse(safe.force_flush())
            safe.shutdown()
            telemetry = Telemetry()
            with telemetry.operation(
                "workflow.resume",
                parent=telemetry.parent_from_headers({"traceparent": CANARY, "baggage": CANARY}),
            ):
                pass
            telemetry.shutdown()
        self.assertNotIn(CANARY, str(logs.output))
        self.assertIn('"outcome":"failure"', str(logs.output))

    def test_exporter_failure_does_not_change_operation(self):
        exporter = Mock()
        exporter.export.side_effect = RuntimeError(CANARY)
        exporter.force_flush.return_value = True
        metric_exporter = fake_metric_exporter()
        metric_exporter.export.side_effect = RuntimeError(CANARY)
        telemetry = Telemetry(
            "azure-monitor", "test", exporter=exporter, metric_exporter=metric_exporter
        )
        with self.assertLogs("blueprint.telemetry", level="INFO") as logs:
            with telemetry.operation("workflow.resume"):
                result = "completed"
            telemetry.provider.force_flush()
            telemetry.meter_provider.force_flush()
            telemetry.shutdown()
        self.assertEqual(result, "completed")
        self.assertIn('"outcome":"failure"', str(logs.output))
        self.assertIn('"event":"telemetry.metric_export"', str(logs.output))
        self.assertNotIn(CANARY, str(logs.output))

    def test_logging_failure_uses_fixed_stderr_signal_without_changing_operation(self):
        telemetry = Telemetry()
        self.addCleanup(telemetry.shutdown)
        fallback = b'{"event":"telemetry.log","outcome":"failure"}\n'

        with (
            patch("app.infrastructure.telemetry._log.info", side_effect=RuntimeError(CANARY)),
            patch("app.infrastructure.telemetry.os.write") as write_stderr,
        ):
            with telemetry.operation("workflow.resume"):
                result = "completed"
        self.assertEqual(result, "completed")
        write_stderr.assert_called_once_with(2, fallback)
        self.assertNotIn(CANARY, repr(write_stderr.call_args))

        error = ValueError(CANARY)
        with (
            patch("app.infrastructure.telemetry._log.info", side_effect=RuntimeError(CANARY)),
            patch("app.infrastructure.telemetry.os.write") as write_stderr,
        ):
            with self.assertRaises(ValueError) as caught:
                with telemetry.operation("workflow.resume"):
                    raise error
        self.assertIs(caught.exception, error)
        write_stderr.assert_called_once_with(2, fallback)

        with (
            patch("app.infrastructure.telemetry._log.info", side_effect=RuntimeError(CANARY)),
            patch("app.infrastructure.telemetry.os.write", side_effect=OSError(CANARY)),
        ):
            with telemetry.operation("workflow.resume"):
                result = "completed despite stderr failure"
        self.assertEqual(result, "completed despite stderr failure")

    def test_instrumentation_failures_preserve_action_and_original_exception(self):
        class Action:
            def __init__(self, telemetry, error):
                self.telemetry = telemetry
                self.error = error
                self.calls = 0

            @instrumented("workflow.resume")
            def run(self):
                self.calls += 1
                if self.error is not None:
                    raise self.error
                return "completed"

        for stage in ("start", "enter", "status", "context", "close"):
            for raises in (False, True):
                with self.subTest(stage=stage, application_error=raises):
                    telemetry = Telemetry()
                    self.addCleanup(telemetry.shutdown)
                    span = Mock()
                    span.get_span_context.return_value = Mock(trace_id=1, span_id=2)
                    manager = MagicMock()
                    manager.__enter__.return_value = span
                    tracer = Mock()
                    tracer.start_as_current_span.return_value = manager
                    telemetry.tracer = tracer
                    failure = RuntimeError(CANARY)
                    if stage == "start":
                        tracer.start_as_current_span.side_effect = failure
                    elif stage == "enter":
                        manager.__enter__.side_effect = failure
                    elif stage == "status":
                        span.set_status.side_effect = failure
                    elif stage == "context":
                        span.get_span_context.side_effect = failure
                    else:
                        manager.__exit__.side_effect = failure
                    error = ValueError("application error") if raises else None
                    action = Action(telemetry, error)
                    # A successful action does not set span status itself.
                    if stage == "status" and not raises:
                        continue
                    with self.assertLogs("blueprint.telemetry", level="INFO") as logs:
                        if raises:
                            with self.assertRaises(ValueError) as caught:
                                action.run()
                            self.assertIs(caught.exception, error)
                        else:
                            self.assertEqual(action.run(), "completed")
                    self.assertEqual(action.calls, 1)
                    self.assertIn('"event":"telemetry.instrumentation"', str(logs.output))
                    self.assertNotIn(CANARY, str(logs.output))
                    if stage not in ("start", "enter"):
                        manager.__exit__.assert_called_once_with(None, None, None)

    def test_http_metadata_and_propagation_failures_do_not_change_response(self):
        app = self.app()
        span = Mock()
        span.set_attribute.side_effect = RuntimeError(CANARY)
        span.set_status.side_effect = RuntimeError(CANARY)
        span.get_span_context.return_value = Mock(trace_id=1, span_id=2)
        manager = MagicMock()
        manager.__enter__.return_value = span
        app.state.telemetry.tracer = Mock()
        app.state.telemetry.tracer.start_as_current_span.return_value = manager
        calls = []

        @app.get("/telemetry-failure")
        async def route():
            calls.append(1)
            return {"ok": True}

        @app.get("/telemetry-failure-error")
        async def route_error():
            calls.append(2)
            raise RuntimeError(CANARY)

        with (
            patch(
                "app.infrastructure.telemetry._propagator.extract", side_effect=RuntimeError(CANARY)
            ),
            self.assertLogs("blueprint.telemetry", level="INFO") as logs,
            TestClient(app) as client,
        ):
            response = client.get("/telemetry-failure")
            response_error = client.get("/telemetry-failure-error")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        UUID(response.headers["X-Correlation-ID"])
        self.assertEqual(response_error.status_code, 500)
        self.assertEqual(calls, [1, 2])
        span.set_status.assert_called_once()
        self.assertIn('"event":"telemetry.instrumentation"', str(logs.output))
        self.assertNotIn(CANARY, str(logs.output))

    def test_async_action_executes_once_when_span_start_fails(self):
        telemetry = Telemetry()
        self.addCleanup(telemetry.shutdown)
        telemetry.tracer = Mock()
        telemetry.tracer.start_as_current_span.side_effect = RuntimeError(CANARY)

        class Action:
            def __init__(self):
                self.telemetry = telemetry
                self.calls = 0

            @instrumented("workflow.start")
            async def run(self, error):
                self.calls += 1
                if error is not None:
                    raise error
                return "completed"

        action = Action()
        error = ValueError("application error")
        with self.assertLogs("blueprint.telemetry", level="INFO") as logs:
            self.assertEqual(asyncio.run(action.run(None)), "completed")
            with self.assertRaises(ValueError) as caught:
                asyncio.run(action.run(error))
        self.assertIs(caught.exception, error)
        self.assertEqual(action.calls, 2)
        self.assertEqual(sum("telemetry.instrumentation" in line for line in logs.output), 2)
        self.assertNotIn(CANARY, str(logs.output))

    def test_startup_failures_shutdown_telemetry_and_preserve_original_error(self):
        for stage in ("host", "app", "store", "components", "recovery"):
            with self.subTest(stage=stage):
                telemetry = Mock()
                store, components = Mock(), Mock()
                store.recoverable.return_value = []
                error = RuntimeError(CANARY)
                if stage == "store":
                    store.initialize.side_effect = error
                elif stage == "components":
                    components.initialize.side_effect = error
                elif stage == "recovery":
                    store.recoverable.side_effect = error
                with patch("app.api.Telemetry", return_value=telemetry):
                    if stage in ("host", "app"):
                        target = (
                            "app.api.LocalWorkflowHost" if stage == "host" else "app.api.FastAPI"
                        )
                        with patch(target, side_effect=error):
                            with self.assertRaises(RuntimeError) as caught:
                                self.app(store=store, components=components)
                    else:
                        app = self.app(store=store, components=components)
                        with self.assertRaises(RuntimeError) as caught:
                            with TestClient(app):
                                pass
                self.assertIs(caught.exception, error)
                telemetry.shutdown.assert_called_once_with()

    def test_provider_initialization_failures_close_created_exporters(self):
        for stage in ("trace", "meter"):
            with self.subTest(stage=stage):
                trace_exporter = Mock()
                metric_exporter = fake_metric_exporter()
                target = (
                    "app.infrastructure.telemetry.TracerProvider.get_tracer"
                    if stage == "trace"
                    else "app.infrastructure.telemetry.MeterProvider.get_meter"
                )
                with patch(target, side_effect=RuntimeError(CANARY)):
                    with self.assertRaisesRegex(
                        RuntimeError, "^Azure Monitor telemetry initialization failed[.]$"
                    ) as caught:
                        Telemetry(
                            "azure-monitor",
                            "configured",
                            exporter=trace_exporter,
                            metric_exporter=metric_exporter,
                        )
                trace_exporter.shutdown.assert_called_once()
                metric_exporter.shutdown.assert_called_once()
                self.assertNotIn(CANARY, str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)

    def test_dependency_exception_payload_is_not_recorded(self):
        telemetry = Telemetry()
        exporter = InMemorySpanExporter()
        telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))
        with self.assertLogs("blueprint.telemetry", level="INFO") as logs:
            with self.assertRaisesRegex(RuntimeError, CANARY):
                with telemetry.operation("workflow.resume"):
                    raise RuntimeError(CANARY)
        spans = exporter.get_finished_spans()
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
        self.assertFalse(spans[0].events)
        self.assertNotIn(CANARY, str(logs.output) + spans[0].to_json())
        telemetry.shutdown()

    def test_database_and_obo_failure_canaries_are_not_recorded(self):
        telemetry = Telemetry()
        exporter = InMemorySpanExporter()
        telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))
        store = PostgresStore("postgresql://localhost/" + CANARY)
        store.telemetry = telemetry
        settings = replace(
            Settings(
                "10000000-0000-4000-8000-000000000001",
                "20000000-0000-4000-8000-000000000002",
                "postgresql://localhost/test",
                Path("."),
            ),
            obo_enabled=True,
            obo_client_secret=CANARY,
            obo_allowed_scopes=("api://example/read",),
        )
        client = Mock()
        client.acquire_token_on_behalf_of.side_effect = RuntimeError(CANARY)
        obo = OnBehalfOf(settings, client_factory=Mock(return_value=client), telemetry=telemetry)
        with self.assertLogs("blueprint.telemetry", level="INFO") as logs:
            with patch("psycopg.connect", side_effect=RuntimeError(CANARY)):
                with self.assertRaises(RuntimeError):
                    store.get(UUID("30000000-0000-4000-8000-000000000003"))
            with self.assertRaises(DelegationError):
                obo.exchange(AuthenticatedRequest(None, CANARY), ("api://example/read",))
        spans = exporter.get_finished_spans()
        self.assertEqual(
            {s.name for s in spans}, {"database.connect", "database.read", "identity.obo"}
        )
        self.assertNotIn(CANARY, str(logs.output) + "".join(s.to_json() for s in spans))
        self.assertTrue(all(not s.events for s in spans))
        telemetry.shutdown()

    def test_sdk_error_logging_is_not_forwarded(self):
        exporter = Mock()

        def fail(_spans):
            logging.getLogger(
                "azure.monitor.opentelemetry.exporter.export.trace._exporter"
            ).exception(CANARY)
            return SpanExportResult.FAILURE

        exporter.export.side_effect = fail
        exporter.force_flush.return_value = True
        root_handler = Mock(spec=logging.Handler)
        root_handler.level = logging.NOTSET
        root = logging.getLogger()
        root.addHandler(root_handler)
        try:
            with (
                patch(
                    "azure.monitor.opentelemetry.exporter.AzureMonitorTraceExporter",
                    return_value=exporter,
                ),
                patch(
                    "azure.monitor.opentelemetry.exporter.AzureMonitorMetricExporter",
                    return_value=fake_metric_exporter(),
                ),
            ):
                telemetry = Telemetry("azure-monitor", "not-a-real-connection-string")
                with telemetry.operation("workflow.resume"):
                    pass
                telemetry.provider.force_flush()
                telemetry.shutdown()
            self.assertFalse(
                any(CANARY in str(call) for call in root_handler.handle.call_args_list)
            )
        finally:
            root.removeHandler(root_handler)

    def test_azure_envelope_does_not_default_to_host_identifier(self):
        from azure.monitor.opentelemetry.exporter import _utils
        from azure.monitor.opentelemetry.exporter.export.trace._exporter import (
            _convert_span_to_envelope,
        )

        telemetry = Telemetry()
        exporter = InMemorySpanExporter()
        telemetry.provider.add_span_processor(SimpleSpanProcessor(exporter))
        with telemetry.operation("workflow.resume"):
            pass
        with patch.dict(_utils.azure_monitor_context, {"ai.device.id": CANARY}):
            envelope = _convert_span_to_envelope(exporter.get_finished_spans()[0])
        self.assertNotIn(CANARY, str(envelope.tags))
        self.assertEqual(envelope.tags["ai.device.id"], "not-collected")
        self.assertEqual(envelope.tags["ai.cloud.roleInstance"], "not-collected")
        self.assertEqual(envelope.tags["ai.internal.nodeName"], "not-collected")
        telemetry.shutdown()

    def test_azure_auxiliary_collection_is_disabled(self):
        fake = Mock()
        with (
            patch.dict(os.environ, {}, clear=False),
            patch(
                "azure.monitor.opentelemetry.exporter.AzureMonitorTraceExporter", return_value=fake
            ),
            patch(
                "azure.monitor.opentelemetry.exporter.AzureMonitorMetricExporter",
                return_value=fake_metric_exporter(),
            ),
        ):
            telemetry = Telemetry("azure-monitor", "not-a-real-connection-string")
            for name in (
                "APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL",
                "APPLICATIONINSIGHTS_SDKSTATS_DISABLED",
                "APPLICATIONINSIGHTS_CONTROLPLANE_DISABLED",
            ):
                self.assertEqual(os.environ[name], "true")
            telemetry.shutdown()

    def test_azure_configuration_is_required_and_invalid_initialization_fails_closed(self):
        settings = Settings(
            "10000000-0000-4000-8000-000000000001",
            "20000000-0000-4000-8000-000000000002",
            "postgresql://localhost/test",
            Path("."),
        )
        for connection in (None, "", "   "):
            with self.subTest(connection=connection):
                with self.assertRaisesRegex(ValueError, "APPLICATIONINSIGHTS_CONNECTION_STRING"):
                    replace(
                        settings,
                        telemetry_mode="azure-monitor",
                        applicationinsights_connection_string=connection,
                    )
                with self.assertRaisesRegex(ValueError, "APPLICATIONINSIGHTS_CONNECTION_STRING"):
                    Telemetry("azure-monitor", connection)
        with patch(
            "azure.monitor.opentelemetry.exporter.AzureMonitorTraceExporter",
            side_effect=ValueError(CANARY),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "^Azure Monitor telemetry initialization failed[.]$"
            ) as exc:
                Telemetry("azure-monitor", "invalid-" + CANARY)
            self.assertNotIn(CANARY, str(exc.exception))
            self.assertTrue(exc.exception.__suppress_context__)
        with self.assertRaisesRegex(
            RuntimeError, "^Azure Monitor telemetry initialization failed[.]$"
        ) as exc:
            Telemetry("azure-monitor", "invalid-" + CANARY)
        self.assertNotIn(CANARY, str(exc.exception))

    def test_metric_initialization_failure_cleans_up_and_is_not_silent(self):
        exporter = Mock()
        metric_exporter = fake_metric_exporter()
        metric_exporter._metrics_to_log_analytics = False
        with self.assertRaisesRegex(RuntimeError, "Azure Monitor telemetry initialization failed"):
            Telemetry(
                "azure-monitor", "configured", exporter=exporter, metric_exporter=metric_exporter
            )
        exporter.shutdown.assert_called_once()
        metric_exporter.shutdown.assert_called_once()
        exporter = Mock()
        with patch(
            "azure.monitor.opentelemetry.exporter.AzureMonitorMetricExporter",
            side_effect=ValueError(CANARY),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "^Azure Monitor telemetry initialization failed[.]$"
            ) as exc:
                Telemetry("azure-monitor", "configured", exporter=exporter)
        exporter.shutdown.assert_called_once()
        self.assertNotIn(CANARY, str(exc.exception))
        self.assertTrue(exc.exception.__suppress_context__)

    def test_metrics_use_only_allowlisted_labels_and_no_exemplars_or_host_identifier(self):
        from azure.monitor.opentelemetry.exporter import _utils
        from azure.monitor.opentelemetry.exporter.export.metrics._exporter import (
            _convert_point_to_envelope,
        )

        reader = InMemoryMetricReader()
        telemetry = Telemetry(metric_reader=reader)
        with telemetry.operation("workflow.resume", correlation_id=CANARY):
            pass
        with self.assertRaises(RuntimeError):
            with telemetry.operation("workflow.resume"):
                raise RuntimeError(CANARY)
        with telemetry.operation(CANARY):
            pass
        data = reader.get_metrics_data()
        self.assertNotIn(CANARY, data.to_json())
        resources = data.resource_metrics
        metrics = resources[0].scope_metrics[0].metrics
        self.assertEqual(
            {metric.name for metric in metrics},
            {"blueprint.operations", "blueprint.operation.duration"},
        )
        for metric in metrics:
            points = metric.data.data_points
            labels = {(p.attributes["operation"], p.attributes["outcome"]) for p in points}
            self.assertEqual(
                labels,
                {
                    ("workflow.resume", "success"),
                    ("workflow.resume", "error"),
                    ("other", "success"),
                },
            )
            for point in points:
                self.assertEqual(set(point.attributes), {"operation", "outcome"})
                self.assertFalse(point.exemplars)
                with patch.dict(_utils.azure_monitor_context, {"ai.device.id": CANARY}):
                    envelope = _convert_point_to_envelope(point, metric.name, resources[0].resource)
                self.assertNotIn(CANARY, str(envelope.as_dict()))
                self.assertEqual(envelope.tags["ai.device.id"], "not-collected")
                self.assertEqual(envelope.tags["ai.cloud.roleInstance"], "not-collected")
                self.assertEqual(envelope.tags["ai.internal.nodeName"], "not-collected")
        telemetry.shutdown()

    def test_request_canaries_do_not_reach_metrics_even_when_unsampled(self):
        reader = InMemoryMetricReader()
        with patch(
            "app.api.Telemetry", side_effect=lambda *args: Telemetry(*args, metric_reader=reader)
        ):
            app = self.app()

        @app.get("/test-metric-error")
        async def fail():
            raise RuntimeError(CANARY)

        with TestClient(app) as client:
            response = client.get(
                "/test-metric-error?" + CANARY,
                headers={
                    "traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-00",
                    "Authorization": "Bearer " + CANARY,
                    "baggage": "secret=" + CANARY,
                },
            )
            self.assertEqual(response.status_code, 500)
            data = reader.get_metrics_data()
            payload = data.to_json()
            self.assertNotIn(CANARY, payload)
            self.assertNotIn(response.headers["X-Correlation-ID"], payload)
            metrics = data.resource_metrics[0].scope_metrics[0].metrics
            self.assertTrue(
                all(
                    p.attributes == {"operation": "http.request", "outcome": "error"}
                    and not p.exemplars
                    for metric in metrics
                    for p in metric.data.data_points
                )
            )

    def test_metric_export_failure_status_and_exception_are_signaled(self):
        exporter = fake_metric_exporter()
        safe = SafeMetricExporter(exporter)
        with self.assertLogs("blueprint.telemetry", level="INFO") as logs:
            exporter.export.return_value = MetricExportResult.FAILURE
            self.assertEqual(safe.export(None), MetricExportResult.FAILURE)
            exporter.export.side_effect = RuntimeError(CANARY)
            self.assertEqual(safe.export(None), MetricExportResult.FAILURE)
            exporter.force_flush.side_effect = RuntimeError(CANARY)
            self.assertFalse(safe.force_flush())
            exporter.shutdown.side_effect = RuntimeError(CANARY)
            safe.shutdown()
        self.assertNotIn(CANARY, str(logs.output))
        self.assertEqual(sum("telemetry.metric_export" in line for line in logs.output), 2)
        self.assertIn("telemetry.metric_flush", str(logs.output))
        self.assertIn("telemetry.metric_shutdown", str(logs.output))

    def test_configured_azure_pipeline_exports_metrics_with_safe_dimensions(self):
        exporter = fake_metric_exporter()
        trace_exporter = Mock()
        trace_exporter.export.return_value = SpanExportResult.SUCCESS
        trace_exporter.force_flush.return_value = True
        telemetry = Telemetry(
            "azure-monitor", "configured", exporter=trace_exporter, metric_exporter=exporter
        )
        with telemetry.operation("workflow.resume", correlation_id=CANARY):
            pass
        telemetry.meter_provider.force_flush()
        exported = exporter.export.call_args.args[0]
        self.assertNotIn(CANARY, exported.to_json())
        metrics = exported.resource_metrics[0].scope_metrics[0].metrics
        self.assertEqual(
            {metric.name for metric in metrics},
            {"blueprint.operations", "blueprint.operation.duration"},
        )
        self.assertTrue(all(not p.exemplars for m in metrics for p in m.data.data_points))
        telemetry.shutdown()


if __name__ == "__main__":
    unittest.main()
