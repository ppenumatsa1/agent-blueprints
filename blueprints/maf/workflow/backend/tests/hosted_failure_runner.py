"""Run explicitly configured hosted failure scenarios without hidden retries."""

import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4


class TransientFailure(RuntimeError):
    pass


class UnknownOutcome(RuntimeError):
    pass


class AuthorizationFailure(RuntimeError):
    pass


class StaleApproval(RuntimeError):
    pass


class ConflictFailure(RuntimeError):
    pass


class ReconciliationRequired(RuntimeError):
    pass


class UnsupportedScenario(RuntimeError):
    pass


@dataclass(frozen=True)
class HostedRecord:
    case_id: str
    request_id: str
    idempotency_key: str
    status: str
    technical_status: str
    business_outcome: str
    effect_count: int

    def __post_init__(self):
        UUID(self.case_id)
        UUID(self.request_id)
        if not self.idempotency_key:
            raise ValueError("Hosted records require request and idempotency identifiers.")
        if self.technical_status not in {
            "succeeded",
            "failed",
            "interrupted",
            "retrying",
            "unknown",
        }:
            raise ValueError("Hosted records require an explicit technical status.")
        if self.business_outcome not in {
            "created",
            "pending",
            "approved",
            "rejected",
            "completed",
            "failed",
            "unknown",
        }:
            raise ValueError("Hosted records require a distinct business outcome.")
        if (
            isinstance(self.effect_count, bool)
            or not isinstance(self.effect_count, int)
            or self.effect_count < 0
        ):
            raise ValueError("Effect counts must be non-negative integers.")


class HostedFailureAdapter(Protocol):
    source_revision: str
    deployment_revision: str

    def create(self, idempotency_key: str, *, lose_ack: bool = False) -> HostedRecord: ...

    def lookup(self, idempotency_key: str) -> HostedRecord: ...

    def read(self, case_id: str) -> HostedRecord: ...

    def approve(
        self,
        case_id: str,
        *,
        actor: str = "authorized",
        request_id: str | None = None,
    ) -> HostedRecord: ...

    def restart_api(self) -> None: ...

    def interrupt_host(self, case_id: str) -> None: ...

    def set_postgres_transient(self, enabled: bool) -> None: ...

    def set_tool_timeout_after_effect(self, enabled: bool) -> None: ...

    def retry(self, case_id: str) -> HostedRecord: ...

    def reconcile(self, case_id: str) -> HostedRecord: ...

    def correlations(self) -> list[dict[str, str | int]]: ...


def _key(name):
    return f"failure-{name}-{uuid4()}"


def _same_record(before, after):
    return (
        before.case_id == after.case_id
        and before.request_id == after.request_id
        and before.idempotency_key == after.idempotency_key
    )


def _api_restart(adapter):
    created = adapter.create(_key("api-restart"))
    adapter.restart_api()
    observed = adapter.read(created.case_id)
    if not _same_record(created, observed):
        raise AssertionError("API restart changed persisted workflow identity.")
    return observed


def _hosted_interruption(adapter):
    created = adapter.create(_key("hosted-interruption"))
    adapter.interrupt_host(created.case_id)
    interrupted = adapter.read(created.case_id)
    if interrupted.technical_status not in {"interrupted", "unknown"}:
        raise AssertionError("Hosted interruption was not visible.")
    recovered = adapter.reconcile(created.case_id)
    if not _same_record(created, recovered) or recovered.effect_count != 0:
        raise AssertionError("Hosted resume did not preserve the pending request.")
    return recovered


def _postgres_transient(adapter):
    created = adapter.create(_key("postgres-transient"))
    adapter.set_postgres_transient(True)
    try:
        adapter.read(created.case_id)
    except TransientFailure:
        pass
    else:
        raise AssertionError("PostgreSQL transient failure was not observed.")
    finally:
        adapter.set_postgres_transient(False)
    if not _same_record(created, adapter.read(created.case_id)):
        raise AssertionError("PostgreSQL recovery changed persisted workflow identity.")
    return created


def _tool_timeout_after_effect(adapter):
    created = adapter.create(_key("tool-timeout"))
    adapter.set_tool_timeout_after_effect(True)
    try:
        adapter.approve(created.case_id, request_id=created.request_id)
    except UnknownOutcome:
        pass
    else:
        raise AssertionError("Tool timeout after effect did not remain unknown.")
    finally:
        adapter.set_tool_timeout_after_effect(False)
    unknown = adapter.read(created.case_id)
    if unknown.effect_count != 1 or unknown.technical_status != "unknown":
        raise AssertionError("Unknown tool outcome was replayed or hidden.")
    reconciled = adapter.reconcile(created.case_id)
    if reconciled.effect_count != 1 or reconciled.business_outcome != "completed":
        raise AssertionError("Tool reconciliation did not preserve exactly one effect.")
    return reconciled


def _duplicate_approval(adapter):
    created = adapter.create(_key("duplicate-approval"))
    completed = adapter.approve(created.case_id, request_id=created.request_id)
    if (
        completed.technical_status != "succeeded"
        or completed.business_outcome != "completed"
        or completed.effect_count != 1
    ):
        raise AssertionError("The first approval did not complete exactly one effect.")
    try:
        duplicate = adapter.approve(created.case_id, request_id=created.request_id)
    except ConflictFailure:
        duplicate = adapter.read(created.case_id)
    if (
        duplicate.effect_count != completed.effect_count
        or duplicate.business_outcome != completed.business_outcome
    ):
        raise AssertionError("Duplicate approval changed the durable outcome.")
    return duplicate


def _stale_approval(adapter):
    created = adapter.create(_key("stale-approval"))
    try:
        adapter.approve(
            created.case_id,
            request_id=f"{created.request_id}-stale",
        )
    except StaleApproval:
        pass
    else:
        raise AssertionError("Stale approval was accepted.")
    observed = adapter.read(created.case_id)
    if observed.business_outcome != "pending" or observed.effect_count != 0:
        raise AssertionError("Stale approval changed the pending business state.")
    return observed


def _unauthorized_approval(adapter):
    created = adapter.create(_key("unauthorized-approval"))
    try:
        adapter.approve(
            created.case_id,
            actor="unauthorized",
            request_id=created.request_id,
        )
    except AuthorizationFailure:
        pass
    else:
        raise AssertionError("Unauthorized approval was accepted.")
    observed = adapter.read(created.case_id)
    if observed.business_outcome != "pending" or observed.effect_count != 0:
        raise AssertionError("Unauthorized approval changed the business state.")
    return observed


def _lost_response_acknowledgement(adapter):
    key = _key("lost-ack")
    try:
        adapter.create(key, lose_ack=True)
    except UnknownOutcome:
        pass
    else:
        raise AssertionError("Lost create acknowledgement did not remain unknown.")
    reconciled = adapter.lookup(key)
    replay = adapter.create(key)
    if not _same_record(reconciled, replay) or replay.effect_count != 0:
        raise AssertionError("Lost acknowledgement caused a duplicate create.")
    return replay


def _unknown_outcome_reconciliation(adapter):
    created = adapter.create(_key("unknown-retry"))
    adapter.set_tool_timeout_after_effect(True)
    try:
        adapter.approve(created.case_id, request_id=created.request_id)
    except UnknownOutcome:
        pass
    else:
        raise AssertionError("Unknown outcome injection did not produce an unknown result.")
    finally:
        adapter.set_tool_timeout_after_effect(False)
    try:
        adapter.retry(created.case_id)
    except ReconciliationRequired:
        pass
    else:
        raise AssertionError("Unknown outcome was retried before reconciliation.")
    reconciled = adapter.reconcile(created.case_id)
    if reconciled.effect_count != 1 or reconciled.business_outcome != "completed":
        raise AssertionError("Unknown outcome reconciliation was not exactly-once.")
    return reconciled


SCENARIOS = (
    ("api_restart", _api_restart),
    ("hosted_interruption", _hosted_interruption),
    ("postgres_transient_failure", _postgres_transient),
    ("tool_timeout_after_effect", _tool_timeout_after_effect),
    ("duplicate_approval", _duplicate_approval),
    ("stale_approval", _stale_approval),
    ("unauthorized_approval", _unauthorized_approval),
    ("lost_response_acknowledgement", _lost_response_acknowledgement),
    ("unknown_outcome_retry_reconciliation", _unknown_outcome_reconciliation),
)


def run_scenarios(adapter, *, source_revision, deployment_revision, environment):
    if adapter.source_revision != source_revision:
        raise ValueError("Hosted adapter source revision does not match the requested revision.")
    if adapter.deployment_revision != deployment_revision:
        raise ValueError("Hosted adapter deployment revision is not the active requested revision.")
    started_at = datetime.now(timezone.utc).isoformat()
    results = {}
    expected_correlations = set()
    for name, scenario in SCENARIOS:
        try:
            record = scenario(adapter)
        except UnsupportedScenario:
            results[name] = {
                "status": "blocked",
                "reason": "The hosted adapter does not implement this bounded fault.",
            }
        except Exception as error:  # noqa: BLE001 - evidence retains type, never payload text.
            results[name] = {
                "status": "failed",
                "reason": f"Scenario failed with {type(error).__name__}.",
            }
        else:
            if not isinstance(record, HostedRecord):
                raise ValueError("Hosted scenarios must return their correlated record.")
            expected_correlations.add((record.request_id, record.case_id))
            results[name] = {
                "status": "passed",
                "reason": "The hosted failure contract was observed.",
            }
    correlations = adapter.correlations()
    if not correlations:
        raise ValueError("Hosted failure evidence requires correlation records.")
    for item in correlations:
        required = {
            "request_id",
            "case_id",
            "trace_id",
            "agent_version",
            "deployment_revision",
        }
        hosted = {"hosted_phase", "conversation_id", "hosted_agent_name", "hosted_agent_version"}
        optional = {"http_status"} | hosted
        if not required <= set(item) or set(item) - required - optional:
            raise ValueError("Hosted correlation records have an unexpected shape.")
        if "http_status" in item and (
            type(item["http_status"]) is not int or not 100 <= item["http_status"] <= 599
        ):
            raise ValueError("Hosted correlation HTTP status is invalid.")
        if set(item) & hosted:
            if not hosted <= set(item) or item["hosted_phase"] not in {"start", "resume"}:
                raise ValueError("Hosted correlation phase is invalid.")
            if any(
                not isinstance(item[name], str) or not item[name].strip() or len(item[name]) > 512
                for name in hosted - {"hosted_phase"}
            ):
                raise ValueError("Hosted correlation metadata is invalid.")
        UUID(item["request_id"])
        UUID(item["case_id"])
        int(item["trace_id"], 16)
        if len(item["trace_id"]) != 32:
            raise ValueError("Hosted trace IDs must contain 32 hexadecimal characters.")
        if item["deployment_revision"] != deployment_revision:
            raise ValueError("Hosted correlation deployment revision mismatch.")
    observed_correlations = {(item["request_id"], item["case_id"]) for item in correlations}
    if not expected_correlations.issubset(observed_correlations):
        raise ValueError("Hosted correlation evidence does not cover every passed scenario.")
    return {
        "schema_version": "1.0.0",
        "source_revision": source_revision,
        "deployment_revision": deployment_revision,
        "environment": environment,
        "started_at": started_at,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": results,
        "correlations": correlations,
    }


def _load_adapter(specification, base_url):
    module_name, separator, attribute = specification.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("MAF_HOSTED_FAILURE_ADAPTER must use module:callable syntax.")
    factory = getattr(importlib.import_module(module_name), attribute)
    return factory(base_url=base_url)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("MAF_HOSTED_FAILURE_ENABLED", "").lower() != "true":
        print(
            "Hosted failure injection requires MAF_HOSTED_FAILURE_ENABLED=true.",
            file=sys.stderr,
        )
        return 2
    required = {
        name: os.environ.get(name, "")
        for name in (
            "MAF_HOSTED_FAILURE_ADAPTER",
            "MAF_HOSTED_BASE_URL",
            "SOURCE_REVISION",
            "DEPLOYMENT_REVISION",
            "EVIDENCE_ENVIRONMENT",
        )
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        print(
            "Hosted failure injection is missing: " + ", ".join(sorted(missing)),
            file=sys.stderr,
        )
        return 2
    try:
        evidence = run_scenarios(
            _load_adapter(
                required["MAF_HOSTED_FAILURE_ADAPTER"],
                required["MAF_HOSTED_BASE_URL"],
            ),
            source_revision=required["SOURCE_REVISION"],
            deployment_revision=required["DEPLOYMENT_REVISION"],
            environment=required["EVIDENCE_ENVIRONMENT"],
        )
        args.output.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, ImportError, AttributeError) as error:
        print(f"Hosted failure injection could not start: {type(error).__name__}.", file=sys.stderr)
        return 2
    return 0 if all(item["status"] == "passed" for item in evidence["scenarios"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
