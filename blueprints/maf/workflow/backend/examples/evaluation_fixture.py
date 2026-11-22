"""Small synthetic configuration fixture for the application-owned evaluation seam."""

from app.extensions.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationRubric,
    RubricCriterion,
)

SYNTHETIC_DATASET = EvaluationDataset(
    dataset_id="synthetic-review",
    version="v1",
    cases=(
        EvaluationCase(
            case_id="synthetic-explanation",
            inputs={"query": "synthetic explanation query"},
            check_ids=("CHECK-EXPLANATION", "CHECK-HINT"),
        ),
        EvaluationCase(
            case_id="synthetic-hint",
            inputs={"query": "synthetic browser-hint query"},
            check_ids=("CHECK-EXPLANATION", "CHECK-HINT"),
        ),
    ),
)

SYNTHETIC_RUBRIC = EvaluationRubric(
    rubric_id="synthetic-review-quality",
    version="v1",
    criteria=(
        RubricCriterion(
            criterion_id="grounded-explanation",
            check_id="CHECK-EXPLANATION",
            minimum_score=1.0,
        ),
        RubricCriterion(
            criterion_id="accurate-hint",
            check_id="CHECK-HINT",
            minimum_score=0.9,
        ),
    ),
)
