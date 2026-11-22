import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from agent_framework import Agent

from app.extensions.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationObservation,
    EvaluationRubric,
    RubricCriterion,
    evaluate_agent,
    map_observations,
    unavailable_assessment,
)
from examples.evaluation_fixture import (
    SYNTHETIC_DATASET,
    SYNTHETIC_RUBRIC,
)


def selected_contract_check_ids() -> tuple[str, ...]:
    test_file = Path(__file__).resolve()
    copied_contract = (
        test_file.parents[2]
        / "verification"
        / "scenarios"
        / "order-adjustment"
        / "verification-contract.json"
    )
    source_contract = (
        test_file.parents[5] / "scenarios" / "order-adjustment" / "verification-contract.json"
    )
    contract_path = copied_contract if copied_contract.is_file() else source_contract
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    check_ids = [
        check["id"] for requirement in contract["requirements"] for check in requirement["checks"]
    ]
    if not check_ids or len(check_ids) != len(set(check_ids)):
        raise AssertionError("Selected verification contract must have unique check IDs.")
    return tuple(sorted(check_ids))


class EvaluationExtensionTests(unittest.TestCase):
    def setUp(self):
        self.agent = Mock(spec=Agent)
        self.known_check_ids = selected_contract_check_ids()

    def observations(self, explanation=1.0, hint=0.9):
        return (
            EvaluationObservation(
                "synthetic-explanation", "grounded-explanation", explanation, "trace-exp-1"
            ),
            EvaluationObservation("synthetic-hint", "accurate-hint", hint, "trace-hint-1"),
        )

    def test_synthetic_configuration_maps_to_existing_check_results(self):
        result = map_observations(
            SYNTHETIC_DATASET, SYNTHETIC_RUBRIC, self.known_check_ids, self.observations()
        )
        self.assertEqual(result.outcome, "passed")
        checks = {item.check_id: item for item in result.check_results}
        configured_check_ids = {
            check_id for case in SYNTHETIC_DATASET.cases for check_id in case.check_ids
        }
        self.assertTrue(configured_check_ids.issubset(self.known_check_ids))
        self.assertEqual(set(checks), configured_check_ids)
        self.assertEqual(
            checks[SYNTHETIC_RUBRIC.criteria[0].check_id].observations[0].case_id,
            "synthetic-explanation",
        )
        self.assertEqual(
            checks[SYNTHETIC_RUBRIC.criteria[0].check_id].observations[0].criterion_id,
            "grounded-explanation",
        )
        explanation = checks[SYNTHETIC_RUBRIC.criteria[0].check_id].observations[0]
        hint = checks[SYNTHETIC_RUBRIC.criteria[1].check_id].observations[0]
        self.assertEqual(explanation.score, 1.0)
        self.assertEqual(explanation.minimum_score, 1.0)
        self.assertEqual(explanation.reference, "trace-exp-1")
        self.assertEqual(hint.reference, "trace-hint-1")

    def test_threshold_edges_are_inclusive_and_below_threshold_fails(self):
        edge = map_observations(
            SYNTHETIC_DATASET,
            SYNTHETIC_RUBRIC,
            self.known_check_ids,
            self.observations(1.0, 0.9),
        )
        below = map_observations(
            SYNTHETIC_DATASET,
            SYNTHETIC_RUBRIC,
            self.known_check_ids,
            self.observations(0.99, 0.89),
        )
        self.assertEqual(edge.outcome, "passed")
        self.assertEqual(below.outcome, "failed")
        self.assertTrue(all(item.outcome == "failed" for item in below.check_results))

    def test_unavailable_evaluator_is_unverified_and_does_not_invoke_agent(self):
        result = asyncio.run(
            evaluate_agent(
                self.agent,
                SYNTHETIC_DATASET,
                SYNTHETIC_RUBRIC,
                self.known_check_ids,
                None,
            )
        )
        self.assertEqual(result.outcome, "unverified")
        self.assertTrue(all(item.outcome == "unverified" for item in result.check_results))

    def test_failed_evaluator_propagates_without_fabricating_a_result(self):
        for error in ("provider unavailable", "tool failed"):
            with self.subTest(error=error):
                evaluator = Mock()
                evaluator.evaluate = AsyncMock(side_effect=RuntimeError(error))
                with self.assertRaisesRegex(RuntimeError, error):
                    asyncio.run(
                        evaluate_agent(
                            self.agent,
                            SYNTHETIC_DATASET,
                            SYNTHETIC_RUBRIC,
                            self.known_check_ids,
                            evaluator,
                        )
                    )
                evaluator.evaluate.assert_awaited_once_with(
                    self.agent, SYNTHETIC_DATASET, SYNTHETIC_RUBRIC
                )

    def test_missing_observations_remain_unverified(self):
        result = map_observations(
            SYNTHETIC_DATASET,
            SYNTHETIC_RUBRIC,
            self.known_check_ids,
            self.observations()[:1],
        )
        checks = {item.check_id: item.outcome for item in result.check_results}
        self.assertEqual(checks[SYNTHETIC_RUBRIC.criteria[0].check_id], "passed")
        self.assertEqual(checks[SYNTHETIC_RUBRIC.criteria[1].check_id], "unverified")
        self.assertEqual(result.outcome, "unverified")

    def test_unknown_and_duplicate_observations_cannot_pass(self):
        observations = self.observations()
        duplicate = map_observations(
            SYNTHETIC_DATASET,
            SYNTHETIC_RUBRIC,
            self.known_check_ids,
            (*observations, observations[0]),
        )
        unknown = map_observations(
            SYNTHETIC_DATASET,
            SYNTHETIC_RUBRIC,
            self.known_check_ids,
            (
                observations[1],
                EvaluationObservation("unknown-case", "grounded-explanation", 1.0, "trace"),
            ),
        )
        self.assertEqual(duplicate.outcome, "failed")
        self.assertEqual(unknown.outcome, "failed")
        self.assertEqual(
            {item.check_id: item.outcome for item in duplicate.check_results}[
                SYNTHETIC_RUBRIC.criteria[0].check_id
            ],
            "failed",
        )

    def test_unknown_criterion_and_malformed_evaluator_output_fail(self):
        unknown = map_observations(
            SYNTHETIC_DATASET,
            SYNTHETIC_RUBRIC,
            self.known_check_ids,
            (
                EvaluationObservation("synthetic-explanation", "unknown-criterion", 1.0, "trace"),
                self.observations()[1],
            ),
        )
        malformed = map_observations(
            SYNTHETIC_DATASET, SYNTHETIC_RUBRIC, self.known_check_ids, (None,)
        )
        invalid_collection = map_observations(
            SYNTHETIC_DATASET, SYNTHETIC_RUBRIC, self.known_check_ids, None
        )
        self.assertEqual(unknown.outcome, "failed")
        self.assertEqual(malformed.outcome, "failed")
        self.assertEqual(invalid_collection.outcome, "failed")

    def test_malformed_scores_and_trace_references_fail_closed(self):
        invalid_score = self.observations(float("nan"), 0.9)
        invalid_trace = (
            invalid_score[0],
            EvaluationObservation("synthetic-hint", "accurate-hint", 0.9, " "),
        )
        result = map_observations(
            SYNTHETIC_DATASET, SYNTHETIC_RUBRIC, self.known_check_ids, invalid_trace
        )
        self.assertEqual(result.outcome, "failed")

    def test_malformed_threshold_is_rejected_before_evaluator_runs(self):
        evaluator = Mock()
        evaluator.evaluate = AsyncMock()
        check_id = SYNTHETIC_RUBRIC.criteria[0].check_id
        for threshold in (float("nan"), float("inf"), -0.01, 1.01, True):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                RubricCriterion("criterion", check_id, threshold)
        self.assertEqual(evaluator.evaluate.await_count, 0)

    def test_oversized_integer_threshold_and_score_fail_safely(self):
        check_id = SYNTHETIC_RUBRIC.criteria[0].check_id
        with self.assertRaisesRegex(ValueError, "finite numbers"):
            RubricCriterion("criterion", check_id, 10**1000)
        invalid = (
            EvaluationObservation(
                "synthetic-explanation", "grounded-explanation", 10**1000, "synthetic-trace"
            ),
            self.observations()[1],
        )
        result = map_observations(
            SYNTHETIC_DATASET, SYNTHETIC_RUBRIC, self.known_check_ids, invalid
        )
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.check_results[0].outcome, "failed")

    def test_dataset_rubric_check_mapping_must_be_explicit_and_complete(self):
        rubric = EvaluationRubric(
            "incomplete",
            "v1",
            (RubricCriterion("criterion", "CHECK-UNKNOWN", 0.5),),
        )
        with self.assertRaisesRegex(ValueError, "must match"):
            rubric.validate_for(SYNTHETIC_DATASET, self.known_check_ids)

    def test_multiple_criteria_produce_one_check_result_with_each_trace(self):
        explanation_check_id = SYNTHETIC_RUBRIC.criteria[0].check_id
        hint_check_id = SYNTHETIC_RUBRIC.criteria[1].check_id
        rubric = EvaluationRubric(
            "two-explanation-criteria",
            "v1",
            (
                RubricCriterion("grounded", explanation_check_id, 0.8),
                RubricCriterion("safe", explanation_check_id, 0.9),
                RubricCriterion("accurate-hint", hint_check_id, 0.9),
            ),
        )
        observations = (
            EvaluationObservation("synthetic-explanation", "grounded", 0.95, "trace-grounded"),
            EvaluationObservation("synthetic-explanation", "safe", 0.9, "trace-safe"),
            EvaluationObservation("synthetic-hint", "accurate-hint", 0.9, "trace-hint"),
        )
        result = map_observations(SYNTHETIC_DATASET, rubric, self.known_check_ids, observations)
        explanation = [
            item for item in result.check_results if item.check_id == explanation_check_id
        ]
        self.assertEqual(len(explanation), 1)
        self.assertEqual(
            {item.criterion_id for item in explanation[0].observations}, {"grounded", "safe"}
        )
        unavailable = unavailable_assessment(SYNTHETIC_DATASET, rubric, self.known_check_ids)
        self.assertEqual(len(unavailable.check_results), 2)

    def test_unknown_matching_dataset_and_rubric_check_is_rejected_before_evaluation(self):
        dataset = EvaluationDataset(
            "unknown-check", "v1", (EvaluationCase("case", {}, ("CHECK-NOT-IN-CONTRACT",)),)
        )
        rubric = EvaluationRubric(
            "unknown-check",
            "v1",
            (RubricCriterion("criterion", "CHECK-NOT-IN-CONTRACT", 0.5),),
        )
        evaluator = Mock()
        evaluator.evaluate = AsyncMock()

        with self.assertRaisesRegex(ValueError, "outside the selected readiness contract"):
            asyncio.run(
                evaluate_agent(
                    self.agent,
                    dataset,
                    rubric,
                    self.known_check_ids,
                    evaluator,
                )
            )
        evaluator.evaluate.assert_not_awaited()
        for assessment in (
            lambda: map_observations(
                dataset,
                rubric,
                self.known_check_ids,
                (EvaluationObservation("case", "criterion", 1.0, "synthetic-trace"),),
            ),
            lambda: unavailable_assessment(dataset, rubric, self.known_check_ids),
        ):
            with self.assertRaisesRegex(ValueError, "outside the selected readiness contract"):
                assessment()

    def test_malformed_or_duplicate_known_checks_are_rejected_before_evaluation(self):
        evaluator = Mock()
        evaluator.evaluate = AsyncMock()
        duplicate_check_id = self.known_check_ids[0]
        for known_checks in ((), (duplicate_check_id, duplicate_check_id), (" ",)):
            with self.subTest(known_checks=known_checks), self.assertRaises(ValueError):
                asyncio.run(
                    evaluate_agent(
                        self.agent,
                        SYNTHETIC_DATASET,
                        SYNTHETIC_RUBRIC,
                        known_checks,
                        evaluator,
                    )
                )
        evaluator.evaluate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
