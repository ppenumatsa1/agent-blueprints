"""Verify privacy-safe App Insights correlation for exact hosted evidence pairs."""

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID


def _azure_cli():
    executable = shutil.which("az")
    if executable is None:
        raise RuntimeError("Azure CLI is unavailable.")
    return executable


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("tables"), list):
        tables = payload["tables"]
        if len(tables) != 1:
            return []
        table = tables[0]
        columns = [column["name"] for column in table.get("columns", [])]
        return [dict(zip(columns, row, strict=True)) for row in table.get("rows", [])]
    return []


def _expected_pairs(evidence):
    pairs = []
    seen = set()
    for item in evidence.get("correlations", []):
        request_id = str(UUID(item["request_id"]))
        case_id = str(UUID(item["case_id"]))
        trace_id = item["trace_id"]
        if len(trace_id) != 32:
            raise ValueError("Trace IDs must contain 32 hexadecimal characters.")
        int(trace_id, 16)
        key = (request_id, case_id, trace_id)
        if key in seen:
            raise ValueError("Correlation evidence contains duplicate pairs.")
        seen.add(key)
        pairs.append(
            {
                "request_id": request_id,
                "case_id": case_id,
                "trace_id": trace_id,
                "agent_version": item["agent_version"],
                "deployment_revision": item["deployment_revision"],
            }
        )
    if not pairs:
        raise ValueError("Correlation evidence is empty.")
    return pairs


def _quoted(value):
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f"'{escaped}'"


def _query(expected, started_at):
    fields = (
        "request_id",
        "case_id",
        "trace_id",
        "agent_version",
        "deployment_revision",
    )
    datatable = ",".join(
        _quoted(item[field])
        for item in expected
        for field in fields
    )
    return (
        "let expected=datatable("
        "request_id:string,case_id:string,trace_id:string,"
        "agent_version:string,deployment_revision:string"
        f")[{datatable}]; "
        "union withsource=table_name "
        "AppRequests, AppDependencies, AppTraces, AppExceptions "
        f"| where TimeGenerated between (datetime({_quoted(started_at)}) .. now()) "
        "| extend request_id=tostring(Properties['blueprint.request.id']) "
        "| extend case_id=tostring(Properties['blueprint.case.id']) "
        "| extend trace_id=tolower(OperationId) "
        "| extend agent_version=tostring(Properties['blueprint.agent.version']) "
        "| extend deployment_revision="
        "tostring(Properties['blueprint.deployment.revision']) "
        "| join kind=inner expected on "
        "request_id, case_id, trace_id, agent_version, deployment_revision "
        "| summarize telemetry_count=count(), "
        "exception_count=countif(table_name == 'AppExceptions') by "
        "request_id, case_id, trace_id, agent_version, deployment_revision "
        "| order by request_id asc"
    )


def _query_workspace(workspace):
    if not workspace.casefold().startswith("/subscriptions/"):
        return workspace
    resolved = subprocess.run(
        [
            _azure_cli(),
            "monitor",
            "log-analytics",
            "workspace",
            "show",
            "--ids",
            workspace,
            "--query",
            "customerId",
            "--output",
            "tsv",
            "--only-show-errors",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    customer_id = resolved.stdout.strip()
    if resolved.returncode != 0 or not customer_id:
        raise RuntimeError("Unable to resolve the Log Analytics workspace query ID.")
    return customer_id


def verify(
    evidence_path,
    workspace,
    output,
    *,
    source_revision,
    deployment_revision,
    environment,
    attempts=1,
    wait_seconds=0,
):
    evidence = _read(evidence_path)
    if evidence.get("source_revision") != source_revision:
        raise ValueError("Hosted evidence source revision mismatch.")
    if evidence.get("deployment_revision") != deployment_revision:
        raise ValueError("Hosted evidence deployment revision mismatch.")
    if evidence.get("environment") != environment:
        raise ValueError("Hosted evidence environment mismatch.")
    expected = _expected_pairs(evidence)
    query = _query(expected, evidence["started_at"])
    query_workspace = _query_workspace(workspace)
    observed = []
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            [
                _azure_cli(),
                "monitor",
                "log-analytics",
                "query",
                "--workspace",
                query_workspace,
                "--analytics-query",
                query,
                "--output",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            observed = []
        else:
            try:
                observed = _rows(json.loads(completed.stdout))
            except json.JSONDecodeError:
                observed = []
        expected_keys = {
            (
                item["request_id"],
                item["case_id"],
                item["trace_id"],
                item["agent_version"],
                item["deployment_revision"],
            )
            for item in expected
        }
        observed_keys = {
            (
                item.get("request_id"),
                item.get("case_id"),
                item.get("trace_id"),
                item.get("agent_version"),
                item.get("deployment_revision"),
            )
            for item in observed
            if int(item.get("telemetry_count", 0)) > 0
            and int(item.get("exception_count", 0)) == 0
        }
        if observed_keys == expected_keys:
            break
        if attempt < attempts:
            time.sleep(wait_seconds)
    else:
        raise RuntimeError(
            "App Insights did not corroborate every exact correlation pair."
        )

    artifact = {
        "schema_version": "1.0.0",
        "source_revision": source_revision,
        "deployment_revision": deployment_revision,
        "environment": environment,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "check_id": "APP-INSIGHTS-CORRELATION",
        "outcome": "passed",
        "attempts": attempt,
        "validated_pairs": observed,
    }
    Path(output).write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--deployment-revision", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 30:
        parser.error("--attempts must be between 1 and 30")
    if args.wait_seconds < 0 or args.wait_seconds > 300:
        parser.error("--wait-seconds must be between 0 and 300")
    try:
        verify(
            args.evidence,
            args.workspace,
            args.output,
            source_revision=args.source_revision,
            deployment_revision=args.deployment_revision,
            environment=args.environment,
            attempts=args.attempts,
            wait_seconds=args.wait_seconds,
        )
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as error:
        print(
            f"App Insights correlation failed: {type(error).__name__}.", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
