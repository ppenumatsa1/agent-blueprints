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
from opentelemetry.sdk.metrics import AlwaysOffExemplarFilter, MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricExportResult,
    PeriodicExportingMetricReader,
)
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


class SafeMetricExporter(MetricExporter):
    """Report metric exporter failures without exposing payload or exception text."""

    def __init__(self, exporter):
        super().__init__(
            preferred_temporality=exporter._preferred_temporality,
            preferred_aggregation=exporter._preferred_aggregation,
        )
        self._exporter = exporter

    def export(self, metrics_data, timeout_millis=10000, **kwargs):
        try:
            result = self._exporter.export(metrics_data, timeout_millis=timeout_millis, **kwargs)
        except Exception:
            result = MetricExportResult.FAILURE
        if result != MetricExportResult.SUCCESS:
            _emit("telemetry.metric_export", outcome="failure")
        return result

    def shutdown(self, timeout_millis=30000, **kwargs):
        try:
            self._exporter.shutdown(timeout_millis=timeout_millis, **kwargs)
        except Exception:
            _emit("telemetry.metric_shutdown", outcome="failure")

    def force_flush(self, timeout_millis=10000):
        try:
            ok = self._exporter.force_flush(timeout_millis=timeout_millis)
        except Exception:
            ok = False
        if not ok:
            _emit("telemetry.metric_flush", outcome="failure")
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
    def __init__(
        self,
        mode="local",
        connection_string=None,
        *,
        exporter=None,
        metric_exporter=None,
        metric_reader=None,
    ):
        if mode not in ("local", "azure-monitor"):
            raise ValueError("TELEMETRY_MODE must be local or azure-monitor.")
        if mode == "azure-monitor" and (
            not isinstance(connection_string, str) or not connection_string.strip()
        ):
            raise ValueError("APPLICATIONINSIGHTS_CONNECTION_STRING is required for azure-monitor.")
        if mode == "azure-monitor" and metric_reader is not None:
            raise ValueError("A custom metric reader cannot replace Azure Monitor export.")

        resource = Resource(
            {
                "service.name": "maf-workflow",
                "service.instance.id": "not-collected",
                "device.id": "not-collected",
            }
        )
        readers = [metric_reader] if metric_reader is not None else []
        if mode == "azure-monitor":
            try:
                # Do not let exporter diagnostics collect environment identifiers.
                for setting in (
                    "APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL",
                    "APPLICATIONINSIGHTS_SDKSTATS_DISABLED",
                    "APPLICATIONINSIGHTS_CONTROLPLANE_DISABLED",
                ):
                    os.environ[setting] = "true"
                for namespace in ("azure.monitor.opentelemetry.exporter", "azure.core.pipeline"):
                    sdk_log = logging.getLogger(namespace)
                    if not any(
                        isinstance(handler, logging.NullHandler) for handler in sdk_log.handlers
                    ):
                        sdk_log.addHandler(logging.NullHandler())
                    sdk_log.propagate = False
                from azure.monitor.opentelemetry.exporter import (
                    AzureMonitorMetricExporter,
                    AzureMonitorTraceExporter,
                )

                if exporter is None:
                    exporter = AzureMonitorTraceExporter(
                        connection_string=connection_string, disable_offline_storage=True
                    )
                if metric_exporter is None:
                    metric_exporter = AzureMonitorMetricExporter(
                        connection_string=connection_string, disable_offline_storage=True
                    )
                if getattr(metric_exporter, "_metrics_to_log_analytics", True) is False:
                    raise ValueError("Azure Monitor custom metric export is disabled.")
                readers.append(PeriodicExportingMetricReader(SafeMetricExporter(metric_exporter)))
            except Exception:
                if metric_exporter is not None:
                    try:
                        metric_exporter.shutdown()
                    except Exception:
                        pass
                if exporter is not None:
                    try:
                        exporter.shutdown()
                    except Exception:
                        pass
                raise RuntimeError("Azure Monitor telemetry initialization failed.") from None
        self.provider = TracerProvider(resource=resource)
        self.tracer = self.provider.get_tracer("blueprint.manual")
        self.meter_provider = MeterProvider(
            resource=resource, metric_readers=readers, exemplar_filter=AlwaysOffExemplarFilter()
        )
        meter = self.meter_provider.get_meter("blueprint.manual")
        self._operations = meter.create_counter("blueprint.operations", unit="{operation}")
        self._duration = meter.create_histogram("blueprint.operation.duration", unit="s")
        if mode == "azure-monitor":
            self.provider.add_span_processor(BatchSpanProcessor(SafeExporter(exporter)))
            _emit("telemetry.export", outcome="configured")
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
                try:
                    labels = {"operation": name, "outcome": fields["outcome"]}
                    self._operations.add(1, labels)
                    self._duration.record(fields["duration_ms"] / 1000, labels)
                except Exception:
                    _emit("telemetry.metric", outcome="failure")

    def parent_from_headers(self, headers):
        # Only the W3C traceparent field is accepted: no baggage or tracestate.
        return _propagator.extract({"traceparent": headers.get("traceparent", "")})

    def shutdown(self):
        try:
            self.provider.shutdown()
        except Exception:
            _emit("telemetry.shutdown", outcome="failure")
        try:
            self.meter_provider.shutdown()
        except Exception:
            _emit("telemetry.metric_shutdown", outcome="failure")
