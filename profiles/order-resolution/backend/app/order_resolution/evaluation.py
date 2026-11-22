"""Order Resolution evaluation configuration and native MAF result mapping."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
from typing import Literal

from agent_framework import (
    EvalItemResult,
    EvalResults,
    EvalScoreResult,
    Evaluator,
    LocalEvaluator,
    evaluator,
)


Outcome = Literal["passed", "failed", "unverified"]

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
NATIVE_CHECK_IDS = (TECHNICAL_EXECUTION_CHECK_ID, BUSINESS_OUTCOME_CHECK_ID)
READINESS_CHECK_IDS = (
    TECHNICAL_EXECUTION_CHECK_ID,
    BUSINESS_OUTCOME_CHECK_ID,
    MODEL_QUALITY_CHECK_ID,
    BROWSER_EVIDENCE_CHECK_ID,
    PROVENANCE_CHECK_ID,
)


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and whitespace-trimmed.")
    return value


def _require_string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list.")
    items = tuple(_require_text(item, label) for item in value)
    if len(items) != len(set(items)):
        raise ValueError(f"{label} must contain unique values.")
    return items


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    return value


def _is_valid_score(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, int):
        return 0 <= value <= 1
    return isfinite(value) and 0 <= value <= 1


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
    """Require the normalized execution facts to match the declared expectation."""
    return _matches_expected_section(response, expected_output, "technical_execution")


@evaluator(name="order-resolution-business-outcome")
def exact_business_outcome(response: str, expected_output: str) -> bool:
    """Require the normalized business outcome to match the declared expectation."""
    return _matches_expected_section(response, expected_output, "business_outcome")


ORDER_RESOLUTION_LOCAL_EVALUATOR: Evaluator = LocalEvaluator(
    exact_technical_execution,
    exact_business_outcome,
)


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    query: str
    scenario_ids: tuple[str, ...]
    check_ids: tuple[str, ...]
    expected_output: Mapping[str, object]

    @property
    def expected_output_text(self) -> str:
        return _canonical_json(self.expected_output)


@dataclass(frozen=True)
class EvaluationDataset:
    dataset_id: str
    version: str
    specification_id: str
    specification_version: str
    cases: tuple[EvaluationCase, ...]

    def validate_for(
        self,
        rubric: "EvaluationRubric",
        known_check_ids: tuple[str, ...],
    ) -> None:
        known_checks = _validate_known_check_ids(known_check_ids)
        if self.dataset_id != DATASET_ID or self.version != DATASET_VERSION:
            raise ValueError("Unexpected Order Resolution evaluation dataset identity.")
        if (
            self.specification_id != SPECIFICATION_ID
            or self.specification_version != SPECIFICATION_VERSION
        ):
            raise ValueError("Unexpected Order Resolution specification identity.")
        if not self.cases or len({case.case_id for case in self.cases}) != len(
            self.cases
        ):
            raise ValueError("Evaluation cases must have unique IDs.")
        if len({case.query for case in self.cases}) != len(self.cases):
            raise ValueError(
                "Evaluation case queries must be unique for native result mapping."
            )
        scenario_ids = tuple(
            scenario_id for case in self.cases for scenario_id in case.scenario_ids
        )
        if tuple(sorted(scenario_ids)) != EXPECTED_SCENARIO_IDS:
            raise ValueError(
                "Evaluation cases must reference ORS-001 through ORS-009 exactly once."
            )
        dataset_checks = {
            check_id for case in self.cases for check_id in case.check_ids
        }
        rubric_checks = {criterion.check_id for criterion in rubric.criteria}
        if dataset_checks != rubric_checks:
            raise ValueError("Dataset check IDs must match rubric readiness check IDs.")
        unknown_checks = dataset_checks - known_checks
        if unknown_checks:
            unknown = ", ".join(sorted(unknown_checks))
            raise ValueError(
                f"Dataset checks are outside the readiness contract: {unknown}."
            )


@dataclass(frozen=True)
class RubricCriterion:
    criterion_id: str
    check_id: str
    minimum_score: float

    def __post_init__(self) -> None:
        _require_text(self.criterion_id, "Rubric criterion IDs")
        _require_text(self.check_id, "Readiness check IDs")
        if not _is_valid_score(self.minimum_score):
            raise ValueError(
                "Rubric minimum scores must be finite numbers from 0 to 1."
            )


@dataclass(frozen=True)
class EvaluationRubric:
    rubric_id: str
    version: str
    criteria: tuple[RubricCriterion, ...]


ORDER_RESOLUTION_RUBRIC = EvaluationRubric(
    rubric_id="order-resolution-deterministic-assertions",
    version="0.1.0",
    criteria=(
        RubricCriterion(
            criterion_id="order-resolution-technical-execution",
            check_id=TECHNICAL_EXECUTION_CHECK_ID,
            minimum_score=1.0,
        ),
        RubricCriterion(
            criterion_id="order-resolution-business-outcome",
            check_id=BUSINESS_OUTCOME_CHECK_ID,
            minimum_score=1.0,
        ),
    ),
)


def _validate_known_check_ids(known_check_ids: tuple[str, ...]) -> set[str]:
    if not isinstance(known_check_ids, tuple) or not known_check_ids:
        raise ValueError("Known readiness check IDs must be a non-empty tuple.")
    for check_id in known_check_ids:
        _require_text(check_id, "Known readiness check IDs")
    if len(known_check_ids) != len(set(known_check_ids)):
        raise ValueError("Known readiness check IDs must be unique.")
    return set(known_check_ids)


def load_evaluation_dataset(path: Path | None = None) -> EvaluationDataset:
    dataset_path = (
        path or Path(__file__).resolve().parents[2] / "evaluations" / DATASET_FILENAME
    )
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    root = _require_mapping(raw, "Evaluation dataset")
    if root.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported evaluation dataset schema version.")
    specification = _require_mapping(root.get("specification"), "Specification")
    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("Evaluation cases must be a list.")
    cases = []
    for raw_case in raw_cases:
        item = _require_mapping(raw_case, "Evaluation case")
        expected_output = _require_mapping(
            item.get("expected_output"), "Expected output"
        )
        scenario_ids = _require_string_tuple(item.get("scenario_ids"), "Scenario IDs")
        check_ids = _require_string_tuple(item.get("check_ids"), "Readiness check IDs")
        if set(check_ids) != set(NATIVE_CHECK_IDS):
            raise ValueError(
                "Each evaluation case must map to both deterministic checks."
            )
        if expected_output.get("scenario_ids") != list(scenario_ids):
            raise ValueError(
                "Expected output scenario IDs must match the evaluation case."
            )
        if set(expected_output) != {
            "scenario_ids",
            "technical_execution",
            "business_outcome",
        }:
            raise ValueError(
                "Expected output must keep execution and business facts distinct."
            )
        for section in ("technical_execution", "business_outcome"):
            section_value = _require_mapping(expected_output.get(section), section)
            if set(section_value) != set(scenario_ids):
                raise ValueError(
                    f"{section} must contain exactly the evaluation case scenario IDs."
                )
        cases.append(
            EvaluationCase(
                case_id=_require_text(item.get("case_id"), "Evaluation case IDs"),
                query=_require_text(item.get("query"), "Evaluation case queries"),
                scenario_ids=scenario_ids,
                check_ids=check_ids,
                expected_output=expected_output,
            )
        )
    dataset = EvaluationDataset(
        dataset_id=_require_text(root.get("dataset_id"), "Evaluation dataset ID"),
        version=_require_text(
            root.get("dataset_version"), "Evaluation dataset version"
        ),
        specification_id=_require_text(specification.get("id"), "Specification ID"),
        specification_version=_require_text(
            specification.get("version"), "Specification version"
        ),
        cases=tuple(cases),
    )
    dataset.validate_for(ORDER_RESOLUTION_RUBRIC, READINESS_CHECK_IDS)
    return dataset


@dataclass(frozen=True)
class EvaluationTraceReference:
    case_id: str
    criterion_id: str
    score: float
    minimum_score: float
    reference: str


@dataclass(frozen=True)
class CheckEvaluation:
    check_id: str
    outcome: Outcome
    reason: str
    observations: tuple[EvaluationTraceReference, ...]


@dataclass(frozen=True)
class EvaluationAssessment:
    dataset_id: str
    dataset_version: str
    rubric_id: str
    rubric_version: str
    check_results: tuple[CheckEvaluation, ...]
    diagnostics: tuple[str, ...] = ()

    @property
    def outcome(self) -> Outcome:
        if self.diagnostics or any(
            result.outcome == "failed" for result in self.check_results
        ):
            return "failed"
        if any(result.outcome == "unverified" for result in self.check_results):
            return "unverified"
        return "passed"


def _assessment(
    dataset: EvaluationDataset,
    results: Sequence[CheckEvaluation],
    diagnostics: Sequence[str] = (),
) -> EvaluationAssessment:
    return EvaluationAssessment(
        dataset.dataset_id,
        dataset.version,
        ORDER_RESOLUTION_RUBRIC.rubric_id,
        ORDER_RESOLUTION_RUBRIC.version,
        tuple(results),
        tuple(diagnostics),
    )


def _valid_trace_reference(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def map_evaluation_results(
    dataset: EvaluationDataset,
    known_check_ids: tuple[str, ...],
    evaluations: Sequence[EvalResults],
) -> EvaluationAssessment:
    """Normalize native MAF results; item references are not trusted evidence."""
    dataset.validate_for(ORDER_RESOLUTION_RUBRIC, known_check_ids)
    cases_by_query = {case.query: case for case in dataset.cases}
    criteria = {
        criterion.criterion_id: criterion
        for criterion in ORDER_RESOLUTION_RUBRIC.criteria
    }
    expected = tuple(
        sorted(
            (case.case_id, criterion.criterion_id)
            for case in dataset.cases
            for criterion in ORDER_RESOLUTION_RUBRIC.criteria
            if criterion.check_id in case.check_ids
        )
    )
    recorded: dict[tuple[str, str], EvaluationTraceReference] = {}
    invalid_checks: set[str] = set()
    diagnostics: list[str] = []
    all_check_ids = {
        criterion.check_id for criterion in ORDER_RESOLUTION_RUBRIC.criteria
    }
    if not isinstance(evaluations, Sequence) or isinstance(evaluations, (str, bytes)):
        diagnostics.append("MAF did not return an evaluation result sequence.")
        return _assessment(
            dataset,
            tuple(
                CheckEvaluation(
                    check_id,
                    "failed",
                    "MAF returned a malformed evaluation result collection.",
                    (),
                )
                for check_id in sorted(all_check_ids)
            ),
            diagnostics,
        )

    for evaluation in evaluations:
        if not isinstance(evaluation, EvalResults):
            diagnostics.append("MAF returned a malformed evaluation result.")
            invalid_checks.update(all_check_ids)
            continue
        if evaluation.status == "failed":
            diagnostics.append("MAF evaluation failed.")
            invalid_checks.update(all_check_ids)
            continue
        if evaluation.status in {"canceled", "timeout"}:
            continue
        if evaluation.status != "completed":
            diagnostics.append("MAF returned an unknown evaluation status.")
            invalid_checks.update(all_check_ids)
            continue
        if not isinstance(evaluation.items, Sequence) or isinstance(
            evaluation.items, (str, bytes)
        ):
            diagnostics.append("MAF returned a malformed per-item result collection.")
            invalid_checks.update(all_check_ids)
            continue
        for item in evaluation.items:
            if not isinstance(item, EvalItemResult):
                diagnostics.append("MAF returned a malformed per-item result.")
                invalid_checks.update(all_check_ids)
                continue
            case = cases_by_query.get(item.input_text)
            if case is None:
                diagnostics.append(
                    "MAF returned a result with an unknown or malformed input."
                )
                invalid_checks.update(all_check_ids)
                continue
            relevant = [
                criterion
                for criterion in ORDER_RESOLUTION_RUBRIC.criteria
                if criterion.check_id in case.check_ids
            ]
            if not isinstance(item.scores, Sequence) or isinstance(
                item.scores, (str, bytes)
            ):
                diagnostics.append(
                    "MAF returned a malformed evaluator score collection."
                )
                invalid_checks.update(criterion.check_id for criterion in relevant)
                continue
            if item.status in {"error", "errored"}:
                continue
            if item.status not in {"pass", "fail"}:
                diagnostics.append("MAF returned an item with an unknown status.")
                invalid_checks.update(criterion.check_id for criterion in relevant)
                continue
            item_failed_checks: set[str] = set()
            trace_reference = item.response_id or item.item_id
            for score in item.scores:
                if not isinstance(score, EvalScoreResult):
                    diagnostics.append("MAF returned a malformed evaluator score.")
                    invalid_checks.update(criterion.check_id for criterion in relevant)
                    continue
                criterion = criteria.get(score.name)
                if criterion is None:
                    diagnostics.append(
                        "MAF returned a score for an unknown rubric criterion."
                    )
                    invalid_checks.update(criterion.check_id for criterion in relevant)
                    continue
                check_id = criterion.check_id
                key = (case.case_id, criterion.criterion_id)
                if key not in expected:
                    diagnostics.append(
                        "MAF returned a score outside the dataset mapping."
                    )
                    invalid_checks.add(check_id)
                    continue
                if key in recorded:
                    diagnostics.append("MAF returned a duplicate case/evaluator score.")
                    invalid_checks.add(check_id)
                    continue
                if not _is_valid_score(score.score) or (
                    score.passed is not None and not isinstance(score.passed, bool)
                ):
                    diagnostics.append("MAF returned a malformed evaluator score.")
                    invalid_checks.add(check_id)
                    continue
                if not _valid_trace_reference(trace_reference):
                    diagnostics.append("MAF returned an invalid trace reference.")
                    invalid_checks.add(check_id)
                    continue
                if score.passed is False:
                    invalid_checks.add(check_id)
                    item_failed_checks.add(check_id)
                if score.score < criterion.minimum_score:
                    item_failed_checks.add(check_id)
                recorded[key] = EvaluationTraceReference(
                    case.case_id,
                    criterion.criterion_id,
                    float(score.score),
                    criterion.minimum_score,
                    trace_reference,
                )
            if item.status == "fail" and not item_failed_checks:
                invalid_checks.update(criterion.check_id for criterion in relevant)

    results = []
    for check_id in sorted(all_check_ids):
        check_keys = [key for key in expected if criteria[key[1]].check_id == check_id]
        observations = tuple(recorded[key] for key in check_keys if key in recorded)
        below_threshold = any(
            observation.score < criteria[key[1]].minimum_score
            for key in check_keys
            if (observation := recorded.get(key)) is not None
        )
        missing = [key for key in check_keys if key not in recorded]
        if check_id in invalid_checks or below_threshold:
            outcome: Outcome = "failed"
            reason = "A native evaluation result was invalid or below threshold."
        elif missing:
            outcome = "unverified"
            reason = "One or more configured native evaluation results are missing."
        else:
            outcome = "passed"
            reason = "Every configured native result met its declared threshold."
        results.append(CheckEvaluation(check_id, outcome, reason, observations))
    return _assessment(dataset, results, diagnostics)


def unavailable_assessment(
    dataset: EvaluationDataset,
    known_check_ids: tuple[str, ...],
) -> EvaluationAssessment:
    dataset.validate_for(ORDER_RESOLUTION_RUBRIC, known_check_ids)
    return _assessment(
        dataset,
        tuple(
            CheckEvaluation(
                check_id,
                "unverified",
                "No native MAF evaluation result is available.",
                (),
            )
            for check_id in NATIVE_CHECK_IDS
        ),
    )


@dataclass(frozen=True)
class ReadinessState:
    area: str
    check_id: str
    outcome: Outcome
    reason: str


def map_readiness_states(
    assessment: EvaluationAssessment,
) -> tuple[ReadinessState, ...]:
    """Keep deterministic, model, browser, and provenance evidence independent."""
    mapped = {result.check_id: result for result in assessment.check_results}
    native_states = tuple(
        ReadinessState(
            area,
            check_id,
            mapped[check_id].outcome,
            mapped[check_id].reason,
        )
        for area, check_id in (
            ("technical_execution", TECHNICAL_EXECUTION_CHECK_ID),
            ("business_outcome", BUSINESS_OUTCOME_CHECK_ID),
        )
    )
    return native_states + (
        ReadinessState(
            "model_quality",
            MODEL_QUALITY_CHECK_ID,
            "unverified",
            "No real model or provider evaluation evidence is supplied.",
        ),
        ReadinessState(
            "browser_evidence",
            BROWSER_EVIDENCE_CHECK_ID,
            "unverified",
            "No actual browser execution evidence is supplied.",
        ),
        ReadinessState(
            "provenance",
            PROVENANCE_CHECK_ID,
            "unverified",
            "Native item references are not evidence bytes or trusted provenance.",
        ),
    )
