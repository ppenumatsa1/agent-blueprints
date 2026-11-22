"""Execute canonical Order Resolution cases and produce local readiness evidence."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.order_resolution.evaluation import (  # noqa: E402
    BUSINESS_OUTCOME_CHECK_ID,
    MODEL_QUALITY_CHECK_ID,
    TECHNICAL_EXECUTION_CHECK_ID,
    evaluate_deterministic_results,
    evaluate_real_provider_results,
    load_evaluation_configuration,
    load_golden_expected_outputs,
    map_readiness_states,
)
from app.extensions.evaluation import (  # noqa: E402
    RealProviderEvaluationSettings,
    load_real_provider_evaluator,
)
from tests.order_resolution_adapter import run_case  # noqa: E402


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _redacted_failure(error: Exception) -> dict[str, str]:
    message = str(error)
    dsn = os.environ.get("MAF_TEST_DATABASE_URL", "")
    if dsn:
        message = message.replace(dsn, "[redacted database URL]")
        password = urlsplit(dsn).password
        if password:
            for value in (password, unquote(password)):
                message = message.replace(value, "[redacted]")
    return {"type": type(error).__name__, "message": message}


def _evidence(
    output: Path,
    kind: str,
    filename: str,
    revision: str,
    environment: str,
    recorded_at: str,
) -> dict[str, str]:
    return {
        "kind": kind,
        "reference": filename,
        "revision": revision,
        "environment": environment,
        "recorded_at": recorded_at,
        "sha256": hashlib.sha256((output / filename).read_bytes()).hexdigest(),
    }


def execute_cases(
    cases: list[dict[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    actual_results = {}
    records = {}
    for case in cases:
        case_id = case["id"]
        try:
            actual = run_case(case)
            expected = case["expected"]
            outcome = "passed" if actual == expected else "failed"
            records[case_id] = {
                "outcome": outcome,
                "actual": actual,
                **(
                    {}
                    if outcome == "passed"
                    else {"reason": "Actual result did not exactly match the canonical case."}
                ),
            }
            actual_results[case_id] = actual
        except Exception as error:  # noqa: BLE001 - evidence retains an explicit failed case.
            failure = _redacted_failure(error)
            records[case_id] = {"outcome": "failed", "failure": failure}
            actual_results[case_id] = {
                "business_outcome": {"execution_failure": failure["type"]},
                "technical_execution": {"execution_failure": failure["type"]},
            }
    return actual_results, records


def produce(
    verification_root: Path,
    output: Path,
    revision: str,
    environment: str,
) -> dict[str, object]:
    if not revision.strip() or not environment.strip():
        raise ValueError("A source revision and environment are required.")
    if not os.environ.get("MAF_TEST_DATABASE_URL"):
        raise ValueError("MAF_TEST_DATABASE_URL must identify an isolated test database.")
    scenario_root = verification_root / "scenarios" / "order-resolution"
    golden_path = scenario_root / "golden-cases.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = golden.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Canonical Order Resolution cases are missing.")
    output.mkdir(parents=True, exist_ok=False)

    configuration = load_evaluation_configuration()
    expected_results = load_golden_expected_outputs(golden_path)
    actual_results, case_records = execute_cases(cases)
    assessment = asyncio.run(
        evaluate_deterministic_results(
            configuration,
            actual_results,
            expected_results,
        )
    )
    real_provider = RealProviderEvaluationSettings.from_environment()
    model_assessment = None
    if real_provider.enabled:
        model_assessment = asyncio.run(
            evaluate_real_provider_results(
                configuration,
                actual_results,
                expected_results,
                load_real_provider_evaluator(real_provider),
                real_provider,
            )
        )
    states = map_readiness_states(assessment, model_assessment)
    recorded_at = datetime.now(timezone.utc).isoformat()
    deployment_revision = os.environ.get("DEPLOYMENT_REVISION") or None

    _write_json(
        output / "runner-results.json",
        {
            "source_revision": revision,
            "environment": environment,
            "deployment_revision": deployment_revision,
            "recorded_at": recorded_at,
            "scenario_set": golden["scenario_set"],
            "cases": case_records,
        },
    )

    normalized = []
    for state in states:
        filename = f"{state.check_id}.json"
        observations = []
        if state.check_id in {
            TECHNICAL_EXECUTION_CHECK_ID,
            BUSINESS_OUTCOME_CHECK_ID,
        }:
            check = next(
                item for item in assessment.check_results if item.check_id == state.check_id
            )
            observations = [
                {
                    "case_id": item.case_id,
                    "criterion_id": item.criterion_id,
                    "score": item.score,
                    "minimum_score": item.minimum_score,
                    "native_reference": item.reference,
                }
                for item in check.observations
            ]
            _write_json(
                output / filename,
                {
                    "check_id": state.check_id,
                    "outcome": state.outcome,
                    "reason": state.reason,
                    "source_revision": revision,
                    "environment": environment,
                    "deployment_revision": deployment_revision,
                    "recorded_at": recorded_at,
                    "dataset_id": assessment.dataset_id,
                    "dataset_version": assessment.dataset_version,
                    "rubric_id": assessment.rubric_id,
                    "rubric_version": assessment.rubric_version,
                    "observations": observations,
                },
            )
            evidence = [
                _evidence(
                    output,
                    "evaluation_result",
                    filename,
                    revision,
                    environment,
                    recorded_at,
                ),
                _evidence(
                    output,
                    "trace",
                    "runner-results.json",
                    revision,
                    environment,
                    recorded_at,
                ),
            ]
        elif state.check_id == MODEL_QUALITY_CHECK_ID and model_assessment is not None:
            check = next(
                item
                for item in model_assessment.check_results
                if item.check_id == MODEL_QUALITY_CHECK_ID
            )
            observations = [
                {
                    "case_id": item.case_id,
                    "criterion_id": item.criterion_id,
                    "score": item.score,
                    "minimum_score": item.minimum_score,
                    "native_reference": item.reference,
                }
                for item in check.observations
            ]
            _write_json(
                output / filename,
                {
                    "check_id": state.check_id,
                    "outcome": state.outcome,
                    "reason": state.reason,
                    "source_revision": revision,
                    "environment": environment,
                    "deployment_revision": deployment_revision,
                    "recorded_at": recorded_at,
                    "provider": real_provider.provider_id,
                    "model": real_provider.model_id,
                    "dataset_id": model_assessment.dataset_id,
                    "dataset_version": model_assessment.dataset_version,
                    "rubric_id": model_assessment.rubric_id,
                    "rubric_version": model_assessment.rubric_version,
                    "observations": observations,
                },
            )
            evidence = [
                _evidence(
                    output,
                    "evaluation_result",
                    filename,
                    revision,
                    environment,
                    recorded_at,
                )
            ]
        else:
            evidence = []
        normalized.append(
            {
                "check_id": state.check_id,
                "outcome": state.outcome,
                "reason": state.reason,
                "implementation_refs": [
                    "app/order_resolution/evaluation.py",
                    "tests/order_resolution_adapter.py",
                    "tests/order_resolution_evidence_runner.py",
                ],
                "evidence": evidence,
            }
        )

    assessed_at = datetime.now(timezone.utc).isoformat()
    _write_json(
        output / "readiness-input.json",
        {
            "schema_version": "1.0.0",
            "context": {
                "target_maturity": "prototype",
                "source_revision": revision,
                "environment": environment,
                "assessed_at": assessed_at,
            },
            "assumptions": [
                "All orders, identities, policies, approvals, and effects are synthetic."
            ],
            "incomplete_integrations": [
                *(
                    []
                    if real_provider.enabled
                    else ["Real model/provider evaluation was not explicitly configured."]
                ),
                "No browser end-to-end execution was performed by this producer.",
                "Local evidence digests have no independently trusted producer attestation.",
            ],
            "limitations": [
                "The local producer cannot attest its own evidence as trusted provenance.",
                "The deterministic evaluator measures exact canonical outcomes, not LLM quality.",
                "No Azure resource, hosted agent, or consequential external effect was used.",
            ],
            "results": normalized,
            "decisions": [],
        },
    )

    state_map = {state.area: state.outcome for state in states}
    matrix = {
        "source_revision": revision,
        "environment": environment,
        "recorded_at": recorded_at,
        "scenario_results": {
            case_id: record["outcome"] for case_id, record in case_records.items()
        },
        "evaluation_results": state_map,
        "local_factory_status": (
            "passed"
            if all(record["outcome"] == "passed" for record in case_records.values())
            and state_map["technical_execution"] == "passed"
            and state_map["business_outcome"] == "passed"
            else "failed"
        ),
        "release_status": "blocked",
        "release_blockers": [
            *(
                []
                if state_map["model_quality"] == "passed"
                else ["real model quality is not passed"]
            ),
            "browser evidence is unverified",
            "trusted producer provenance is unverified",
            "deployment and real consequential effects are outside this milestone",
        ],
    }
    _write_json(output / "readiness-matrix.json", matrix)
    release_evidence = {
        "schema_version": "1.0.0",
        "source_revision": revision,
        "environment": environment,
        "agent_version": os.environ.get("AGENT_VERSION", "0.1.0"),
        "deployment_revision": deployment_revision,
        "recorded_at": recorded_at,
        "dimensions": {
            "implementation": {
                "status": matrix["local_factory_status"],
                "reason": "Canonical ORS scenarios and deterministic technical/business checks.",
                "required_checks": [
                    "ORS-001-009",
                    "TECHNICAL-EXECUTION",
                    "BUSINESS-OUTCOME",
                ],
                "evidence": [
                    {
                        "check_id": "ORS-001-009",
                        "kind": "local_test",
                        "reference": "runner-results.json",
                        "source_revision": revision,
                        "deployment_revision": deployment_revision,
                        "environment": environment,
                        "recorded_at": recorded_at,
                        "sha256": hashlib.sha256(
                            (output / "runner-results.json").read_bytes()
                        ).hexdigest(),
                    },
                    {
                        "check_id": "TECHNICAL-EXECUTION",
                        "kind": "evaluation_result",
                        "reference": f"{TECHNICAL_EXECUTION_CHECK_ID}.json",
                        "source_revision": revision,
                        "deployment_revision": deployment_revision,
                        "environment": environment,
                        "recorded_at": recorded_at,
                        "sha256": hashlib.sha256(
                            (output / f"{TECHNICAL_EXECUTION_CHECK_ID}.json").read_bytes()
                        ).hexdigest(),
                    },
                    {
                        "check_id": "BUSINESS-OUTCOME",
                        "kind": "evaluation_result",
                        "reference": f"{BUSINESS_OUTCOME_CHECK_ID}.json",
                        "source_revision": revision,
                        "deployment_revision": deployment_revision,
                        "environment": environment,
                        "recorded_at": recorded_at,
                        "sha256": hashlib.sha256(
                            (output / f"{BUSINESS_OUTCOME_CHECK_ID}.json").read_bytes()
                        ).hexdigest(),
                    },
                ],
                "blockers": [],
            },
            "azure_runtime": {
                "status": "unverified",
                "reason": "Cloud readiness remains unverified until every hosted gate has real evidence.",
                "required_checks": [
                    "ACTIVE-REVISION",
                    "HOSTED-EXECUTION",
                    "MODEL-QUALITY",
                    "BROWSER-E2E",
                    "FAILURE-INJECTION",
                    "APP-INSIGHTS-CORRELATION",
                ],
                "evidence": (
                    [
                        {
                            "check_id": "MODEL-QUALITY",
                            "kind": "evaluation_result",
                            "reference": f"{MODEL_QUALITY_CHECK_ID}.json",
                            "source_revision": revision,
                            "deployment_revision": deployment_revision,
                            "environment": environment,
                            "recorded_at": recorded_at,
                            "sha256": hashlib.sha256(
                                (output / f"{MODEL_QUALITY_CHECK_ID}.json").read_bytes()
                            ).hexdigest(),
                        }
                    ]
                    if model_assessment is not None
                    else []
                ),
                "blockers": [],
            },
            "production": {
                "status": "blocked",
                "reason": "Production readiness requires passed implementation and Azure runtime readiness.",
                "required_checks": [
                    "SECURITY-REVIEW",
                    "COST-REVIEW",
                    "HUMAN-RISK-ACCEPTANCE",
                ],
                "evidence": [],
                "blockers": [
                    "Azure runtime readiness is unverified.",
                    "Scoped production risk acceptance is not present.",
                ],
            },
        },
    }
    _write_json(output / "release-evidence.json", release_evidence)
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verification-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--environment", required=True)
    args = parser.parse_args()
    try:
        matrix = produce(
            args.verification_root.resolve(),
            args.output.resolve(),
            args.revision,
            args.environment,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Order Resolution evidence run failed: {error}", file=sys.stderr)
        return 2
    for case_id, outcome in matrix["scenario_results"].items():
        print(f"{case_id}: {outcome}")
    for area, outcome in matrix["evaluation_results"].items():
        print(f"{area}: {outcome}")
    print(f"local_factory_status: {matrix['local_factory_status']}")
    print(f"release_status: {matrix['release_status']}")
    return 0 if matrix["local_factory_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
