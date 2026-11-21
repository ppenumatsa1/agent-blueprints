"""Allowlisted operational telemetry; never inspect application payloads."""

import json
import logging
import os
import time
import inspect
from contextlib import contextmanager
from functools import wraps
from uuid import UUID

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExportResult, SpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


_log = logging.getLogger("blueprint.telemetry")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
_log.setLevel(logging.INFO)
_log.propagate = False
_propagator = TraceContextTextMapPropagator()
_OPERATIONS = frozenset(
    {
        "http.request",
        "workflow.start",
        "workflow.resume",
        "database.connect",
        "database.read",
        "database.create",
        "database.decision",
        "database.finish",
        "identity.obo",
    }
)


def _emit(event: str, **fields) -> None:
    try:
        _log.info(json.dumps({"event": event, **fields}, separators=(",", ":")))
    except Exception:
        # Operational telemetry must not affect application execution.
        pass


def instrumented(name):
    def decorate(func):
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(self, *args, **kwargs):
                if self.telemetry is None:
                    return await func(self, *args, **kwargs)
                with self.telemetry.operation(name):
                    return await func(self, *args, **kwargs)

            return async_wrapper

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if self.telemetry is None:
                return func(self, *args, **kwargs)
            with self.telemetry.operation(name):
                return func(self, *args, **kwargs)

        return wrapper

    return decorate


class SafeExporter(SpanExporter):
    """Keep exporter errors and exception text out of operational logs."""

    def __init__(self, exporter):
        self._exporter = exporter

    def export(self, spans):
        try:
            result = self._exporter.export(spans)
        except Exception:
            result = SpanExportResult.FAILURE
        if result != SpanExportResult.SUCCESS:
            _emit("telemetry.export", outcome="failure")
        return result

    def shutdown(self):
        try:
            self._exporter.shutdown()
        except Exception:
            _emit("telemetry.shutdown", outcome="failure")

    def force_flush(self, timeout_millis=30000):
        try:
            ok = self._exporter.force_flush(timeout_millis)
        except Exception:
            ok = False
        if not ok:
            _emit("telemetry.flush", outcome="failure")
        return ok


class _Operation:
    def __init__(self, span):
        self.span = span
        self.status = StatusCode.UNSET
        self.http_status = None

    def set_attribute(self, name, value):
        if name == "http.response.status_code" and isinstance(value, int):
            self.http_status = value
            self.span.set_attribute(name, value)

    def set_status(self, status):
        self.status = status.status_code
        self.span.set_status(status)


class Telemetry:
    def __init__(self, mode="local", connection_string=None, *, exporter=None):
        self.provider = TracerProvider(
            resource=Resource(
                {
                    "service.name": "maf-workflow",
                    "service.instance.id": "not-collected",
                    "device.id": "not-collected",
                }
            )
        )
        self.tracer = self.provider.get_tracer("blueprint.manual")
        if mode not in ("local", "azure-monitor"):
            raise ValueError("TELEMETRY_MODE must be local or azure-monitor.")
        if mode == "azure-monitor":
            try:
                if exporter is None:
                    if not connection_string:
                        raise ValueError("Missing connection string.")
                    # Do not let exporter diagnostics collect environment identifiers.
                    for setting in (
                        "APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL",
                        "APPLICATIONINSIGHTS_SDKSTATS_DISABLED",
                        "APPLICATIONINSIGHTS_CONTROLPLANE_DISABLED",
                    ):
                        os.environ[setting] = "true"
                    # The SDK can log exception messages and endpoints; failures
                    # are instead reported by SafeExporter without their text.
                    for namespace in (
                        "azure.monitor.opentelemetry.exporter",
                        "azure.core.pipeline",
                    ):
                        sdk_log = logging.getLogger(namespace)
                        sdk_log.addHandler(logging.NullHandler())
                        sdk_log.propagate = False
                    from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

                    exporter = AzureMonitorTraceExporter(
                        connection_string=connection_string, disable_offline_storage=True
                    )
                self.provider.add_span_processor(BatchSpanProcessor(SafeExporter(exporter)))
                _emit("telemetry.export", outcome="configured")
            except Exception:
                _emit("telemetry.export", outcome="unavailable")
        else:
            _emit("telemetry.export", outcome="disabled")

    @contextmanager
    def operation(self, name, *, kind=SpanKind.INTERNAL, parent=None, correlation_id=None):
        if name not in _OPERATIONS:
            name = "other"
        start = time.monotonic()
        # Exceptions are classified without message, stack, or automatic span events.
        with self.tracer.start_as_current_span(
            name, context=parent, kind=kind, record_exception=False, set_status_on_exception=False
        ) as span:
            operation = _Operation(span)
            outcome = "success"
            try:
                yield operation
            except BaseException:
                outcome = "error"
                operation.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                if operation.status == StatusCode.ERROR:
                    outcome = "error"
                ctx = span.get_span_context()
                fields = dict(
                    operation=name,
                    outcome=outcome,
                    duration_ms=round((time.monotonic() - start) * 1000, 3),
                    trace_id=f"{ctx.trace_id:032x}",
                    span_id=f"{ctx.span_id:016x}",
                )
                status_code = operation.http_status
                if isinstance(status_code, int):
                    fields["http_status_code"] = status_code
                    if 400 <= status_code < 500:
                        fields["outcome"] = "client_error"
                if correlation_id is not None:
                    try:
                        fields["correlation_id"] = str(UUID(correlation_id))
                    except (ValueError, TypeError, AttributeError):
                        pass
                _emit(
                    "operation",
                    **fields,
                )

    def parent_from_headers(self, headers):
        # Only the W3C traceparent field is accepted: no baggage or tracestate.
        return _propagator.extract({"traceparent": headers.get("traceparent", "")})

    def shutdown(self):
        try:
            self.provider.shutdown()
        except Exception:
            _emit("telemetry.shutdown", outcome="failure")
