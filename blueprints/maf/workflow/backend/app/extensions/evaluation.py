"""Application-owned evaluation configuration and per-check result mapping."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal, Protocol

from agent_framework import Agent


Outcome = Literal["passed", "failed", "unverified"]


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and whitespace-trimmed.")


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    inputs: Mapping[str, object]
    check_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.case_id, "Evaluation case IDs")
        if not isinstance(self.inputs, Mapping):
            raise ValueError("Evaluation case inputs must be a mapping.")
        if not self.check_ids or len(self.check_ids) != len(set(self.check_ids)):
            raise ValueError("Evaluation cases must map to unique readiness check IDs.")
        for check_id in self.check_ids:
            _require_text(check_id, "Readiness check IDs")


@dataclass(frozen=True)
class EvaluationDataset:
    dataset_id: str
    version: str
    cases: tuple[EvaluationCase, ...]

    def __post_init__(self) -> None:
        _require_text(self.dataset_id, "Evaluation dataset IDs")
        _require_text(self.version, "Evaluation dataset versions")
        if not self.cases or len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("Evaluation datasets must contain cases with unique IDs.")


@dataclass(frozen=True)
class RubricCriterion:
    criterion_id: str
    check_id: str
    minimum_score: float

    def __post_init__(self) -> None:
        _require_text(self.criterion_id, "Rubric criterion IDs")
        _require_text(self.check_id, "Readiness check IDs")
        if (
            isinstance(self.minimum_score, bool)
            or not isinstance(self.minimum_score, (int, float))
            or not isfinite(self.minimum_score)
            or not 0 <= self.minimum_score <= 1
        ):
            raise ValueError("Rubric minimum scores must be finite numbers from 0 to 1.")


@dataclass(frozen=True)
class EvaluationRubric:
    rubric_id: str
    version: str
    criteria: tuple[RubricCriterion, ...]

    def __post_init__(self) -> None:
        _require_text(self.rubric_id, "Evaluation rubric IDs")
        _require_text(self.version, "Evaluation rubric versions")
        if not self.criteria or len({item.criterion_id for item in self.criteria}) != len(
            self.criteria
        ):
            raise ValueError("Evaluation rubrics must contain criteria with unique IDs.")

    def validate_for(self, dataset: EvaluationDataset) -> None:
        case_checks = {check_id for case in dataset.cases for check_id in case.check_ids}
        criterion_checks = {item.check_id for item in self.criteria}
        if case_checks != criterion_checks:
            raise ValueError("Dataset check IDs must match rubric readiness check IDs.")
        for criterion in self.criteria:
            if not any(criterion.check_id in case.check_ids for case in dataset.cases):
                raise ValueError(f"Rubric check {criterion.check_id!r} has no dataset cases.")


@dataclass(frozen=True)
class EvaluationObservation:
    case_id: str
    criterion_id: str
    score: float
    trace_reference: str


class AgentEvaluator(Protocol):
    async def evaluate(
        self, agent: Agent, dataset: EvaluationDataset, rubric: EvaluationRubric
    ) -> Sequence[EvaluationObservation]: ...


@dataclass(frozen=True)
class EvaluationTraceReference:
    case_id: str
    criterion_id: str
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


def unavailable_assessment(
    dataset: EvaluationDataset, rubric: EvaluationRubric
) -> EvaluationAssessment:
    rubric.validate_for(dataset)
    check_ids = sorted({criterion.check_id for criterion in rubric.criteria})
    return _assessment(
        dataset,
        rubric,
        tuple(
            CheckEvaluation(
                check_id=check_id,
                outcome="unverified",
                reason="No application-owned evaluator is configured.",
                observations=(),
            )
            for check_id in check_ids
        ),
    )


def map_observations(
    dataset: EvaluationDataset,
    rubric: EvaluationRubric,
    observations: Sequence[EvaluationObservation],
) -> EvaluationAssessment:
    """Adjudicate evaluator observations; references are not evidence or provenance."""
    rubric.validate_for(dataset)
    cases = {case.case_id: case for case in dataset.cases}
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
    recorded: dict[tuple[str, str], EvaluationObservation] = {}
    invalid_checks: set[str] = set()
    diagnostics: list[str] = []
    all_check_ids = {criterion.check_id for criterion in rubric.criteria}
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        diagnostics.append("Evaluator did not return an observation sequence.")
        return _assessment(
            dataset,
            rubric,
            tuple(
                CheckEvaluation(
                    check_id=check_id,
                    outcome="failed",
                    reason="Evaluator returned a malformed observation collection.",
                    observations=(),
                )
                for check_id in sorted(all_check_ids)
            ),
            diagnostics,
        )

    for observation in observations:
        if not isinstance(observation, EvaluationObservation):
            diagnostics.append("Evaluator returned a malformed observation.")
            invalid_checks.update(all_check_ids)
            continue
        if (
            not isinstance(observation.case_id, str)
            or not observation.case_id
            or not isinstance(observation.criterion_id, str)
            or not observation.criterion_id
        ):
            diagnostics.append("Evaluator returned an observation with malformed IDs.")
            invalid_checks.update(all_check_ids)
            continue
        case = cases.get(observation.case_id)
        criterion = criteria.get(observation.criterion_id)
        if case is None:
            diagnostics.append(f"Evaluator returned unknown case ID {observation.case_id!r}.")
            invalid_checks.update(all_check_ids)
            continue
        if criterion is None:
            diagnostics.append(
                f"Evaluator returned unknown criterion ID {observation.criterion_id!r}."
            )
            invalid_checks.update(case.check_ids)
            continue
        check_id = criterion.check_id
        key = (observation.case_id, observation.criterion_id)
        if key not in expected:
            diagnostics.append("Evaluator returned an observation outside the dataset mapping.")
            invalid_checks.add(check_id)
            continue
        if key in recorded:
            diagnostics.append(
                f"Evaluator returned duplicate observation for {key[0]!r}/{key[1]!r}."
            )
            invalid_checks.add(check_id)
            continue
        recorded[key] = observation
        if (
            isinstance(observation.score, bool)
            or not isinstance(observation.score, (int, float))
            or not isfinite(observation.score)
            or not 0 <= observation.score <= 1
        ):
            diagnostics.append(f"Evaluator returned malformed score for {key[0]!r}/{key[1]!r}.")
            invalid_checks.add(check_id)
        if (
            not isinstance(observation.trace_reference, str)
            or not observation.trace_reference
            or observation.trace_reference != observation.trace_reference.strip()
        ):
            diagnostics.append(
                f"Evaluator returned invalid trace reference for {key[0]!r}/{key[1]!r}."
            )
            invalid_checks.add(check_id)

    results = []
    for check_id in sorted(all_check_ids):
        check_keys = [key for key in expected if criteria[key[1]].check_id == check_id]
        check_observations = [recorded[key] for key in check_keys if key in recorded]
        traces = tuple(
            EvaluationTraceReference(
                observation.case_id, observation.criterion_id, observation.trace_reference
            )
            for observation in check_observations
            if isinstance(observation.trace_reference, str)
            and observation.trace_reference
            and observation.trace_reference == observation.trace_reference.strip()
        )
        below_threshold = any(
            observation.score < criteria[key[1]].minimum_score
            for key in check_keys
            if (observation := recorded.get(key)) is not None
            and isinstance(observation.score, (int, float))
            and not isinstance(observation.score, bool)
            and isfinite(observation.score)
            and 0 <= observation.score <= 1
        )
        missing = [key for key in check_keys if key not in recorded]
        if check_id in invalid_checks or below_threshold:
            outcome: Outcome = "failed"
            reason = "An evaluation observation was invalid or below its configured threshold."
        elif missing:
            outcome = "unverified"
            reason = "One or more configured evaluation observations are missing."
        else:
            outcome = "passed"
            reason = "Every configured observation met its rubric threshold."
        results.append(CheckEvaluation(check_id, outcome, reason, traces))
    return _assessment(dataset, rubric, results, diagnostics)


async def evaluate_agent(
    agent: Agent,
    dataset: EvaluationDataset,
    rubric: EvaluationRubric,
    evaluator: AgentEvaluator | None,
) -> EvaluationAssessment:
    """Run an application-owned evaluator; provider errors propagate without fallback."""
    rubric.validate_for(dataset)
    if evaluator is None:
        return unavailable_assessment(dataset, rubric)
    observations = await evaluator.evaluate(agent, dataset, rubric)
    return map_observations(dataset, rubric, observations)
