"""Allowlisted operational telemetry; never inspect application payloads."""

import hashlib
import inspect
import json
import logging
import os
import re
import threading
import time
import weakref
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import wraps
from uuid import UUID

from agent_framework.observability import enable_instrumentation
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics import (
    AlwaysOffExemplarFilter,
    Counter,
    Histogram,
    MeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    MetricExporter,
    MetricExportResult,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExportResult, SpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


_log = logging.getLogger("blueprint.telemetry")
if not _log.handlers:
    _log.addHandler(logging.StreamHandler())
_log.setLevel(logging.INFO)
_log.propagate = False
_propagator = TraceContextTextMapPropagator()
_provider_lock = threading.Lock()
_azure_trace_destinations = weakref.WeakKeyDictionary()
_SCHEMA_VERSION = "1.0.0"
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_OPERATIONS = frozenset(
    {
        "http.request",
        "foundry.invoke",
        "workflow.start",
        "workflow.resume",
        "model.invoke",
        "tool.execute",
        "database.connect",
        "database.read",
        "database.create",
        "database.decision",
        "database.finish",
        "identity.obo",
    }
)
_TECHNICAL_STATUSES = frozenset({"succeeded", "failed", "interrupted", "retrying", "unknown"})
_BUSINESS_OUTCOMES = frozenset(
    {"created", "pending", "approved", "rejected", "completed", "failed", "unknown"}
)
_RETRY_REASONS = frozenset({"transient", "timeout", "conflict", "interrupted", "unknown_outcome"})
_SPAN_ATTRIBUTES = frozenset(
    {
        "http.response.status_code",
        "blueprint.request.id",
        "blueprint.case.id",
        "blueprint.agent.version",
        "blueprint.deployment.revision",
        "blueprint.technical.status",
        "blueprint.business.outcome",
        "blueprint.model.provider",
        "blueprint.model.name",
        "blueprint.tool.name",
        "blueprint.retry.count",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.cached_tokens",
    }
)


@dataclass(frozen=True)
class CorrelationContext:
    request_id: str | None = None
    case_id: str | None = None


_correlation = ContextVar("blueprint_correlation", default=CorrelationContext())


def _safe_identifier(value):
    return value if isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value) else None


def _uuid_text(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _case_id_from(values):
    for value in values:
        if isinstance(value, UUID):
            return str(value)
        candidate = getattr(value, "id", None)
        if isinstance(candidate, UUID):
            return str(candidate)
    return None


def _emit(event: str, **fields) -> None:
    try:
        _log.info(
            json.dumps(
                {"schema_version": _SCHEMA_VERSION, "event": event, **fields},
                separators=(",", ":"),
            )
        )
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
                self.telemetry.bind_case(_case_id_from((*args, *kwargs.values())))
                with self.telemetry.operation(name) as operation:
                    result = await func(self, *args, **kwargs)
                    result_case_id = _case_id_from((result,))
                    self.telemetry.bind_case(result_case_id)
                    if result_case_id is not None:
                        operation.set_attribute("blueprint.case.id", result_case_id)
                    operation.capture_result(result)
                    return result

            return async_wrapper

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if self.telemetry is None:
                return func(self, *args, **kwargs)
            self.telemetry.bind_case(_case_id_from((*args, *kwargs.values())))
            with self.telemetry.operation(name) as operation:
                result = func(self, *args, **kwargs)
                result_case_id = _case_id_from((result,))
                self.telemetry.bind_case(result_case_id)
                if result_case_id is not None:
                    operation.set_attribute("blueprint.case.id", result_case_id)
                operation.capture_result(result)
                return result

        return wrapper

    return decorate


class SafeExporter(SpanExporter):
    """Drop unredacted FastAPI spans and keep exporter diagnostics payload-free."""

    def __init__(self, exporter):
        self._exporter = exporter

    def export(self, spans):
        spans = tuple(spans)
        exportable = tuple(span for span in spans if span.instrumentation_scope.name != "fastapi")
        if spans and not exportable:
            return SpanExportResult.SUCCESS
        try:
            result = self._exporter.export(exportable)
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
    def __init__(self, telemetry, span):
        self.telemetry = telemetry
        self.span = span
        self.status = StatusCode.UNSET
        self.http_status = None
        self.technical_status = None
        self.business_outcome = None
        self.retry_count = 0

    def set_attribute(self, name, value):
        valid = False
        if name == "http.response.status_code":
            valid = isinstance(value, int)
        elif name in {
            "blueprint.request.id",
            "blueprint.case.id",
        }:
            value = _uuid_text(value)
            valid = value is not None
        elif name in {
            "blueprint.agent.version",
            "blueprint.deployment.revision",
            "blueprint.model.provider",
            "blueprint.model.name",
            "blueprint.tool.name",
        }:
            value = _safe_identifier(value)
            valid = value is not None
        elif name in {
            "blueprint.retry.count",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
            "gen_ai.usage.cached_tokens",
        }:
            valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        elif name == "blueprint.technical.status":
            valid = value in _TECHNICAL_STATUSES
        elif name == "blueprint.business.outcome":
            valid = value in _BUSINESS_OUTCOMES
        if name not in _SPAN_ATTRIBUTES or not valid:
            return
        if name == "http.response.status_code":
            self.http_status = value
        if self.span is not None:
            try:
                self.span.set_attribute(name, value)
            except Exception:
                _instrumentation_failure()

    def traceparent(self):
        if self.span is None:
            return None
        try:
            context = self.span.get_span_context()
            if not context.is_valid:
                return None
            flags = int(context.trace_flags)
            return f"00-{context.trace_id:032x}-{context.span_id:016x}-{flags:02x}"
        except Exception:
            _instrumentation_failure()
            return None

    def set_status(self, status):
        try:
            self.status = status.status_code
            if self.span is not None:
                self.span.set_status(status)
        except Exception:
            _instrumentation_failure()

    def set_technical_status(self, status):
        if status in _TECHNICAL_STATUSES:
            self.technical_status = status
            self.set_attribute("blueprint.technical.status", status)

    def set_business_outcome(self, outcome):
        if outcome in _BUSINESS_OUTCOMES:
            self.business_outcome = outcome
            self.set_attribute("blueprint.business.outcome", outcome)
            self.telemetry._record_outcome("business", outcome)

    def capture_result(self, result):
        status = getattr(result, "status", None)
        decision = getattr(result, "decision", None)
        if status in _BUSINESS_OUTCOMES:
            self.set_business_outcome(status)
        elif decision in _BUSINESS_OUTCOMES:
            self.set_business_outcome(decision)

    def record_retry(self, reason):
        if reason not in _RETRY_REASONS:
            raise ValueError("Retry reasons must use the privacy-safe allowlist.")
        self.retry_count += 1
        self.set_technical_status("retrying")
        self.set_attribute("blueprint.retry.count", self.retry_count)
        self.telemetry._record_retry(reason)
        _emit(
            "retry",
            **self.telemetry.correlation_fields(self.span),
            reason=reason,
            retry_count=self.retry_count,
        )

    def record_model_usage(
        self,
        *,
        provider,
        model,
        input_tokens,
        output_tokens,
        cached_tokens=0,
    ):
        provider = _safe_identifier(provider)
        model = _safe_identifier(model)
        counts = (input_tokens, output_tokens, cached_tokens)
        if (
            provider is None
            or model is None
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in counts
            )
        ):
            raise ValueError("Model usage must contain allowlisted identifiers and token counts.")
        self.set_attribute("blueprint.model.provider", provider)
        self.set_attribute("blueprint.model.name", model)
        for attribute, value in (
            ("gen_ai.usage.input_tokens", input_tokens),
            ("gen_ai.usage.output_tokens", output_tokens),
            ("gen_ai.usage.cached_tokens", cached_tokens),
        ):
            self.set_attribute(attribute, value)
        self.telemetry._record_model_usage(
            provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )
        _emit(
            "model.usage",
            **self.telemetry.correlation_fields(self.span),
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )


class Telemetry:
    def __init__(
        self,
        mode="local",
        connection_string=None,
        *,
        exporter=None,
        metric_exporter=None,
        metric_reader=None,
        agent_version="0.1.0",
        deployment_revision="local-unversioned",
    ):
        if mode not in ("local", "azure-monitor"):
            raise ValueError("TELEMETRY_MODE must be local or azure-monitor.")
        if mode == "azure-monitor" and (
            not isinstance(connection_string, str) or not connection_string.strip()
        ):
            raise ValueError("APPLICATIONINSIGHTS_CONNECTION_STRING is required for azure-monitor.")
        if mode == "azure-monitor" and metric_reader is not None:
            raise ValueError("A custom metric reader cannot replace Azure Monitor export.")
        if _safe_identifier(agent_version) is None:
            raise ValueError("AGENT_VERSION must be a privacy-safe identifier.")
        if _safe_identifier(deployment_revision) is None:
            raise ValueError("DEPLOYMENT_REVISION must be a privacy-safe identifier.")

        resource = Resource(
            {
                "service.name": "maf-workflow",
                "service.version": agent_version,
                "service.namespace": "agent-blueprints",
                "service.instance.id": "not-collected",
                "device.id": "not-collected",
                "deployment.environment.revision": deployment_revision,
            }
        )
        readers = [metric_reader] if metric_reader is not None else []
        provider = meter_provider = azure_reader = processor = None
        owns_provider = False
        trace_destination = None
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

                if metric_exporter is None:
                    metric_exporter = AzureMonitorMetricExporter(
                        connection_string=connection_string, disable_offline_storage=True
                    )
            current_provider = trace.get_tracer_provider()
            if isinstance(current_provider, TracerProvider):
                provider = current_provider
            else:
                provider = TracerProvider(resource=resource)
                trace.set_tracer_provider(provider)
                owns_provider = True
            enable_instrumentation(
                enable_sensitive_data=False,
                enable_message_events=False,
                force=True,
            )
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
            model_tokens = meter.create_counter("blueprint.model.tokens", unit="{token}")
            retries = meter.create_counter("blueprint.retries", unit="{retry}")
            outcomes = meter.create_counter("blueprint.outcomes", unit="{outcome}")
            if mode == "azure-monitor":
                if exporter is None:
                    trace_destination = hashlib.sha256(
                        connection_string.encode("utf-8")
                    ).hexdigest()
                    with _provider_lock:
                        destinations = _azure_trace_destinations.setdefault(provider, set())
                        if trace_destination not in destinations:
                            exporter = AzureMonitorTraceExporter(
                                connection_string=connection_string,
                                disable_offline_storage=True,
                            )
                            processor = BatchSpanProcessor(SafeExporter(exporter))
                            provider.add_span_processor(processor)
                            destinations.add(trace_destination)
                            processor_attached = True
                else:
                    processor = BatchSpanProcessor(SafeExporter(exporter))
                    provider.add_span_processor(processor)
                    processor_attached = True
        except Exception:
            if provider is not None and owns_provider:
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
        self.agent_version = agent_version
        self.deployment_revision = deployment_revision
        self._operations = operations
        self._duration = duration
        self._model_tokens = model_tokens
        self._retries = retries
        self._outcomes = outcomes
        if mode == "azure-monitor":
            _emit("telemetry.export", outcome="configured")
        else:
            _emit("telemetry.export", outcome="disabled")

    @contextmanager
    def request_scope(self, request_id):
        request_id = _uuid_text(request_id)
        if request_id is None:
            raise ValueError("Request IDs must be UUIDs.")
        token = _correlation.set(CorrelationContext(request_id=request_id))
        try:
            yield
        finally:
            _correlation.reset(token)

    def bind_case(self, case_id):
        case_id = _uuid_text(case_id)
        if case_id is not None:
            _correlation.set(replace(_correlation.get(), case_id=case_id))

    def correlation_fields(self, span=None):
        context = _correlation.get()
        fields = {
            "agent_version": self.agent_version,
            "deployment_revision": self.deployment_revision,
        }
        if context.request_id is not None:
            fields["request_id"] = context.request_id
            fields["correlation_id"] = context.request_id
        if context.case_id is not None:
            fields["case_id"] = context.case_id
        if span is not None:
            try:
                span_context = span.get_span_context()
                fields["trace_id"] = f"{span_context.trace_id:032x}"
                fields["span_id"] = f"{span_context.span_id:016x}"
            except Exception:
                _instrumentation_failure()
        return fields

    def _record_model_usage(self, provider, *, input_tokens, output_tokens, cached_tokens):
        try:
            for token_type, value in (
                ("input", input_tokens),
                ("output", output_tokens),
                ("cached", cached_tokens),
            ):
                if value:
                    self._model_tokens.add(
                        value,
                        {"provider": provider, "token_type": token_type},
                    )
        except Exception:
            _emit("telemetry.metric", outcome="failure")

    def _record_retry(self, reason):
        try:
            self._retries.add(1, {"reason": reason})
        except Exception:
            _emit("telemetry.metric", outcome="failure")

    def _record_outcome(self, kind, status):
        try:
            self._outcomes.add(1, {"kind": kind, "status": status})
        except Exception:
            _emit("telemetry.metric", outcome="failure")

    @contextmanager
    def operation(
        self,
        name,
        *,
        kind=SpanKind.INTERNAL,
        parent=None,
        correlation_id=None,
        model_provider=None,
        model=None,
        tool=None,
    ):
        if name not in _OPERATIONS:
            name = "other"
        if correlation_id is not None and _correlation.get().request_id is None:
            request_id = _uuid_text(correlation_id)
            if request_id is not None:
                _correlation.set(replace(_correlation.get(), request_id=request_id))
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
        operation = _Operation(self, span)
        context = _correlation.get()
        for attribute, value in (
            ("blueprint.request.id", context.request_id),
            ("blueprint.case.id", context.case_id),
            ("blueprint.agent.version", self.agent_version),
            ("blueprint.deployment.revision", self.deployment_revision),
            ("blueprint.model.provider", model_provider),
            ("blueprint.model.name", model),
            ("blueprint.tool.name", tool),
        ):
            if value is not None:
                operation.set_attribute(attribute, value)
        outcome = "success"
        try:
            yield operation
        except BaseException:
            outcome = "error"
            operation.set_technical_status("failed")
            try:
                operation.set_status(Status(StatusCode.ERROR))
            except Exception:
                _instrumentation_failure()
            raise
        finally:
            try:
                if operation.status == StatusCode.ERROR:
                    outcome = "error"
                if operation.technical_status is None:
                    operation.set_technical_status("failed" if outcome == "error" else "succeeded")
                fields = dict(
                    operation=name,
                    outcome=outcome,
                    technical_status=operation.technical_status,
                    duration_ms=round((time.monotonic() - start) * 1000, 3)
                    if start is not None
                    else 0,
                )
                fields.update(self.correlation_fields(span))
                status_code = operation.http_status
                if isinstance(status_code, int):
                    fields["http_status_code"] = status_code
                    if 400 <= status_code < 500:
                        fields["outcome"] = "client_error"
                if operation.business_outcome is not None:
                    fields["business_outcome"] = operation.business_outcome
                if operation.retry_count:
                    fields["retry_count"] = operation.retry_count
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
            self.provider.force_flush()
        except Exception:
            _emit("telemetry.shutdown", outcome="failure")
        try:
            self.meter_provider.shutdown()
        except Exception:
            _emit("telemetry.metric_shutdown", outcome="failure")
