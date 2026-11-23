#!/usr/bin/env python3
"""Capture privacy-safe Foundry trajectory-index evidence for hosted traces."""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.verify_app_insights_correlation import _azure_cli, _quoted
except ModuleNotFoundError:
    from verify_app_insights_correlation import _azure_cli, _quoted


def _single_line(value):
    return " ".join(line.strip() for line in value.splitlines() if line.strip())


def _query(trace_ids, started_at):
    expected = json.dumps(trace_ids, separators=(",", ":"))
    return _single_line(
        f"""
        let expected = dynamic({expected});
        AppRequests
        | where TimeGenerated between (datetime({_quoted(started_at)}) .. now())
        | extend trace_id=tolower(tostring(OperationId)), properties=Properties
        | where trace_id in (expected)
        | extend operation_name=tostring(properties['gen_ai.operation.name']),
                 conversation_id=coalesce(
                     tostring(properties['gen_ai.conversation.id']),
                     tostring(properties['azure.ai.agentserver.conversation_id'])
                 ),
                 agent_name=coalesce(
                     tostring(properties['gen_ai.agent.name']),
                     tostring(properties['azure.ai.agentserver.agent_name'])
                 ),
                 agent_version=coalesce(
                     tostring(properties['gen_ai.agent.version']),
                     tostring(properties['azure.ai.agentserver.agent_version'])
                 ),
                 foundry_marker=coalesce(
                     tostring(properties['azure.ai.foundry.agent.id']),
                     tostring(properties['azure.ai.agentserver.agent_id']),
                     tostring(properties['azure.ai.agentserver.is_hosted'])
                 )
        | where operation_name == 'invoke_agent' and isnotempty(foundry_marker)
        | project trace_id, span_id=tolower(tostring(Id)),
                  parent_id=tolower(tostring(ParentId)), conversation_id,
                  agent_name, agent_version, foundry_marker
        """
    )


def capture(
    evidence_path,
    workspace,
    output_path,
    *,
    source_revision,
    deployment_revision,
    environment,
    attempts=12,
    wait_seconds=10,
):
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    for key, expected in (
        ("source_revision", source_revision),
        ("deployment_revision", deployment_revision),
        ("environment", environment),
    ):
        if evidence.get(key) != expected:
            raise ValueError(f"Evidence {key} does not match the requested value.")
    hosted = [
        item
        for item in evidence.get("correlations", [])
        if item.get("hosted_phase") in {"start", "resume"}
    ]
    if not hosted:
        raise ValueError("No hosted trace correlations were supplied.")
    expected = {}
    for item in hosted:
        trace_id = str(item.get("trace_id", "")).lower()
        if len(trace_id) != 32:
            raise ValueError("A hosted trace ID is invalid.")
        expected[trace_id] = item

    az = _azure_cli()
    query = _query(sorted(expected), evidence["started_at"])
    result = None
    for attempt in range(1, attempts + 1):
        result = subprocess.run(
            [
                az,
                "monitor",
                "log-analytics",
                "query",
                "--workspace",
                workspace,
                "--analytics-query",
                query,
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            rows = json.loads(result.stdout or "[]")
            observed = {str(row.get("trace_id", "")).lower() for row in rows}
            if observed == set(expected):
                break
        if attempt < attempts:
            time.sleep(wait_seconds)
    else:
        detail = (result.stderr if result is not None else "").strip()
        raise RuntimeError(
            "Foundry trajectory roots were not visible for every hosted trace."
            + (f" Azure CLI: {detail}" if detail else "")
        )

    rows_by_trace = {}
    for row in rows:
        trace_id = str(row["trace_id"]).lower()
        if trace_id in rows_by_trace:
            raise RuntimeError("A hosted trace has multiple Foundry trajectory roots.")
        item = expected[trace_id]
        if row.get("conversation_id") != item.get("conversation_id"):
            raise RuntimeError("Foundry trajectory conversation continuity failed.")
        if row.get("agent_name") != item.get("hosted_agent_name"):
            raise RuntimeError("Foundry trajectory agent identity failed.")
        if row.get("agent_version") != item.get("hosted_agent_version"):
            raise RuntimeError("Foundry trajectory agent version failed.")
        rows_by_trace[trace_id] = {
            "trace_id": trace_id,
            "span_id": row["span_id"],
            "parent_id": row.get("parent_id", ""),
            "conversation_id": row["conversation_id"],
            "agent_name": row["agent_name"],
            "agent_version": row["agent_version"],
        }

    artifact = {
        "schema_version": "1.0.0",
        "evidence_kind": "foundry_trajectory_index",
        "outcome": "passed",
        "source_revision": source_revision,
        "deployment_revision": deployment_revision,
        "environment": environment,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "agent_name": next(iter(rows_by_trace.values()))["agent_name"],
        "trace_ids": sorted(rows_by_trace),
        "trajectories": [rows_by_trace[key] for key in sorted(rows_by_trace)],
        "query": query,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--deployment-revision", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--wait-seconds", type=int, default=10)
    args = parser.parse_args()
    capture(
        args.evidence,
        args.workspace,
        args.output,
        source_revision=args.source_revision,
        deployment_revision=args.deployment_revision,
        environment=args.environment,
        attempts=args.attempts,
        wait_seconds=args.wait_seconds,
    )


if __name__ == "__main__":
    main()
