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
        pair = {
            "request_id": request_id,
            "case_id": case_id,
            "trace_id": trace_id,
            "agent_version": item["agent_version"],
            "deployment_revision": item["deployment_revision"],
        }
        hosted_phase = item.get("hosted_phase")
        if hosted_phase is not None:
            if hosted_phase not in {"start", "resume"}:
                raise ValueError("Hosted phases must be start or resume.")
            for name in (
                "conversation_id",
                "hosted_agent_name",
                "hosted_agent_version",
            ):
                value = item.get(name)
                if not isinstance(value, str) or not value.strip() or len(value) > 512:
                    raise ValueError(f"{name} is required for hosted trace evidence.")
                pair[name] = value
            pair["hosted_phase"] = hosted_phase
        pairs.append(pair)
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
    datatable = ",".join(_quoted(item[field]) for item in expected for field in fields)
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


def _trace_query(expected, started_at):
    trace_ids = sorted(
        {
            item["trace_id"]
            for item in expected
            if item.get("hosted_phase") in {"start", "resume"}
        }
    )
    if not trace_ids:
        return None
    values = ",".join(_quoted(item) for item in trace_ids)
    raw_fields = (
        "gen_ai.input.messages",
        "gen_ai.output.messages",
        "gen_ai.prompt",
        "gen_ai.completion",
        "gen_ai.tool.call.arguments",
        "gen_ai.tool.call.result",
        "input.value",
        "output.value",
        "tool.arguments",
        "tool.result",
    )
    raw_expression = " or ".join(
        f"strlen(tostring(Properties[{_quoted(name)}])) > 0" for name in raw_fields
    )
    return (
        f"let expected=dynamic([{values}]); "
        "union withsource=table_name "
        "AppRequests, AppDependencies, AppTraces, AppExceptions "
        f"| where TimeGenerated between (datetime({_quoted(started_at)}) .. now()) "
        "| extend trace_id=tolower(tostring(OperationId)) "
        "| where trace_id in (expected) "
        "| extend span_id=tolower(tostring(Id)), "
        "parent_id=tolower(tostring(ParentId)), "
        "span_name=tostring(Name), role_name=tostring(AppRoleName), "
        "operation_name=tostring(Properties['gen_ai.operation.name']), "
        "conversation_id=coalesce("
        "tostring(Properties['gen_ai.conversation.id']), "
        "tostring(Properties['azure.ai.agentserver.conversation_id']), "
        "tostring(Properties['azure.ai.agentserver.responses.conversation_id'])), "
        "agent_name=tostring(Properties['gen_ai.agent.name']), "
        "agent_version=tostring(Properties['gen_ai.agent.version']), "
        "foundry_marker=tostring(Properties['microsoft.foundry']), "
        "deployment_revision="
        "tostring(Properties['blueprint.deployment.revision']), "
        "anchor_type=tostring(Properties['blueprint.trace.anchor.type']), "
        "anchor_source=tostring(Properties['blueprint.trace.anchor.source']), "
        "remote_parent=tostring(Properties['blueprint.trace.parent.remote']), "
        "workflow_stage=tostring(Properties['blueprint.workflow.stage']), "
        "link_trace_id=tolower(tostring(Properties['blueprint.trace.link.trace_id'])), "
        "link_span_id=tolower(tostring(Properties['blueprint.trace.link.span_id'])), "
        f"raw_content=iff({raw_expression}, 1, 0) "
        "| project table_name, trace_id, span_id, parent_id, span_name, role_name, "
        "operation_name, conversation_id, agent_name, agent_version, foundry_marker, "
        "deployment_revision, anchor_type, anchor_source, remote_parent, "
        "workflow_stage, link_trace_id, link_span_id, raw_content "
        "| order by trace_id asc, span_id asc"
    )


def _foundry_trace_ids(path):
    value = _read(path)
    if (
        value.get("evidence_kind") != "foundry_trajectory_index"
        or value.get("outcome") != "passed"
    ):
        raise ValueError("Foundry trajectory evidence is not a passed index artifact.")
    traces = value.get("trace_ids")
    if not isinstance(traces, list) or not traces:
        raise ValueError("Foundry trajectory evidence must contain trace_ids.")
    result = set()
    for trace_id in traces:
        if not isinstance(trace_id, str) or len(trace_id) != 32:
            raise ValueError(
                "Foundry trace IDs must contain 32 hexadecimal characters."
            )
        int(trace_id, 16)
        result.add(trace_id.lower())
    return result, value


def _validate_trace_rows(expected, rows, foundry_trace_ids):
    hosted = [
        item for item in expected if item.get("hosted_phase") in {"start", "resume"}
    ]
    if not hosted:
        return []
    by_trace = {}
    for row in rows:
        by_trace.setdefault(str(row.get("trace_id", "")).lower(), []).append(row)
    validated = []
    starts = {
        (item["case_id"], item["conversation_id"]): item["trace_id"].lower()
        for item in hosted
        if item["hosted_phase"] == "start"
    }
    for item in hosted:
        trace_id = item["trace_id"].lower()
        trace_rows = by_trace.get(trace_id, [])
        if not trace_rows:
            raise RuntimeError("A required hosted trace is missing from App Insights.")
        if trace_id not in foundry_trace_ids:
            raise RuntimeError(
                "A required hosted trace is missing from Foundry trajectories."
            )
        if any(int(row.get("raw_content", 0)) != 0 for row in trace_rows):
            raise RuntimeError(
                "Raw prompt, message, tool, or result content was captured."
            )
        roots = [
            row
            for row in trace_rows
            if row.get("operation_name") == "invoke_agent"
            and row.get("conversation_id") == item["conversation_id"]
            and row.get("agent_name") == item["hosted_agent_name"]
            and row.get("agent_version") == item["hosted_agent_version"]
            and str(row.get("foundry_marker", "")).casefold() == "true"
        ]
        if not roots:
            raise RuntimeError("The trace has no enriched hosted invoke_agent root.")
        if len(roots) != 1:
            raise RuntimeError(
                "The trace has multiple enriched hosted invoke_agent roots."
            )
        hosted_root = roots[0]
        if hosted_root.get("deployment_revision") != item["deployment_revision"]:
            raise RuntimeError(
                "The hosted invoke_agent root has stale deployment metadata."
            )
        if (
            hosted_root.get("anchor_type") != "app-owned-invoke-agent"
            or hosted_root.get("anchor_source")
            != "azure.ai.agentserver.responses.create_span_hook"
            or str(hosted_root.get("remote_parent", "")).casefold() != "true"
        ):
            raise RuntimeError(
                "The app-owned hosted root lacks the required platform-gap marker."
            )
        root_kind = "app-owned-hook"
        names = {str(row.get("span_name", "")) for row in trace_rows}
        required_exact = {
            "workflow.build",
            f"order_resolution.workflow.{item['hosted_phase']}",
        }
        required_prefixes = (
            "invoke_workflow",
            "executor.process approval",
            "edge_group.process",
        )
        if not required_exact.issubset(names) or any(
            not any(name.startswith(prefix) for name in names)
            for prefix in required_prefixes
        ):
            raise RuntimeError(
                "The trace is missing required native or business spans."
            )
        span_rows = [
            row
            for row in trace_rows
            if row.get("table_name") in {"AppRequests", "AppDependencies"}
            and len(str(row.get("span_id", ""))) == 16
        ]
        ids = {str(row["span_id"]).lower() for row in span_rows}
        if len(ids) != len(span_rows):
            raise RuntimeError("The trace contains duplicate span identifiers.")
        api_role = "agent-blueprints.maf-workflow"
        hosted_role = item["hosted_agent_name"]
        roles = {str(row.get("role_name", "")) for row in trace_rows}
        if api_role not in roles or hosted_role not in roles:
            raise RuntimeError(
                "The trace does not cover both API and hosted service roles."
            )
        unexpected = [
            row
            for row in span_rows
            if row.get("role_name") not in {api_role, hosted_role}
        ]
        if unexpected:
            raise RuntimeError("The trace contains spans from an unexpected role.")

        api_rows = [row for row in span_rows if row.get("role_name") == api_role]
        hosted_rows = [row for row in span_rows if row.get("role_name") == hosted_role]
        if not api_rows or not hosted_rows:
            raise RuntimeError("The trace lacks a required service span graph.")
        boundaries = [
            row
            for row in span_rows
            if str(row.get("parent_id", "")).lower() not in ids
        ]
        if len(boundaries) != 2:
            raise RuntimeError(
                "The trace must expose exactly two distributed boundary parents."
            )
        api_boundaries = [
            row for row in boundaries if row.get("role_name") == api_role
        ]
        if len(api_boundaries) != 1:
            raise RuntimeError("The API caller boundary is ambiguous.")
        hosted_boundary = next(
            (
                row
                for row in boundaries
                if str(row.get("span_id", "")).lower()
                == str(hosted_root["span_id"]).lower()
            ),
            None,
        )
        if hosted_boundary is None:
            raise RuntimeError(
                "The hosted invoke_agent root lacks its propagated platform parent."
            )
        external_parents = {
            str(row.get("parent_id", "")).lower() for row in boundaries
        }
        if "" in external_parents or len(external_parents) != 2:
            raise RuntimeError("The distributed boundary parents are not explicit.")
        children = {}
        for row in span_rows:
            children.setdefault(
                str(row.get("parent_id", "")).lower(),
                [],
            ).append(str(row["span_id"]).lower())
        visited = set()
        pending = [str(row["span_id"]).lower() for row in boundaries]
        while pending:
            span_id = pending.pop()
            if span_id in visited:
                continue
            visited.add(span_id)
            pending.extend(children.get(span_id, ()))
        if visited != ids:
            raise RuntimeError("The distributed trace contains disconnected spans.")
        boundary_classifications = [
            {
                "parent_id": str(api_boundaries[0]["parent_id"]).lower(),
                "child_span_id": str(api_boundaries[0]["span_id"]).lower(),
                "classification": "expected-external-caller-boundary",
            },
            {
                "parent_id": str(hosted_boundary["parent_id"]).lower(),
                "child_span_id": str(hosted_boundary["span_id"]).lower(),
                "classification": "expected-agentserver-platform-parent-boundary",
            },
        ]
        graph_mode = "platform-parent-gap"
        key = (item["case_id"], item["conversation_id"])
        if item["hosted_phase"] == "resume":
            restart = next(
                (
                    row
                    for row in trace_rows
                    if row.get("span_name") == "order_resolution.workflow.resume"
                ),
                None,
            )
            if restart is None or not restart.get("link_span_id"):
                raise RuntimeError(
                    "The durable resume is missing its explicit trace link."
                )
            start_trace_id = starts.get(key)
            if start_trace_id is None or restart.get("link_trace_id") != start_trace_id:
                raise RuntimeError(
                    "The durable resume trace link does not target its start trace."
                )
        validated.append(
            {
                "trace_id": trace_id,
                "case_id": item["case_id"],
                "conversation_id": item["conversation_id"],
                "hosted_phase": item["hosted_phase"],
                "root_kind": root_kind,
                "graph_mode": graph_mode,
                "external_parent_count": len(external_parents),
                "boundary_classifications": boundary_classifications,
                "span_count": len(span_rows),
            }
        )
    return validated


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
    foundry_evidence=None,
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
    hosted_expected = any(item.get("hosted_phase") for item in expected)
    if hosted_expected and foundry_evidence is None:
        raise ValueError("Foundry trajectory evidence is required for hosted traces.")
    foundry_trace_ids = set()
    foundry_value = None
    if foundry_evidence is not None:
        foundry_trace_ids, foundry_value = _foundry_trace_ids(foundry_evidence)
        for key, expected_value in (
            ("source_revision", source_revision),
            ("deployment_revision", deployment_revision),
            ("environment", environment),
        ):
            if foundry_value.get(key) != expected_value:
                raise ValueError(f"Foundry trajectory {key} does not match.")
    query = _query(expected, evidence["started_at"])
    trace_query = _trace_query(expected, evidence["started_at"])
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
            trace_rows = []
            if trace_query is not None:
                detail = subprocess.run(
                    [
                        _azure_cli(),
                        "monitor",
                        "log-analytics",
                        "query",
                        "--workspace",
                        query_workspace,
                        "--analytics-query",
                        trace_query,
                        "--output",
                        "json",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if detail.returncode == 0:
                    try:
                        trace_rows = _rows(json.loads(detail.stdout))
                    except json.JSONDecodeError:
                        trace_rows = []
                try:
                    validated_traces = _validate_trace_rows(
                        expected,
                        trace_rows,
                        foundry_trace_ids,
                    )
                except RuntimeError:
                    validated_traces = []
                if hosted_expected and not validated_traces:
                    if attempt < attempts:
                        time.sleep(wait_seconds)
                        continue
                    raise RuntimeError(
                        "App Insights or Foundry did not corroborate the hosted trace graph."
                    )
            else:
                validated_traces = []
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
        "validated_hosted_traces": validated_traces,
        "foundry_evidence": (
            {
                "recorded_at": foundry_value.get("recorded_at"),
                "agent_name": foundry_value.get("agent_name"),
                "trace_ids": sorted(foundry_trace_ids),
            }
            if foundry_value is not None
            else None
        ),
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
    parser.add_argument("--foundry-evidence", type=Path)
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
            foundry_evidence=args.foundry_evidence,
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
