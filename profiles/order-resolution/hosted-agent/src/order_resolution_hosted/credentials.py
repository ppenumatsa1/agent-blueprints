from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode


_lock = threading.Lock()
_credential: Any | None = None
_AUDIENCES = frozenset({"foundry", "internal-api"})
_ERROR_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")


def application_credential() -> Any:
    """Return one process-wide credential so app-owned token caches are shared."""

    global _credential
    if _credential is None:
        with _lock:
            if _credential is None:
                from azure.identity import DefaultAzureCredential

                _credential = DefaultAzureCredential(
                    exclude_interactive_browser_credential=True,
                )
    return _credential


@contextmanager
def application_credential_prewarm(audience: str):
    if audience not in _AUDIENCES:
        raise ValueError("The credential audience is invalid.")
    tracer = trace.get_tracer("agent-blueprints.order-resolution.credentials")
    with tracer.start_as_current_span(
        "application.credentials.prewarm",
        kind=SpanKind.INTERNAL,
        attributes={
            "blueprint.credential.owner": "application",
            "blueprint.credential.audience": audience,
        },
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
