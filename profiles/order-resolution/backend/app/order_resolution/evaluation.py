"""Native MAF evaluation configuration for canonical Order Resolution results."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_framework import (
    AgentResponse,
    Evaluator,
    LocalEvaluator,
    Message,
    evaluate_agent,
    evaluator,
)

from app.extensions.evaluation import (
    EvaluationAssessment,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRubric,
    RealProviderEvaluationSettings,
    RubricCriterion,
    map_evaluation_results,
    unavailable_assessment,
)


DATASET_FILENAME = "order-resolution-0.1.0.json"
DATASET_ID = "order-resolution-evaluation"
DATASET_VERSION = "0.1.0"
SPECIFICATION_ID = "order-resolution-spec"
SPECIFICATION_VERSION = "0.1.0"

TECHNICAL_EXECUTION_CHECK_ID = "ORDER-RESOLUTION-TECHNICAL-EXECUTION"
BUSINESS_OUTCOME_CHECK_ID = "ORDER-RESOLUTION-BUSINESS-OUTCOME"
MODEL_QUALITY_CHECK_ID = "ORDER-RESOLUTION-MODEL-QUALITY"
BROWSER_EVIDENCE_CHECK_ID = "ORDER-RESOLUTION-BROWSER-EVIDENCE"
PROVENANCE_CHECK_ID = "ORDER-RESOLUTION-PROVENANCE"

EXPECTED_SCENARIO_IDS = tuple(f"ORS-{number:03d}" for number in range(1, 10))
DETERMINISTIC_CHECK_IDS = (
    TECHNICAL_EXECUTION_CHECK_ID,
    BUSINESS_OUTCOME_CHECK_ID,
)
READINESS_CHECK_IDS = (
    *DETERMINISTIC_CHECK_IDS,
    MODEL_QUALITY_CHECK_ID,
    BROWSER_EVIDENCE_CHECK_ID,
    PROVENANCE_CHECK_ID,
)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and whitespace-trimmed.")
    return value


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    return value


def _require_string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list.")
    items = tuple(_require_text(item, label) for item in value)
    if len(items) != len(set(items)):
        raise ValueError(f"{label} must contain unique values.")
    return items


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _parse_response(value: str) -> Mapping[str, object] | None:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _matches_expected_section(
    response: str, expected_output: str, section: str
) -> bool:
    actual = _parse_response(response)
    expected = _parse_response(expected_output)
    if actual is None or expected is None:
        return False
    return actual.get("scenario_ids") == expected.get("scenario_ids") and actual.get(
        section
    ) == expected.get(section)


@evaluator(name="order-resolution-technical-execution")
def exact_technical_execution(response: str, expected_output: str) -> bool:
    """Compare actual runtime/checkpoint facts with canonical technical expectations."""
    return _matches_expected_section(response, expected_output, "technical_execution")


@evaluator(name="order-resolution-business-outcome")
def exact_business_outcome(response: str, expected_output: str) -> bool:
    """Compare actual application outcomes with canonical business expectations."""
    return _matches_expected_section(response, expected_output, "business_outcome")


ORDER_RESOLUTION_LOCAL_EVALUATOR: Evaluator = LocalEvaluator(
    exact_technical_execution,
    exact_business_outcome,
)
MODEL_QUALITY_CRITERION_ID = "order-resolution-model-quality"


@dataclass(frozen=True)
class ScenarioGroup:
    case_id: str
    query: str
    scenario_ids: tuple[str, ...]
    check_ids: tuple[str, ...]


@dataclass(frozen=True)
class OrderResolutionEvaluationConfiguration:
    specification_id: str
    specification_version: str
    golden_cases_path: str
    groups: tuple[ScenarioGroup, ...]
    dataset: EvaluationDataset
    rubric: EvaluationRubric


@dataclass(frozen=True)
class ReadinessState:
    area: str
    check_id: str
    outcome: str
    reason: str


def load_evaluation_configuration(
    path: Path | None = None,
) -> OrderResolutionEvaluationConfiguration:
    dataset_path = (
        path or Path(__file__).resolve().parents[2] / "evaluations" / DATASET_FILENAME
    )
    root = _require_mapping(
        json.loads(dataset_path.read_text(encoding="utf-8")),
        "Evaluation configuration",
    )
    if root.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported evaluation configuration schema version.")
    if (
        root.get("dataset_id") != DATASET_ID
        or root.get("dataset_version") != DATASET_VERSION
    ):
        raise ValueError("Unexpected Order Resolution evaluation dataset identity.")

    specification = _require_mapping(root.get("specification"), "Specification")
    specification_id = _require_text(specification.get("id"), "Specification ID")
    specification_version = _require_text(
        specification.get("version"), "Specification version"
    )
    if (
        specification_id != SPECIFICATION_ID
        or specification_version != SPECIFICATION_VERSION
    ):
        raise ValueError("Unexpected Order Resolution specification identity.")
    golden_cases_path = _require_text(
        specification.get("golden_cases_path"), "Golden cases path"
    )

    raw_rubric = _require_mapping(root.get("rubric"), "Evaluation rubric")
    raw_criteria = raw_rubric.get("criteria")
    if not isinstance(raw_criteria, list):
        raise ValueError("Evaluation rubric criteria must be a list.")
    rubric = EvaluationRubric(
        rubric_id=_require_text(raw_rubric.get("rubric_id"), "Rubric ID"),
        version=_require_text(raw_rubric.get("rubric_version"), "Rubric version"),
        criteria=tuple(
            RubricCriterion(
                criterion_id=_require_text(item.get("criterion_id"), "Criterion ID"),
                check_id=_require_text(item.get("check_id"), "Readiness check ID"),
                minimum_score=item.get("minimum_score"),
            )
            for value in raw_criteria
            for item in (_require_mapping(value, "Rubric criterion"),)
        ),
    )

    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("Evaluation cases must be a list.")
    groups = tuple(
        ScenarioGroup(
            case_id=_require_text(item.get("case_id"), "Evaluation case ID"),
            query=_require_text(item.get("query"), "Evaluation query"),
            scenario_ids=_require_string_tuple(
                item.get("scenario_ids"), "Scenario IDs"
            ),
            check_ids=_require_string_tuple(
                item.get("check_ids"), "Readiness check IDs"
            ),
        )
        for value in raw_cases
        for item in (_require_mapping(value, "Evaluation case"),)
    )
    if not groups or len({group.case_id for group in groups}) != len(groups):
        raise ValueError("Evaluation cases must have unique IDs.")
    if len({group.query for group in groups}) != len(groups):
        raise ValueError("Evaluation queries must be unique.")
    scenario_ids = tuple(
        sorted(scenario_id for group in groups for scenario_id in group.scenario_ids)
    )
    if scenario_ids != EXPECTED_SCENARIO_IDS:
        raise ValueError(
            "Evaluation cases must reference ORS-001 through ORS-009 exactly once."
        )
    if any(set(group.check_ids) != set(DETERMINISTIC_CHECK_IDS) for group in groups):
        raise ValueError("Each evaluation case must map to both deterministic checks.")

    dataset = EvaluationDataset(
        dataset_id=DATASET_ID,
        version=DATASET_VERSION,
        cases=tuple(
            EvaluationCase(
                case_id=group.case_id,
                inputs={"query": group.query},
                check_ids=group.check_ids,
            )
            for group in groups
        ),
    )
    rubric.validate_for(dataset, READINESS_CHECK_IDS)
    return OrderResolutionEvaluationConfiguration(
        specification_id=specification_id,
        specification_version=specification_version,
        golden_cases_path=golden_cases_path,
        groups=groups,
        dataset=dataset,
        rubric=rubric,
    )


def load_golden_expected_outputs(
    path: Path,
) -> dict[str, Mapping[str, object]]:
    root = _require_mapping(
        json.loads(path.read_text(encoding="utf-8")),
        "Golden cases",
    )
    if root.get("scenario_set") != f"{SPECIFICATION_ID}/{SPECIFICATION_VERSION}":
        raise ValueError("Golden cases do not match the evaluation specification.")
    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("Golden cases must be a list.")
    expected: dict[str, Mapping[str, object]] = {}
    for raw_case in raw_cases:
        case = _require_mapping(raw_case, "Golden case")
        case_id = _require_text(case.get("id"), "Golden case ID")
        if case_id in expected:
            raise ValueError("Golden case IDs must be unique.")
        outcome = _require_mapping(case.get("expected"), "Golden expected result")
        if set(outcome) != {"business_outcome", "technical_execution"}:
            raise ValueError(
                "Golden results must keep business and technical facts distinct."
            )
        expected[case_id] = outcome
    if tuple(sorted(expected)) != EXPECTED_SCENARIO_IDS:
        raise ValueError("Golden cases must contain ORS-001 through ORS-009 exactly.")
    return expected


def build_group_payloads(
    configuration: OrderResolutionEvaluationConfiguration,
    scenario_results: Mapping[str, Mapping[str, object]],
) -> tuple[str, ...]:
    if tuple(sorted(scenario_results)) != EXPECTED_SCENARIO_IDS:
        raise ValueError(
            "Scenario results must contain ORS-001 through ORS-009 exactly."
        )
    payloads = []
    for group in configuration.groups:
        business = {}
        technical = {}
        for scenario_id in group.scenario_ids:
            result = _require_mapping(scenario_results[scenario_id], "Scenario result")
            business[scenario_id] = _require_mapping(
                result.get("business_outcome"), "Business outcome"
            )
            technical[scenario_id] = _require_mapping(
                result.get("technical_execution"), "Technical execution"
            )
        payloads.append(
            _canonical_json(
                {
                    "scenario_ids": list(group.scenario_ids),
                    "business_outcome": business,
                    "technical_execution": technical,
                }
            )
        )
    return tuple(payloads)


async def evaluate_deterministic_results(
    configuration: OrderResolutionEvaluationConfiguration,
    actual_results: Mapping[str, Mapping[str, object]],
    expected_results: Mapping[str, Mapping[str, object]],
    evaluator_provider: Evaluator = ORDER_RESOLUTION_LOCAL_EVALUATOR,
) -> EvaluationAssessment:
    """Run native MAF evaluation and normalize it with the merged #39 mapper."""
    actual_payloads = build_group_payloads(configuration, actual_results)
    expected_payloads = build_group_payloads(configuration, expected_results)
    native_results = await evaluate_agent(
        queries=[group.query for group in configuration.groups],
        responses=[
            AgentResponse(messages=[Message(role="assistant", contents=[payload])])
            for payload in actual_payloads
        ],
        expected_output=list(expected_payloads),
        evaluators=evaluator_provider,
        eval_name="order-resolution-deterministic-evaluation",
    )
    return map_evaluation_results(
        configuration.dataset,
        configuration.rubric,
        READINESS_CHECK_IDS,
        native_results,
    )


async def evaluate_real_provider_results(
    configuration: OrderResolutionEvaluationConfiguration,
    actual_results: Mapping[str, Mapping[str, object]],
    expected_results: Mapping[str, Mapping[str, object]],
    evaluator_provider: Evaluator,
    settings: RealProviderEvaluationSettings,
) -> EvaluationAssessment:
    """Run an explicitly configured provider evaluator without synthetic fallback."""
    if not settings.enabled:
        raise ValueError("Real-provider evaluation was not explicitly enabled.")
    dataset = EvaluationDataset(
        dataset_id=f"{configuration.dataset.dataset_id}-real-provider",
        version=configuration.dataset.version,
        cases=tuple(
            EvaluationCase(
                case_id=group.case_id,
                inputs={"query": group.query},
                check_ids=(MODEL_QUALITY_CHECK_ID,),
            )
            for group in configuration.groups
        ),
    )
    rubric = EvaluationRubric(
        rubric_id="order-resolution-real-provider",
        version=configuration.rubric.version,
        criteria=(
            RubricCriterion(
                MODEL_QUALITY_CRITERION_ID,
                MODEL_QUALITY_CHECK_ID,
                settings.minimum_score,
            ),
        ),
    )
    rubric.validate_for(dataset, READINESS_CHECK_IDS)
    actual_payloads = build_group_payloads(configuration, actual_results)
    expected_payloads = build_group_payloads(configuration, expected_results)
    native_results = await evaluate_agent(
        queries=[group.query for group in configuration.groups],
        responses=[
            AgentResponse(messages=[Message(role="assistant", contents=[payload])])
            for payload in actual_payloads
        ],
        expected_output=list(expected_payloads),
        evaluators=evaluator_provider,
        eval_name=(
            "order-resolution-real-provider-"
            f"{settings.provider_id}-{settings.deployment_revision}"
        ),
    )
    return map_evaluation_results(
        dataset,
        rubric,
        READINESS_CHECK_IDS,
        native_results,
    )


def unavailable_deterministic_assessment(
    configuration: OrderResolutionEvaluationConfiguration,
) -> EvaluationAssessment:
    return unavailable_assessment(
        configuration.dataset,
        configuration.rubric,
        READINESS_CHECK_IDS,
    )


def map_readiness_states(
    assessment: EvaluationAssessment,
    model_assessment: EvaluationAssessment | None = None,
) -> tuple[ReadinessState, ...]:
    """Keep deterministic, model, browser, and provenance evidence independent."""
    mapped = {result.check_id: result for result in assessment.check_results}
    model_result = (
        next(
            (
                result
                for result in model_assessment.check_results
                if result.check_id == MODEL_QUALITY_CHECK_ID
            ),
            None,
        )
        if model_assessment is not None
        else None
    )
    return (
        ReadinessState(
            "technical_execution",
            TECHNICAL_EXECUTION_CHECK_ID,
            mapped[TECHNICAL_EXECUTION_CHECK_ID].outcome,
            mapped[TECHNICAL_EXECUTION_CHECK_ID].reason,
        ),
        ReadinessState(
            "business_outcome",
            BUSINESS_OUTCOME_CHECK_ID,
            mapped[BUSINESS_OUTCOME_CHECK_ID].outcome,
            mapped[BUSINESS_OUTCOME_CHECK_ID].reason,
        ),
        ReadinessState(
            "model_quality",
            MODEL_QUALITY_CHECK_ID,
            model_result.outcome if model_result is not None else "unverified",
            (
                model_result.reason
                if model_result is not None
                else "No explicitly configured real model or provider evaluation was executed."
            ),
        ),
        ReadinessState(
            "browser_evidence",
            BROWSER_EVIDENCE_CHECK_ID,
            "unverified",
            "No actual browser execution artifact is present.",
        ),
        ReadinessState(
            "provenance",
            PROVENANCE_CHECK_ID,
            "unverified",
            "Local evidence digests are not independently attested trusted provenance.",
        ),
    )
