import asyncio
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from azure.monitor.opentelemetry.exporter.export.trace._exporter import _convert_span_to_envelope
from opentelemetry.exporter.otlp.proto.common._internal.trace_encoder import encode_spans
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from order_resolution_hosted.observability import sanitize_async_httpx_url, sanitize_httpx_url


class HttpxUrlPrivacyTests(unittest.TestCase):
    def test_instrumented_callbacks_redact_url_and_keep_spans_metrics_and_parentage(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(self.headers.get("traceparent"))
                self.send_response(503 if "failure" in self.path else 200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        reader = InMemoryMetricReader()
        meter_provider = MeterProvider(metric_readers=[reader])
        self.addCleanup(provider.shutdown)
        self.addCleanup(meter_provider.shutdown)
        instrumentor = HTTPXClientInstrumentor()
        self.addCleanup(instrumentor.uninstrument)
        base = f"http://127.0.0.1:{server.server_port}"
        canary = "synthetic-case-privacy-canary"
        query_canary = "synthetic-query-canary"
        credentials_canary = "synthetic-credentials-canary"
        instrumentor.instrument(tracer_provider=provider, meter_provider=meter_provider)
        with httpx.Client(trust_env=False) as client:
            client.post(f"{base}/cases/{canary}/bindings/start?token={canary}")
        baseline = exporter.get_finished_spans()[-1]
        self.assertEqual(baseline.instrumentation_scope.name, "opentelemetry.instrumentation.httpx")
        self.assertIn(canary, _convert_span_to_envelope(baseline).data.base_data.data)
        instrumentor.uninstrument()
        exporter.clear()
        requests.clear()
        instrumentor.instrument(
            tracer_provider=provider,
            meter_provider=meter_provider,
            request_hook=sanitize_httpx_url,
            async_request_hook=sanitize_async_httpx_url,
        )
        tracer = provider.get_tracer("test")

        async def async_request():
            async with httpx.AsyncClient(trust_env=False) as client:
                return await client.post(f"{base}/cases/{canary}/failure?search={query_canary}")

        with tracer.start_as_current_span("invoke_workflow") as parent:
            with httpx.Client(trust_env=False) as client:
                self.assertEqual(
                    client.post(
                        f"http://{credentials_canary}:pass@127.0.0.1:{server.server_port}"
                        f"/cases/{canary}/bindings/start?search={query_canary}"
                    ).status_code,
                    200,
                )
            self.assertEqual(asyncio.run(async_request()).status_code, 503)
            parent_id = parent.get_span_context().span_id
        spans = [span for span in exporter.get_finished_spans() if span.name == "POST"]
        self.assertEqual(len(spans), 2)
        self.assertEqual(len(requests), 2)
        for span, traceparent in zip(spans, requests):
            self.assertEqual(span.instrumentation_scope.name, "opentelemetry.instrumentation.httpx")
            self.assertEqual(span.parent.span_id, parent_id)
            self.assertIn(f"{span.context.span_id:016x}", traceparent)
            self.assertEqual(span.attributes["http.url"], f"{base}/")
            self.assertEqual(span.attributes["url.full"], f"{base}/")
            envelope = _convert_span_to_envelope(span)
            for value in (canary, query_canary, credentials_canary):
                self.assertNotIn(value, str(envelope))
                self.assertNotIn(value.encode(), encode_spans([span]).SerializeToString())
        self.assertEqual(spans[1].status.status_code, StatusCode.ERROR)
        self.assertEqual(_convert_span_to_envelope(spans[1]).data.base_data.result_code, "503")
        metrics = reader.get_metrics_data()
        names = {
            metric.name
            for resource in metrics.resource_metrics
            for scope in resource.scope_metrics
            for metric in scope.metrics
        }
        self.assertTrue(names & {"http.client.duration", "http.client.request.duration"})
