"""Application-owned evaluation configuration and per-check result mapping."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from agent_framework import EvalItemResult, EvalResults, EvalScoreResult


Outcome = Literal["passed", "failed", "unverified"]


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and whitespace-trimmed.")


def _validate_known_check_ids(known_check_ids: tuple[str, ...]) -> set[str]:
    if not isinstance(known_check_ids, tuple) or not known_check_ids:
        raise ValueError("Known readiness check IDs must be a non-empty tuple.")
    for check_id in known_check_ids:
        _require_text(check_id, "Known readiness check IDs")
    if len(known_check_ids) != len(set(known_check_ids)):
        raise ValueError("Known readiness check IDs must be unique.")
    return set(known_check_ids)


def _is_valid_score(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, int):
        return 0 <= value <= 1
    return isfinite(value) and 0 <= value <= 1


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    inputs: Mapping[str, object]
    check_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.case_id, "Evaluation case IDs")
        if not isinstance(self.inputs, Mapping):
            raise ValueError("Evaluation case inputs must be a mapping.")
        if not isinstance(self.check_ids, tuple) or not self.check_ids:
            raise ValueError("Evaluation cases must map to unique readiness check IDs.")
        for check_id in self.check_ids:
            _require_text(check_id, "Readiness check IDs")
        if len(self.check_ids) != len(set(self.check_ids)):
            raise ValueError("Evaluation cases must map to unique readiness check IDs.")


@dataclass(frozen=True)
class EvaluationDataset:
    dataset_id: str
    version: str
    cases: tuple[EvaluationCase, ...]

    def __post_init__(self) -> None:
        _require_text(self.dataset_id, "Evaluation dataset IDs")
        _require_text(self.version, "Evaluation dataset versions")
        if (
            not isinstance(self.cases, tuple)
            or not self.cases
            or any(not isinstance(case, EvaluationCase) for case in self.cases)
        ):
            raise ValueError("Evaluation datasets must contain cases with unique IDs.")
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Evaluation datasets must contain cases with unique IDs.")


@dataclass(frozen=True)
class RubricCriterion:
    criterion_id: str
    check_id: str
    minimum_score: float

    def __post_init__(self) -> None:
        _require_text(self.criterion_id, "Rubric criterion IDs")
        _require_text(self.check_id, "Readiness check IDs")
        if not _is_valid_score(self.minimum_score):
            raise ValueError("Rubric minimum scores must be finite numbers from 0 to 1.")


@dataclass(frozen=True)
class EvaluationRubric:
    rubric_id: str
    version: str
    criteria: tuple[RubricCriterion, ...]

    def __post_init__(self) -> None:
        _require_text(self.rubric_id, "Evaluation rubric IDs")
        _require_text(self.version, "Evaluation rubric versions")
        if (
            not isinstance(self.criteria, tuple)
            or not self.criteria
            or any(not isinstance(item, RubricCriterion) for item in self.criteria)
        ):
            raise ValueError("Evaluation rubrics must contain criteria with unique IDs.")
        if len({item.criterion_id for item in self.criteria}) != len(self.criteria):
            raise ValueError("Evaluation rubrics must contain criteria with unique IDs.")

    def validate_for(self, dataset: EvaluationDataset, known_check_ids: tuple[str, ...]) -> None:
        known_checks = _validate_known_check_ids(known_check_ids)
        case_checks = {check_id for case in dataset.cases for check_id in case.check_ids}
        criterion_checks = {item.check_id for item in self.criteria}
        if case_checks != criterion_checks:
            raise ValueError("Dataset check IDs must match rubric readiness check IDs.")
        unknown_checks = case_checks - known_checks
        if unknown_checks:
            raise ValueError(
                f"Dataset and rubric contain checks outside the selected readiness contract: "
                f"{', '.join(sorted(unknown_checks))}."
            )
        for criterion in self.criteria:
            if not any(criterion.check_id in case.check_ids for case in dataset.cases):
                raise ValueError(f"Rubric check {criterion.check_id!r} has no dataset cases.")
        queries = []
        for case in dataset.cases:
            query = case.inputs.get("query")
            _require_text(query, "Evaluation case query")
            queries.append(query)
        if len(queries) != len(set(queries)):
            raise ValueError("Evaluation case queries must be unique for native result mapping.")


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
        if self.diagnostics or any(result.outcome == "failed" for result in self.check_results):
            return "failed"
        if any(result.outcome == "unverified" for result in self.check_results):
            return "unverified"
        return "passed"


def _assessment(
    dataset: EvaluationDataset,
    rubric: EvaluationRubric,
    results: Sequence[CheckEvaluation],
    diagnostics: Sequence[str] = (),
) -> EvaluationAssessment:
    return EvaluationAssessment(
        dataset.dataset_id,
        dataset.version,
        rubric.rubric_id,
        rubric.version,
        tuple(results),
        tuple(diagnostics),
    )


def _valid_score(value: object) -> bool:
    return _is_valid_score(value)


def _valid_trace_reference(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def map_evaluation_results(
    dataset: EvaluationDataset,
    rubric: EvaluationRubric,
    known_check_ids: tuple[str, ...],
    evaluations: Sequence[EvalResults],
) -> EvaluationAssessment:
    """Normalize native MAF per-item results; references are not evidence or provenance."""
    rubric.validate_for(dataset, known_check_ids)
    cases_by_query = {case.inputs["query"]: case for case in dataset.cases}
    criteria = {criterion.criterion_id: criterion for criterion in rubric.criteria}
    expected = tuple(
        sorted(
            {
                (case.case_id, criterion.criterion_id)
                for case in dataset.cases
                for criterion in rubric.criteria
                if criterion.check_id in case.check_ids
            }
        )
    )
    recorded: dict[tuple[str, str], EvaluationTraceReference] = {}
    invalid_checks: set[str] = set()
    diagnostics: list[str] = []
    all_check_ids = {criterion.check_id for criterion in rubric.criteria}
    if not isinstance(evaluations, Sequence) or isinstance(evaluations, (str, bytes)):
        diagnostics.append("MAF did not return an evaluation result sequence.")
        return _assessment(
            dataset,
            rubric,
            tuple(
                CheckEvaluation(
                    check_id=check_id,
                    outcome="failed",
                    reason="MAF returned a malformed evaluation result collection.",
                    observations=(),
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
        if not isinstance(evaluation.items, Sequence) or isinstance(evaluation.items, (str, bytes)):
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
                diagnostics.append("MAF returned a result with an unknown or malformed input.")
                invalid_checks.update(all_check_ids)
                continue
            relevant_criteria = [
                criterion for criterion in rubric.criteria if criterion.check_id in case.check_ids
            ]
            if not isinstance(item.scores, Sequence) or isinstance(item.scores, (str, bytes)):
                diagnostics.append("MAF returned a malformed evaluator score collection.")
                invalid_checks.update(criterion.check_id for criterion in relevant_criteria)
                continue
            if item.status == "fail":
                invalid_checks.update(criterion.check_id for criterion in relevant_criteria)
            elif item.status in {"error", "errored"}:
                continue
            elif item.status != "pass":
                diagnostics.append("MAF returned an item with an unknown status.")
                invalid_checks.update(criterion.check_id for criterion in relevant_criteria)
                continue
            trace_reference = item.response_id or item.item_id
            for score in item.scores:
                if not isinstance(score, EvalScoreResult):
                    diagnostics.append("MAF returned a malformed evaluator score.")
                    invalid_checks.update(criterion.check_id for criterion in relevant_criteria)
                    continue
                criterion = criteria.get(score.name)
                if criterion is None:
                    diagnostics.append("MAF returned a score for an unknown rubric criterion.")
                    invalid_checks.update(criterion.check_id for criterion in relevant_criteria)
                    continue
                check_id = criterion.check_id
                key = (case.case_id, criterion.criterion_id)
                if key not in expected:
                    if check_id not in case.check_ids:
                        continue
                    diagnostics.append("MAF returned a score outside the dataset mapping.")
                    invalid_checks.add(check_id)
                    continue
                if key in recorded:
                    diagnostics.append("MAF returned a duplicate case/evaluator score.")
                    invalid_checks.add(check_id)
                    continue
                if not _valid_score(score.score) or (
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
                recorded[key] = EvaluationTraceReference(
                    case.case_id,
                    criterion.criterion_id,
                    float(score.score),
                    criterion.minimum_score,
                    trace_reference,
                )

    results = []
    for check_id in sorted(all_check_ids):
        check_keys = [key for key in expected if criteria[key[1]].check_id == check_id]
        traces = tuple(recorded[key] for key in check_keys if key in recorded)
        below_threshold = any(
            trace.score < criteria[key[1]].minimum_score
            for key in check_keys
            if (trace := recorded.get(key)) is not None
        )
        missing = [key for key in check_keys if key not in recorded]
        if check_id in invalid_checks or below_threshold:
            outcome: Outcome = "failed"
            reason = "A native evaluation result was invalid or below its configured threshold."
        elif missing:
            outcome = "unverified"
            reason = "One or more configured native evaluation results are missing."
        else:
            outcome = "passed"
            reason = "Every configured native result met its rubric threshold."
        results.append(CheckEvaluation(check_id, outcome, reason, traces))
    return _assessment(dataset, rubric, results, diagnostics)


def unavailable_assessment(
    dataset: EvaluationDataset,
    rubric: EvaluationRubric,
    known_check_ids: tuple[str, ...],
) -> EvaluationAssessment:
    rubric.validate_for(dataset, known_check_ids)
    check_ids = sorted({criterion.check_id for criterion in rubric.criteria})
    return _assessment(
        dataset,
        rubric,
        tuple(
            CheckEvaluation(
                check_id=check_id,
                outcome="unverified",
                reason="No native MAF evaluation result is available.",
                observations=(),
            )
            for check_id in check_ids
        ),
    )
