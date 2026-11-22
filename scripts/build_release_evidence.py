"""Build a secret-free release evidence manifest from independently produced artifacts."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _find(root, name):
    matches = [path for path in Path(root).rglob(name) if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {name} artifact.")
    return matches[0]


def _check_metadata(
    document, source_revision, *, deployment_revision=None, environment=None
):
    if document.get("source_revision") != source_revision:
        raise ValueError("Evidence source revision mismatch.")
    if (
        deployment_revision is not None
        and document.get("deployment_revision") != deployment_revision
    ):
        raise ValueError("Evidence deployment revision mismatch.")
    if environment is not None and document.get("environment") != environment:
        raise ValueError("Evidence environment mismatch.")


def _evidence(
    root,
    path,
    *,
    check_id,
    kind,
    source_revision,
    deployment_revision,
    environment,
    recorded_at,
):
    resolved_root = Path(root).resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("Evidence paths must remain inside the evidence root.")
    return {
        "check_id": check_id,
        "kind": kind,
        "reference": resolved.relative_to(resolved_root).as_posix(),
        "source_revision": source_revision,
        "deployment_revision": deployment_revision,
        "environment": environment,
        "recorded_at": recorded_at,
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def build(
    evidence_root,
    implementation_root,
    output,
    *,
    source_revision,
    deployment_revision,
    environment,
    agent_version,
    active_revision=None,
    provider_evaluation=None,
    browser=None,
    failure_injection=None,
    telemetry=None,
    security=None,
    cost=None,
    human_review=None,
):
    evidence_root = Path(evidence_root).resolve()
    implementation_root = Path(implementation_root).resolve()
    recorded_at = datetime.now(timezone.utc).isoformat()
    runner = _find(implementation_root, "runner-results.json")
    technical = _find(
        implementation_root,
        "ORDER-RESOLUTION-TECHNICAL-EXECUTION.json",
    )
    business = _find(
        implementation_root,
        "ORDER-RESOLUTION-BUSINESS-OUTCOME.json",
    )
    implementation_documents = [_read(path) for path in (runner, technical, business)]
    for document in implementation_documents:
        _check_metadata(document, source_revision)
    scenario_records = implementation_documents[0].get("cases", {})
    implementation_passed = (
        set(scenario_records) == {f"ORS-{number:03d}" for number in range(1, 10)}
        and all(item.get("outcome") == "passed" for item in scenario_records.values())
        and implementation_documents[1].get("outcome") == "passed"
        and implementation_documents[2].get("outcome") == "passed"
    )
    implementation_evidence = [
        _evidence(
            evidence_root,
            path,
            check_id=check_id,
            kind=kind,
            source_revision=source_revision,
            deployment_revision=None,
            environment=document["environment"],
            recorded_at=document["recorded_at"],
        )
        for path, document, check_id, kind in (
            (runner, implementation_documents[0], "ORS-001-009", "local_test"),
            (
                technical,
                implementation_documents[1],
                "TECHNICAL-EXECUTION",
                "evaluation_result",
            ),
            (
                business,
                implementation_documents[2],
                "BUSINESS-OUTCOME",
                "evaluation_result",
            ),
        )
    ]

    cloud_sources = (
        ("ACTIVE-REVISION", "active_revision", active_revision),
        ("HOSTED-EXECUTION", "hosted_test", failure_injection),
        ("MODEL-QUALITY", "evaluation_result", provider_evaluation),
        ("BROWSER-E2E", "browser_test", browser),
        ("FAILURE-INJECTION", "failure_injection", failure_injection),
        ("APP-INSIGHTS-CORRELATION", "telemetry_query", telemetry),
    )
    cloud_evidence = []
    cloud_passed = True
    for check_id, kind, path in cloud_sources:
        if path is None:
            cloud_passed = False
            continue
        document = _read(path)
        _check_metadata(
            document,
            source_revision,
            deployment_revision=deployment_revision,
            environment=environment,
        )
        if kind in {"hosted_test", "failure_injection"}:
            passed = all(
                item.get("status") == "passed"
                for item in document.get("scenarios", {}).values()
            )
        else:
            passed = document.get("outcome") == "passed"
        cloud_passed &= passed
        cloud_evidence.append(
            _evidence(
                evidence_root,
                path,
                check_id=check_id,
                kind=kind,
                source_revision=source_revision,
                deployment_revision=deployment_revision,
                environment=environment,
                recorded_at=document["recorded_at"],
            )
        )

    production_sources = (
        ("SECURITY-REVIEW", "security_report", security),
        ("COST-REVIEW", "cost_report", cost),
        ("HUMAN-RISK-ACCEPTANCE", "human_review", human_review),
    )
    production_evidence = []
    production_passed = implementation_passed and cloud_passed
    for check_id, kind, path in production_sources:
        if path is None:
            production_passed = False
            continue
        document = _read(path)
        _check_metadata(
            document,
            source_revision,
            deployment_revision=deployment_revision,
            environment=environment,
        )
        production_passed &= document.get("outcome") == "passed"
        production_evidence.append(
            _evidence(
                evidence_root,
                path,
                check_id=check_id,
                kind=kind,
                source_revision=source_revision,
                deployment_revision=deployment_revision,
                environment=environment,
                recorded_at=document["recorded_at"],
            )
        )

    manifest = {
        "schema_version": "1.0.0",
        "source_revision": source_revision,
        "environment": environment,
        "agent_version": agent_version,
        "deployment_revision": deployment_revision,
        "recorded_at": recorded_at,
        "dimensions": {
            "implementation": {
                "status": "passed" if implementation_passed else "failed",
                "reason": "Exact revision local ORS and deterministic evaluation evidence.",
                "required_checks": [
                    "ORS-001-009",
                    "TECHNICAL-EXECUTION",
                    "BUSINESS-OUTCOME",
                ],
                "evidence": implementation_evidence,
                "blockers": [],
            },
            "azure_runtime": {
                "status": "passed" if cloud_passed else "unverified",
                "reason": (
                    "Every exact-revision hosted gate passed."
                    if cloud_passed
                    else "One or more exact-revision hosted gates lack passing evidence."
                ),
                "required_checks": [item[0] for item in cloud_sources],
                "evidence": cloud_evidence,
                "blockers": [],
            },
            "production": {
                "status": "passed" if production_passed else "blocked",
                "reason": (
                    "Production evidence and scoped human review passed."
                    if production_passed
                    else "Production readiness requires passed implementation, Azure runtime, security, cost, and human review."
                ),
                "required_checks": [item[0] for item in production_sources],
                "evidence": production_evidence,
                "blockers": (
                    []
                    if production_passed
                    else ["Production prerequisites are incomplete or not passed."]
                ),
            },
        },
    }
    Path(output).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--implementation-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--deployment-revision", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--agent-version", required=True)
    for name in (
        "active-revision",
        "provider-evaluation",
        "browser",
        "failure-injection",
        "telemetry",
        "security",
        "cost",
        "human-review",
    ):
        parser.add_argument(f"--{name}", type=Path)
    args = parser.parse_args()
    try:
        build(
            args.evidence_root,
            args.implementation_root,
            args.output,
            source_revision=args.source_revision,
            deployment_revision=args.deployment_revision,
            environment=args.environment,
            agent_version=args.agent_version,
            active_revision=args.active_revision,
            provider_evaluation=args.provider_evaluation,
            browser=args.browser,
            failure_injection=args.failure_injection,
            telemetry=args.telemetry,
            security=args.security,
            cost=args.cost,
            human_review=args.human_review,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(
            f"Release evidence build failed: {type(error).__name__}.", file=sys.stderr
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
