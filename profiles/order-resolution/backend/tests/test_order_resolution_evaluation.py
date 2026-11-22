import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_framework import Evaluator, LocalEvaluator, evaluator
from jsonschema import Draft202012Validator, FormatChecker


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.order_resolution.evaluation import (  # noqa: E402
    BUSINESS_OUTCOME_CHECK_ID,
    EXPECTED_SCENARIO_IDS,
    ORDER_RESOLUTION_LOCAL_EVALUATOR,
    MODEL_QUALITY_CHECK_ID,
    READINESS_CHECK_IDS,
    TECHNICAL_EXECUTION_CHECK_ID,
    build_group_payloads,
    evaluate_deterministic_results,
    evaluate_real_provider_results,
    load_evaluation_configuration,
    load_golden_expected_outputs,
    map_readiness_states,
    unavailable_deterministic_assessment,
)
from app.extensions.evaluation import RealProviderEvaluationSettings  # noqa: E402
from tests.order_resolution_evidence_runner import produce  # noqa: E402


def golden_cases_path() -> Path:
    generated = (
        PROJECT_ROOT / "verification" / "scenarios" / "order-resolution" / "golden-cases.json"
    )
    if generated.is_file():
        return generated
    return (
        Path(__file__).resolve().parents[4] / "scenarios" / "order-resolution" / "golden-cases.json"
    )


def contracts_path() -> Path:
    generated = PROJECT_ROOT / "verification" / "contracts"
    if generated.is_dir():
        return generated
    return Path(__file__).resolve().parents[4] / "contracts"


@evaluator(name="unavailable-order-resolution-check")
async def unavailable_check(response: str) -> bool:
    raise RuntimeError("native evaluator failed")


@evaluator(name="order-resolution-model-quality")
def fixture_real_provider_check(response: str, expected_output: str) -> bool:
    return response == expected_output


class OrderResolutionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.configuration = load_evaluation_configuration()
        self.expected = load_golden_expected_outputs(golden_cases_path())

    def assess(self, actual=None):
        return asyncio.run(
            evaluate_deterministic_results(
                self.configuration,
                actual or self.expected,
                self.expected,
            )
        )

    def test_dataset_and_rubric_reference_the_canonical_nine_cases(self):
        self.assertEqual(self.configuration.dataset.dataset_id, "order-resolution-evaluation")
        self.assertEqual(self.configuration.dataset.version, "0.1.0")
        self.assertEqual(self.configuration.specification_id, "order-resolution-spec")
        self.assertEqual(self.configuration.specification_version, "0.1.0")
        self.assertEqual(
            self.configuration.golden_cases_path,
            "verification/scenarios/order-resolution/golden-cases.json",
        )
        self.assertEqual(len(self.configuration.groups), 3)
        scenario_ids = tuple(
            sorted(
                scenario_id
                for group in self.configuration.groups
                for scenario_id in group.scenario_ids
            )
        )
        self.assertEqual(scenario_ids, EXPECTED_SCENARIO_IDS)
        self.assertEqual(
            {criterion.check_id for criterion in self.configuration.rubric.criteria},
            {TECHNICAL_EXECUTION_CHECK_ID, BUSINESS_OUTCOME_CHECK_ID},
        )

    def test_configuration_rejects_missing_or_duplicate_scenario_references(self):
        source = BACKEND_ROOT / "evaluations" / "order-resolution-0.1.0.json"
        invalid = json.loads(source.read_text(encoding="utf-8"))
        invalid["cases"][0]["scenario_ids"][0] = "ORS-004"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly once"):
                load_evaluation_configuration(path)

    def test_golden_output_loading_requires_exact_scenario_set_and_layers(self):
        source = golden_cases_path()
        invalid = json.loads(source.read_text(encoding="utf-8"))
        invalid["cases"][0]["expected"]["unexpected"] = {}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "keep business and technical"):
                load_golden_expected_outputs(path)

    def test_native_maf_local_evaluator_uses_the_merged_readiness_mapper(self):
        self.assertIsInstance(ORDER_RESOLUTION_LOCAL_EVALUATOR, Evaluator)
        result = self.assess()
        self.assertEqual(result.outcome, "passed")
        checks = {item.check_id: item for item in result.check_results}
        self.assertEqual(
            set(checks),
            {TECHNICAL_EXECUTION_CHECK_ID, BUSINESS_OUTCOME_CHECK_ID},
        )
        self.assertTrue(all(item.outcome == "passed" for item in checks.values()))
        self.assertTrue(all(len(item.observations) == 3 for item in checks.values()))

    def test_wrong_business_or_execution_output_fails_only_its_layer(self):
        business = json.loads(json.dumps(self.expected))
        business["ORS-001"]["business_outcome"]["proposed_action"]["amount"] = "79.00"
        business_checks = {
            item.check_id: item.outcome for item in self.assess(business).check_results
        }
        self.assertEqual(business_checks[BUSINESS_OUTCOME_CHECK_ID], "failed")
        self.assertEqual(business_checks[TECHNICAL_EXECUTION_CHECK_ID], "passed")

        technical = json.loads(json.dumps(self.expected))
        technical["ORS-005"]["technical_execution"]["action_claim_count"] = 2
        technical_checks = {
            item.check_id: item.outcome for item in self.assess(technical).check_results
        }
        self.assertEqual(technical_checks[TECHNICAL_EXECUTION_CHECK_ID], "failed")
        self.assertEqual(technical_checks[BUSINESS_OUTCOME_CHECK_ID], "passed")

    def test_missing_native_results_remain_unverified(self):
        unavailable = unavailable_deterministic_assessment(self.configuration)
        self.assertEqual(unavailable.outcome, "unverified")
        self.assertTrue(all(item.outcome == "unverified" for item in unavailable.check_results))

    def test_native_evaluator_exceptions_propagate_without_synthetic_output(self):
        with self.assertRaisesRegex(RuntimeError, "native evaluator failed"):
            asyncio.run(
                evaluate_deterministic_results(
                    self.configuration,
                    self.expected,
                    self.expected,
                    evaluator_provider=LocalEvaluator(unavailable_check),
                )
            )

    def test_readiness_mapping_keeps_evidence_types_independent(self):
        readiness = {state.area: state for state in map_readiness_states(self.assess())}
        self.assertEqual(readiness["technical_execution"].outcome, "passed")
        self.assertEqual(readiness["business_outcome"].outcome, "passed")
        self.assertEqual(readiness["model_quality"].outcome, "unverified")
        self.assertEqual(readiness["browser_evidence"].outcome, "unverified")
        self.assertEqual(readiness["provenance"].outcome, "unverified")

    def test_real_provider_mapping_is_separate_and_requires_explicit_settings(self):
        settings = RealProviderEvaluationSettings(
            enabled=True,
            provider_id="azure-ai-foundry",
            model_id="configured-deployment",
            evaluator_factory="tests.fixture:create",
            result_factory="tests.fixture:results",
            base_url="https://synthetic.invalid",
            source_revision="source-123",
            deployment_revision="revision-123",
            minimum_score=0.8,
        )
        model = asyncio.run(
            evaluate_real_provider_results(
                self.configuration,
                self.expected,
                self.expected,
                LocalEvaluator(fixture_real_provider_check),
                settings,
            )
        )
        self.assertEqual(model.outcome, "passed")
        self.assertEqual(
            [(item.check_id, item.outcome) for item in model.check_results],
            [(MODEL_QUALITY_CHECK_ID, "passed")],
        )
        readiness = {state.area: state for state in map_readiness_states(self.assess(), model)}
        self.assertEqual(readiness["model_quality"].outcome, "passed")

    def test_group_payloads_do_not_mix_business_and_technical_facts(self):
        payloads = [
            json.loads(value) for value in build_group_payloads(self.configuration, self.expected)
        ]
        self.assertEqual(len(payloads), 3)
        for payload in payloads:
            self.assertEqual(
                set(payload),
                {"scenario_ids", "business_outcome", "technical_execution"},
            )
            self.assertEqual(
                set(payload["business_outcome"]),
                set(payload["technical_execution"]),
            )

    def test_readiness_contract_contains_every_strict_check_id(self):
        scenario = PROJECT_ROOT / "verification" / "scenarios" / "order-resolution"
        contract_path = scenario / "verification-contract.json"
        trust_path = scenario / "example-trust.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        trust = json.loads(trust_path.read_text(encoding="utf-8"))
        for document, schema_name in (
            (contract, "verification-contract.schema.json"),
            (trust, "readiness-trust.schema.json"),
        ):
            schema = json.loads((contracts_path() / schema_name).read_text(encoding="utf-8"))
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).validate(document)
        check_ids = {
            check["id"]
            for requirement in contract["requirements"]
            for check in requirement["checks"]
        }
        self.assertEqual(check_ids, set(READINESS_CHECK_IDS))
        self.assertEqual(
            trust["baseline_sha256"],
            hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        )

    def test_evidence_producer_keeps_untrusted_capabilities_unverified(self):
        golden_path = golden_cases_path()
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        actual = {case["id"]: case["expected"] for case in golden["cases"]}
        records = {
            case_id: {"outcome": "passed", "actual": result} for case_id, result in actual.items()
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verification = root / "verification"
            scenario = verification / "scenarios" / "order-resolution"
            scenario.mkdir(parents=True)
            (scenario / "golden-cases.json").write_text(
                json.dumps(golden),
                encoding="utf-8",
            )
            output = verification / "evidence" / "order-resolution"
            with (
                patch.dict(
                    "os.environ",
                    {"MAF_TEST_DATABASE_URL": "postgresql://test:test@localhost/test"},
                ),
                patch(
                    "tests.order_resolution_evidence_runner.execute_cases",
                    return_value=(actual, records),
                ),
            ):
                matrix = produce(
                    verification,
                    output,
                    "test-revision",
                    "unit-test",
                )
            readiness = json.loads((output / "readiness-input.json").read_text(encoding="utf-8"))
            release = json.loads((output / "release-evidence.json").read_text(encoding="utf-8"))
            release_schema = json.loads(
                (contracts_path() / "release-evidence.schema.json").read_text(encoding="utf-8")
            )
            Draft202012Validator(
                release_schema,
                format_checker=FormatChecker(),
            ).validate(release)
            for evidence in release["dimensions"]["implementation"]["evidence"]:
                self.assertEqual(
                    evidence["sha256"],
                    hashlib.sha256((output / evidence["reference"]).read_bytes()).hexdigest(),
                )
        states = {item["check_id"]: item["outcome"] for item in readiness["results"]}
        self.assertEqual(matrix["local_factory_status"], "passed")
        self.assertEqual(matrix["release_status"], "blocked")
        self.assertEqual(release["authority"], "diagnostic_non_authorizing")
        self.assertEqual(release["dimensions"]["implementation"]["status"], "passed")
        self.assertEqual(release["dimensions"]["azure_runtime"]["status"], "unverified")
        self.assertEqual(release["dimensions"]["production"]["status"], "blocked")
        self.assertEqual(states[TECHNICAL_EXECUTION_CHECK_ID], "passed")
        self.assertEqual(states[BUSINESS_OUTCOME_CHECK_ID], "passed")
        self.assertEqual(states["ORDER-RESOLUTION-MODEL-QUALITY"], "unverified")
        self.assertEqual(states["ORDER-RESOLUTION-BROWSER-EVIDENCE"], "unverified")
        self.assertEqual(states["ORDER-RESOLUTION-PROVENANCE"], "unverified")


if __name__ == "__main__":
    unittest.main()
