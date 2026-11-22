import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

from agent_framework import (
    AgentResponse,
    EvalItemResult,
    EvalResults,
    EvalScoreResult,
    Evaluator,
    LocalEvaluator,
    Message,
    evaluate_agent,
    evaluator,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.order_resolution.evaluation import (  # noqa: E402
    BUSINESS_OUTCOME_CHECK_ID,
    EXPECTED_SCENARIO_IDS,
    ORDER_RESOLUTION_LOCAL_EVALUATOR,
    READINESS_CHECK_IDS,
    TECHNICAL_EXECUTION_CHECK_ID,
    load_evaluation_dataset,
    map_evaluation_results,
    map_readiness_states,
    unavailable_assessment,
)


@evaluator(name="unavailable-order-resolution-check")
async def unavailable_check(response: str) -> bool:
    raise RuntimeError("native evaluator failed")


class OrderResolutionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.dataset = load_evaluation_dataset()

    def native_results(self, response_overrides=None):
        response_overrides = response_overrides or {}
        responses = [
            AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[
                            response_overrides.get(
                                case.case_id, case.expected_output_text
                            )
                        ],
                    )
                ]
            )
            for case in self.dataset.cases
        ]
        return asyncio.run(
            evaluate_agent(
                queries=[case.query for case in self.dataset.cases],
                responses=responses,
                expected_output=[
                    case.expected_output_text for case in self.dataset.cases
                ],
                evaluators=ORDER_RESOLUTION_LOCAL_EVALUATOR,
                eval_name="order-resolution-local-contract-test",
            )
        )

    def assess(self, results):
        return map_evaluation_results(self.dataset, READINESS_CHECK_IDS, results)

    def test_dataset_references_the_versioned_spec_without_copying_nine_cases(self):
        self.assertEqual(self.dataset.dataset_id, "order-resolution-evaluation")
        self.assertEqual(self.dataset.version, "0.1.0")
        self.assertEqual(self.dataset.specification_id, "order-resolution-spec")
        self.assertEqual(self.dataset.specification_version, "0.1.0")
        self.assertEqual(len(self.dataset.cases), 3)
        scenario_ids = tuple(
            sorted(
                scenario_id
                for case in self.dataset.cases
                for scenario_id in case.scenario_ids
            )
        )
        self.assertEqual(scenario_ids, EXPECTED_SCENARIO_IDS)
        resolution = self.dataset.cases[0].expected_output["business_outcome"]
        self.assertEqual(resolution["ORS-001"]["amount"], "USD 7.90")
        self.assertEqual(resolution["ORS-002"]["amount"], "USD 18.50")
        self.assertEqual(resolution["ORS-003"]["action"], "replacement_shipment")

    def test_dataset_validation_rejects_missing_or_duplicate_scenario_references(self):
        source = BACKEND_ROOT / "evaluations" / "order-resolution-0.1.0.json"
        invalid = json.loads(source.read_text(encoding="utf-8"))
        invalid["cases"][0]["scenario_ids"][0] = "ORS-004"
        invalid["cases"][0]["expected_output"]["scenario_ids"][0] = "ORS-004"
        for section in ("technical_execution", "business_outcome"):
            invalid["cases"][0]["expected_output"][section]["ORS-004"] = invalid[
                "cases"
            ][0]["expected_output"][section].pop("ORS-001")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly once"):
                load_evaluation_dataset(path)

    def test_dataset_validation_rejects_incomplete_expected_sections(self):
        source = BACKEND_ROOT / "evaluations" / "order-resolution-0.1.0.json"
        invalid = json.loads(source.read_text(encoding="utf-8"))
        del invalid["cases"][0]["expected_output"]["business_outcome"]["ORS-001"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly the evaluation case"):
                load_evaluation_dataset(path)

    def test_native_maf_local_evaluator_maps_deterministic_assertions(self):
        self.assertIsInstance(ORDER_RESOLUTION_LOCAL_EVALUATOR, Evaluator)
        result = self.assess(self.native_results())
        self.assertEqual(result.outcome, "passed")
        checks = {item.check_id: item for item in result.check_results}
        self.assertEqual(
            set(checks),
            {TECHNICAL_EXECUTION_CHECK_ID, BUSINESS_OUTCOME_CHECK_ID},
        )
        self.assertTrue(all(item.outcome == "passed" for item in checks.values()))
        self.assertTrue(all(len(item.observations) == 3 for item in checks.values()))

    def test_wrong_business_or_execution_output_fails_closed(self):
        business = json.loads(self.dataset.cases[0].expected_output_text)
        business["business_outcome"]["ORS-001"]["amount"] = "USD 79.00"
        business_result = self.assess(
            self.native_results({self.dataset.cases[0].case_id: json.dumps(business)})
        )
        business_checks = {
            item.check_id: item.outcome for item in business_result.check_results
        }
        self.assertEqual(business_checks[BUSINESS_OUTCOME_CHECK_ID], "failed")
        self.assertEqual(business_checks[TECHNICAL_EXECUTION_CHECK_ID], "passed")

        execution = json.loads(self.dataset.cases[1].expected_output_text)
        execution["technical_execution"]["ORS-005"]["action_count_maximum"] = 2
        execution_result = self.assess(
            self.native_results({self.dataset.cases[1].case_id: json.dumps(execution)})
        )
        execution_checks = {
            item.check_id: item.outcome for item in execution_result.check_results
        }
        self.assertEqual(execution_checks[TECHNICAL_EXECUTION_CHECK_ID], "failed")
        self.assertEqual(execution_checks[BUSINESS_OUTCOME_CHECK_ID], "passed")

    def test_missing_canceled_and_unavailable_results_remain_unverified(self):
        missing = self.assess(())
        canceled = self.assess((EvalResults(provider="synthetic", status="canceled"),))
        unavailable = unavailable_assessment(self.dataset, READINESS_CHECK_IDS)
        for result in (missing, canceled, unavailable):
            self.assertEqual(result.outcome, "unverified")
            self.assertTrue(
                all(item.outcome == "unverified" for item in result.check_results)
            )

    def test_failed_malformed_unknown_and_duplicate_results_cannot_pass(self):
        failed = self.assess((EvalResults(provider="synthetic", status="failed"),))
        malformed = self.assess((None,))
        unknown = EvalResults(
            provider="synthetic",
            items=[
                EvalItemResult(
                    item_id="unknown",
                    status="pass",
                    input_text="not in the configured dataset",
                    scores=[
                        EvalScoreResult(
                            name="order-resolution-business-outcome",
                            score=1.0,
                            passed=True,
                        )
                    ],
                )
            ],
        )
        native = self.native_results()
        duplicate = EvalResults(
            provider="synthetic",
            items=[*native[0].items, native[0].items[0]],
        )
        self.assertEqual(failed.outcome, "failed")
        self.assertEqual(malformed.outcome, "failed")
        self.assertEqual(self.assess((unknown, *native)).outcome, "failed")
        self.assertEqual(self.assess((duplicate,)).outcome, "failed")

    def test_invalid_scores_and_unknown_criteria_fail_closed(self):
        invalid_score = EvalResults(
            provider="synthetic",
            items=[
                EvalItemResult(
                    item_id="invalid-score",
                    status="pass",
                    input_text=self.dataset.cases[0].query,
                    scores=[
                        EvalScoreResult(
                            name="order-resolution-business-outcome",
                            score=10**1000,
                            passed=True,
                        )
                    ],
                )
            ],
        )
        unknown_criterion = EvalResults(
            provider="synthetic",
            items=[
                EvalItemResult(
                    item_id="unknown-criterion",
                    status="pass",
                    input_text=self.dataset.cases[0].query,
                    scores=[
                        EvalScoreResult(
                            name="not-in-the-rubric",
                            score=1.0,
                            passed=True,
                        )
                    ],
                )
            ],
        )
        self.assertEqual(self.assess((invalid_score,)).outcome, "failed")
        self.assertEqual(self.assess((unknown_criterion,)).outcome, "failed")

    def test_native_evaluator_exceptions_propagate_without_synthetic_output(self):
        with self.assertRaisesRegex(RuntimeError, "native evaluator failed"):
            asyncio.run(
                evaluate_agent(
                    queries=[self.dataset.cases[0].query],
                    responses=[
                        AgentResponse(
                            messages=[
                                Message(
                                    role="assistant",
                                    contents=[
                                        self.dataset.cases[0].expected_output_text
                                    ],
                                )
                            ]
                        )
                    ],
                    expected_output=[self.dataset.cases[0].expected_output_text],
                    evaluators=LocalEvaluator(unavailable_check),
                )
            )

    def test_readiness_mapping_keeps_evidence_types_independent(self):
        readiness = {
            state.area: state
            for state in map_readiness_states(self.assess(self.native_results()))
        }
        self.assertEqual(readiness["technical_execution"].outcome, "passed")
        self.assertEqual(readiness["business_outcome"].outcome, "passed")
        self.assertEqual(readiness["model_quality"].outcome, "unverified")
        self.assertEqual(readiness["browser_evidence"].outcome, "unverified")
        self.assertEqual(readiness["provenance"].outcome, "unverified")

    def test_committed_readiness_evidence_does_not_manufacture_integration(self):
        evidence_path = (
            Path(__file__).resolve().parents[2]
            / "verification"
            / "readiness-evidence.json"
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        states = {item["area"]: item["state"] for item in evidence["readiness"]}
        self.assertEqual(
            states,
            {
                "technical_execution": "unverified",
                "business_outcome": "unverified",
                "model_quality": "unverified",
                "browser_evidence": "unverified",
                "provenance": "unverified",
            },
        )
        self.assertTrue(evidence["integration_blockers"])


if __name__ == "__main__":
    unittest.main()
