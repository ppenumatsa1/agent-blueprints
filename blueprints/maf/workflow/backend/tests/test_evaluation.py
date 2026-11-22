import asyncio
import importlib
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_framework import (
    AgentResponse,
    EvalItemResult,
    EvalResults,
    EvalScoreResult,
    LocalEvaluator,
    Message,
    evaluate_agent as maf_evaluate_agent,
    evaluator,
)

from app.extensions.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationRubric,
    RealProviderEvaluationSettings,
    RubricCriterion,
    load_real_provider_evaluator,
    load_real_provider_results,
    map_evaluation_results,
    unavailable_assessment,
)
from examples.evaluation_fixture import SYNTHETIC_DATASET, SYNTHETIC_RUBRIC


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


@evaluator(name="grounded-explanation")
def deterministic_explanation_check(response: str) -> bool:
    return "facts" in response


@evaluator(name="accurate-hint")
def deterministic_hint_check(response: str) -> bool:
    return "hint" in response


@evaluator(name="raises")
async def unavailable_check(response: str) -> float:
    raise RuntimeError("native evaluator failed")


class EvaluationExtensionTests(unittest.TestCase):
    def setUp(self):
        self.known_check_ids = selected_contract_check_ids()

    def native_results(self, explanation="facts hint", hint="facts hint"):
        responses = [
            AgentResponse(messages=[Message(role="assistant", contents=[response])])
            for response in (explanation, hint)
        ]
        return asyncio.run(
            maf_evaluate_agent(
                queries=[case.inputs["query"] for case in SYNTHETIC_DATASET.cases],
                responses=responses,
                evaluators=LocalEvaluator(
                    deterministic_explanation_check,
                    deterministic_hint_check,
                ),
                eval_name="synthetic-local-contract-test",
            )
        )

    def assess(self, results):
        return map_evaluation_results(
            SYNTHETIC_DATASET, SYNTHETIC_RUBRIC, self.known_check_ids, results
        )

    def test_native_local_results_map_to_selected_readiness_checks(self):
        result = self.assess(self.native_results())
        self.assertEqual(result.outcome, "passed")
        checks = {item.check_id: item for item in result.check_results}
        configured_check_ids = {
            check_id for case in SYNTHETIC_DATASET.cases for check_id in case.check_ids
        }
        self.assertTrue(configured_check_ids.issubset(self.known_check_ids))
        self.assertEqual(set(checks), configured_check_ids)
        explanation = checks[SYNTHETIC_RUBRIC.criteria[0].check_id].observations[0]
        hint = checks[SYNTHETIC_RUBRIC.criteria[1].check_id].observations[0]
        self.assertEqual(explanation.case_id, SYNTHETIC_DATASET.cases[0].case_id)
        self.assertEqual(explanation.criterion_id, "grounded-explanation")
        self.assertEqual(explanation.score, 1.0)
        self.assertEqual(explanation.minimum_score, 1.0)
        self.assertTrue(explanation.reference)
        self.assertEqual(
            tuple(item.case_id for item in checks["CHECK-HINT"].observations),
            tuple(case.case_id for case in SYNTHETIC_DATASET.cases),
        )
        self.assertEqual(hint.criterion_id, "accurate-hint")
        self.assertEqual(hint.score, 1.0)

    def test_configured_threshold_edges_are_inclusive_and_below_fails(self):
        edge_results = self.native_results()
        for item in edge_results[0].items:
            for score in item.scores:
                score.score = 1.0 if score.name == "grounded-explanation" else 0.9
        edge = self.assess(edge_results)
        below_results = self.native_results()
        for item in below_results[0].items:
            for score in item.scores:
                if score.name == "grounded-explanation":
                    score.score = 0.99
                elif score.name == "accurate-hint":
                    score.score = 0.89
        below = self.assess(below_results)
        self.assertEqual(edge.outcome, "passed")
        self.assertEqual(below.outcome, "failed")
        self.assertTrue(all(item.outcome == "failed" for item in below.check_results))

    def test_unavailable_native_results_remain_unverified(self):
        unavailable = unavailable_assessment(
            SYNTHETIC_DATASET, SYNTHETIC_RUBRIC, self.known_check_ids
        )
        missing = self.assess(())
        self.assertEqual(unavailable.outcome, "unverified")
        self.assertEqual(missing.outcome, "unverified")
        self.assertTrue(all(item.outcome == "unverified" for item in missing.check_results))

    def test_native_evaluator_exceptions_propagate(self):
        responses = [
            AgentResponse(messages=[Message(role="assistant", contents=["synthetic"])])
            for _case in SYNTHETIC_DATASET.cases
        ]
        with self.assertRaisesRegex(RuntimeError, "native evaluator failed"):
            asyncio.run(
                maf_evaluate_agent(
                    queries=[case.inputs["query"] for case in SYNTHETIC_DATASET.cases],
                    responses=responses,
                    evaluators=LocalEvaluator(unavailable_check),
                )
            )

    def test_failed_native_scores_and_oversized_scores_fail_closed(self):
        results = self.native_results()
        item = results[0].items[0]
        item.scores[0].passed = False
        failed = self.assess(results)
        self.assertEqual(failed.outcome, "failed")

        oversized = EvalResults(
            provider="synthetic",
            items=[
                EvalItemResult(
                    item_id="synthetic-item",
                    status="pass",
                    input_text=SYNTHETIC_DATASET.cases[0].inputs["query"],
                    scores=[
                        EvalScoreResult(
                            name="grounded-explanation",
                            score=10**1000,
                            passed=True,
                        )
                    ],
                )
            ],
        )
        malformed = self.assess((oversized,))
        self.assertEqual(malformed.outcome, "failed")

    def test_native_item_failure_maps_to_the_failed_criterion(self):
        result = self.assess(self.native_results("hint", "hint"))
        checks = {item.check_id: item for item in result.check_results}
        self.assertEqual(checks["CHECK-EXPLANATION"].outcome, "failed")
        self.assertEqual(checks["CHECK-HINT"].outcome, "passed")

    def test_native_score_for_unmapped_case_check_fails(self):
        dataset = EvaluationDataset(
            "strict-mapping",
            "v1",
            (
                EvaluationCase(
                    "explanation-only",
                    {"query": "synthetic explanation"},
                    ("CHECK-EXPLANATION",),
                ),
                EvaluationCase(
                    "hint-only",
                    {"query": "synthetic hint"},
                    ("CHECK-HINT",),
                ),
            ),
        )
        extra_score = EvalResults(
            provider="synthetic",
            items=[
                EvalItemResult(
                    item_id="extra-score",
                    status="pass",
                    input_text="synthetic explanation",
                    scores=[
                        EvalScoreResult(
                            name="accurate-hint",
                            score=1.0,
                            passed=True,
                        )
                    ],
                )
            ],
        )
        mapped = map_evaluation_results(
            dataset, SYNTHETIC_RUBRIC, self.known_check_ids, (extra_score,)
        )
        self.assertEqual(mapped.outcome, "failed")
        self.assertTrue(mapped.diagnostics)

    def test_unknown_and_duplicate_native_results_cannot_pass(self):
        results = self.native_results()
        unknown = EvalResults(
            provider="synthetic",
            items=[
                EvalItemResult(
                    item_id="unknown-item",
                    status="pass",
                    input_text="not in the configured dataset",
                    scores=[EvalScoreResult(name="grounded-explanation", score=1.0, passed=True)],
                )
            ],
        )
        unknown_criterion = EvalResults(
            provider="synthetic",
            items=[
                EvalItemResult(
                    item_id="unknown-criterion-item",
                    status="pass",
                    input_text=SYNTHETIC_DATASET.cases[0].inputs["query"],
                    scores=[EvalScoreResult(name="not-in-rubric", score=1.0, passed=True)],
                )
            ],
        )
        duplicate = EvalResults(
            provider="synthetic",
            items=[*results[0].items, results[0].items[0]],
        )
        self.assertEqual(self.assess((unknown, *results)).outcome, "failed")
        self.assertEqual(self.assess((unknown_criterion, *results)).outcome, "failed")
        self.assertEqual(self.assess((duplicate,)).outcome, "failed")

    def test_malformed_native_results_fail_closed(self):
        malformed = self.assess((None,))
        invalid_collection = map_evaluation_results(
            SYNTHETIC_DATASET, SYNTHETIC_RUBRIC, self.known_check_ids, None
        )
        malformed_items = EvalResults(provider="synthetic")
        malformed_items.items = None
        malformed_scores = self.native_results()
        malformed_scores[0].items[0].scores = None
        self.assertEqual(malformed.outcome, "failed")
        self.assertEqual(invalid_collection.outcome, "failed")
        self.assertEqual(self.assess((malformed_items,)).outcome, "failed")
        self.assertEqual(self.assess(malformed_scores).outcome, "failed")

    def test_native_run_failures_fail_and_cancellation_remains_unverified(self):
        failed = EvalResults(provider="synthetic", status="failed")
        canceled = EvalResults(provider="synthetic", status="canceled")
        unknown_status = EvalResults(provider="synthetic", status="unexpected")
        self.assertEqual(self.assess((failed,)).outcome, "failed")
        self.assertEqual(self.assess((canceled,)).outcome, "unverified")
        self.assertEqual(self.assess((unknown_status,)).outcome, "failed")

    def test_oversized_thresholds_reject_before_native_evaluation(self):
        check_id = SYNTHETIC_RUBRIC.criteria[0].check_id
        for threshold in (float("nan"), float("inf"), -0.01, 1.01, True, 10**1000):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                RubricCriterion("criterion", check_id, threshold)

    def test_dataset_rubric_identity_is_checked_against_contract(self):
        dataset = EvaluationDataset(
            "unknown-check",
            "v1",
            (EvaluationCase("case", {"query": "synthetic query"}, ("CHECK-NOT-IN-CONTRACT",)),),
        )
        rubric = EvaluationRubric(
            "unknown-check",
            "v1",
            (RubricCriterion("criterion", "CHECK-NOT-IN-CONTRACT", 0.5),),
        )
        with self.assertRaisesRegex(ValueError, "outside the selected readiness contract"):
            rubric.validate_for(dataset, self.known_check_ids)
        with self.assertRaisesRegex(ValueError, "outside the selected readiness contract"):
            map_evaluation_results(dataset, rubric, self.known_check_ids, ())
        with self.assertRaisesRegex(ValueError, "outside the selected readiness contract"):
            unavailable_assessment(dataset, rubric, self.known_check_ids)

    def test_malformed_or_duplicate_known_checks_are_rejected(self):
        for known_checks in ((), (self.known_check_ids[0],) * 2, (" ",)):
            with self.subTest(known_checks=known_checks), self.assertRaises(ValueError):
                SYNTHETIC_RUBRIC.validate_for(SYNTHETIC_DATASET, known_checks)

    def test_duplicate_dataset_queries_are_rejected_as_ambiguous(self):
        dataset = EvaluationDataset(
            "duplicate-queries",
            "v1",
            (
                EvaluationCase("case-1", {"query": "same"}, ("CHECK-EXPLANATION",)),
                EvaluationCase("case-2", {"query": "same"}, ("CHECK-HINT",)),
            ),
        )
        with self.assertRaisesRegex(ValueError, "queries must be unique"):
            SYNTHETIC_RUBRIC.validate_for(dataset, self.known_check_ids)

    def test_real_provider_evaluation_is_disabled_by_default_and_strict_when_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = RealProviderEvaluationSettings.from_environment()
        self.assertFalse(settings.enabled)
        with self.assertRaisesRegex(ValueError, "not explicitly enabled"):
            load_real_provider_evaluator(settings)
        with self.assertRaisesRegex(ValueError, "not explicitly enabled"):
            load_real_provider_results(settings)

        configured = {
            "MAF_REAL_EVALUATION_ENABLED": "true",
            "MAF_REAL_EVALUATION_PROVIDER": "azure-ai-foundry",
            "MAF_REAL_EVALUATION_MODEL": "configured-deployment",
            "MAF_REAL_EVALUATOR_FACTORY": "tests.fixture_evaluator:create",
            "MAF_REAL_RESULT_FACTORY": "tests.fixture_results:create",
            "MAF_REAL_BASE_URL": "https://example.invalid",
            "MAF_REAL_AUTH_FILE": str(Path(__file__).resolve()),
            "SOURCE_REVISION": "source-123",
            "DEPLOYMENT_REVISION": "revision-123",
        }
        with patch.dict(os.environ, configured, clear=True):
            enabled = RealProviderEvaluationSettings.from_environment()
        self.assertTrue(enabled.enabled)
        self.assertEqual(enabled.minimum_score, 0.8)
        for missing in (
            "MAF_REAL_EVALUATION_PROVIDER",
            "MAF_REAL_EVALUATION_MODEL",
            "MAF_REAL_EVALUATOR_FACTORY",
            "MAF_REAL_RESULT_FACTORY",
            "MAF_REAL_BASE_URL",
            "MAF_REAL_AUTH_FILE",
            "SOURCE_REVISION",
            "DEPLOYMENT_REVISION",
        ):
            with self.subTest(missing=missing):
                environment = dict(configured)
                environment.pop(missing)
                with patch.dict(os.environ, environment, clear=True), self.assertRaises(ValueError):
                    RealProviderEvaluationSettings.from_environment()
        with patch.object(
            importlib,
            "import_module",
            return_value=SimpleNamespace(create=lambda **kwargs: {"ORS-001": {"result": kwargs}}),
        ):
            actual = load_real_provider_results(enabled)
        self.assertIn("ORS-001", actual)


if __name__ == "__main__":
    unittest.main()
