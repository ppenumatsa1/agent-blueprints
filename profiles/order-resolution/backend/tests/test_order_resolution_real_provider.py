"""Opt-in real-provider evaluation; excluded from credential-free CI."""

import asyncio
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.extensions.evaluation import (
    RealProviderEvaluationSettings,
    load_real_provider_evaluator,
    load_real_provider_results,
)
from app.order_resolution.evaluation import (
    MODEL_QUALITY_CHECK_ID,
    evaluate_real_provider_results,
    load_evaluation_configuration,
    load_golden_expected_outputs,
)
from tests.test_order_resolution_evaluation import golden_cases_path


@unittest.skipUnless(
    os.environ.get("MAF_REAL_EVALUATION_ENABLED", "").lower() == "true",
    "Real-provider evaluation requires explicit MAF_REAL_EVALUATION_ENABLED=true.",
)
class OrderResolutionRealProviderTests(unittest.TestCase):
    def test_configured_provider_evaluates_canonical_results(self):
        settings = RealProviderEvaluationSettings.from_environment()
        evaluator_provider = load_real_provider_evaluator(settings)
        actual = load_real_provider_results(settings)
        configuration = load_evaluation_configuration()
        expected = load_golden_expected_outputs(golden_cases_path())
        assessment = asyncio.run(
            evaluate_real_provider_results(
                configuration,
                actual,
                expected,
                evaluator_provider,
                settings,
            )
        )
        self.assertEqual(assessment.outcome, "passed")
        self.assertEqual(
            [(result.check_id, result.outcome) for result in assessment.check_results],
            [(MODEL_QUALITY_CHECK_ID, "passed")],
        )
        output = os.environ.get("REAL_PROVIDER_EVIDENCE_FILE")
        if output:
            Path(output).write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "source_revision": settings.source_revision,
                        "deployment_revision": settings.deployment_revision,
                        "environment": os.environ["EVIDENCE_ENVIRONMENT"],
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "check_id": "MODEL-QUALITY",
                        "outcome": assessment.outcome,
                        "provider": settings.provider_id,
                        "model": settings.model_id,
                        "dataset_id": assessment.dataset_id,
                        "dataset_version": assessment.dataset_version,
                        "rubric_id": assessment.rubric_id,
                        "rubric_version": assessment.rubric_version,
                        "observations": [
                            {
                                "case_id": observation.case_id,
                                "criterion_id": observation.criterion_id,
                                "score": observation.score,
                                "minimum_score": observation.minimum_score,
                                "reference": observation.reference,
                            }
                            for result in assessment.check_results
                            for observation in result.observations
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )


if __name__ == "__main__":
    unittest.main()
