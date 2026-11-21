"""Allowlisted operational telemetry; never inspect application payloads."""

import json
import logging
import os
import time
import inspect
import threading
from contextlib import contextmanager
from functools import wraps
from uuid import UUID

from agent_framework.observability import enable_instrumentation
from opentelemetry import metrics as otel_metrics
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.metrics import (
    Counter,
    Histogram,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import AlwaysOffExemplarFilter, MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
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
_global_provider_lock = threading.Lock()
_global_providers_registered = False
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
        try:
            os.write(2, b'{"event":"telemetry.log","outcome":"failure"}\n')
        except OSError:
            pass


def _instrumentation_failure():
    _emit("telemetry.instrumentation", outcome="failure")


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
        # Match Azure Monitor's documented delta sums without reading exporter internals.
        super().__init__(
            preferred_temporality={
                Counter: AggregationTemporality.DELTA,
                Histogram: AggregationTemporality.DELTA,
                ObservableCounter: AggregationTemporality.DELTA,
                ObservableGauge: AggregationTemporality.CUMULATIVE,
                ObservableUpDownCounter: AggregationTemporality.CUMULATIVE,
                UpDownCounter: AggregationTemporality.CUMULATIVE,
            }
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
            if self.span is not None:
                try:
                    self.span.set_attribute(name, value)
                except Exception:
                    _instrumentation_failure()

    def set_status(self, status):
        try:
            self.status = status.status_code
            if self.span is not None:
                self.span.set_status(status)
        except Exception:
            _instrumentation_failure()


class Telemetry:
    def __init__(
        self,
        mode="local",
        connection_string=None,
        *,
        exporter=None,
        metric_exporter=None,
        metric_reader=None,
        enable_native_instrumentation=False,
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
        provider = meter_provider = azure_reader = processor = None
        processor_attached = reader_attached = False
        try:
            if mode == "azure-monitor":
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
            provider = TracerProvider(resource=resource)
            tracer = provider.get_tracer("blueprint.manual")
            if mode == "azure-monitor":
                azure_reader = PeriodicExportingMetricReader(SafeMetricExporter(metric_exporter))
                readers.append(azure_reader)
            meter_provider = MeterProvider(
                resource=resource, metric_readers=readers, exemplar_filter=AlwaysOffExemplarFilter()
            )
            reader_attached = True
            meter = meter_provider.get_meter("blueprint.manual")
            operations = meter.create_counter("blueprint.operations", unit="{operation}")
            duration = meter.create_histogram("blueprint.operation.duration", unit="s")
            if mode == "azure-monitor":
                processor = BatchSpanProcessor(SafeExporter(exporter))
                provider.add_span_processor(processor)
                processor_attached = True
            if enable_native_instrumentation:
                global _global_providers_registered
                with _global_provider_lock:
                    if not _global_providers_registered:
                        # Agent Framework instrumentation uses the process-wide OTel providers.
                        otel_trace.set_tracer_provider(provider)
                        otel_metrics.set_meter_provider(meter_provider)
                        if (
                            otel_trace.get_tracer_provider() is not provider
                            or otel_metrics.get_meter_provider() is not meter_provider
                        ):
                            raise RuntimeError("OpenTelemetry providers were already configured.")
                        _global_providers_registered = True
                enable_instrumentation(
                    enable_sensitive_data=False, enable_message_events=False
                )
        except Exception:
            if provider is not None:
                try:
                    provider.shutdown()
                except Exception:
                    pass
            if processor is not None and not processor_attached:
                try:
                    processor.shutdown()
                except Exception:
                    pass
            elif exporter is not None and processor is None and mode == "azure-monitor":
                try:
                    exporter.shutdown()
                except Exception:
                    pass
            if meter_provider is not None:
                try:
                    meter_provider.shutdown()
                except Exception:
                    pass
            if azure_reader is not None and not reader_attached:
                try:
                    azure_reader.shutdown()
                except Exception:
                    pass
            elif metric_reader is not None and not reader_attached and mode == "local":
                try:
                    metric_reader.shutdown()
                except Exception:
                    pass
            elif metric_exporter is not None and azure_reader is None and mode == "azure-monitor":
                try:
                    metric_exporter.shutdown()
                except Exception:
                    pass
            if mode == "azure-monitor":
                raise RuntimeError("Azure Monitor telemetry initialization failed.") from None
            raise RuntimeError("Telemetry initialization failed.") from None
        self.provider = provider
        self.tracer = tracer
        self.meter_provider = meter_provider
        self._operations = operations
        self._duration = duration
        if mode == "azure-monitor":
            _emit("telemetry.export", outcome="configured")
        else:
            _emit("telemetry.export", outcome="disabled")

    @contextmanager
    def operation(self, name, *, kind=SpanKind.INTERNAL, parent=None, correlation_id=None):
        if name not in _OPERATIONS:
            name = "other"
        try:
            start = time.monotonic()
        except Exception:
            start = None
            _instrumentation_failure()
        span_context = span = None
        try:
            span_context = self.tracer.start_as_current_span(
                name,
                context=parent,
                kind=kind,
                record_exception=False,
                set_status_on_exception=False,
            )
            span = span_context.__enter__()
        except Exception:
            span_context = None
            _instrumentation_failure()
        operation = _Operation(span)
        outcome = "success"
        try:
            yield operation
        except BaseException:
            outcome = "error"
            try:
                operation.set_status(Status(StatusCode.ERROR))
            except Exception:
                _instrumentation_failure()
            raise
        finally:
            try:
                if operation.status == StatusCode.ERROR:
                    outcome = "error"
                fields = dict(
                    operation=name,
                    outcome=outcome,
                    duration_ms=round((time.monotonic() - start) * 1000, 3)
                    if start is not None
                    else 0,
                )
                if span is not None:
                    try:
                        ctx = span.get_span_context()
                        fields["trace_id"] = f"{ctx.trace_id:032x}"
                        fields["span_id"] = f"{ctx.span_id:016x}"
                    except Exception:
                        _instrumentation_failure()
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
            except Exception:
                _instrumentation_failure()
            finally:
                if span_context is not None:
                    try:
                        span_context.__exit__(None, None, None)
                    except Exception:
                        _instrumentation_failure()

    def parent_from_headers(self, headers):
        # Only the W3C traceparent field is accepted: no baggage or tracestate.
        try:
            return _propagator.extract({"traceparent": headers.get("traceparent", "")})
        except Exception:
            _instrumentation_failure()
            return None

    def shutdown(self):
        try:
            self.provider.shutdown()
        except Exception:
            _emit("telemetry.shutdown", outcome="failure")
        try:
            self.meter_provider.shutdown()
        except Exception:
            _emit("telemetry.metric_shutdown", outcome="failure")
