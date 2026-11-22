"""Run the synthetic acceptance and crash tests and retain untrusted evidence."""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


BLUEPRINT = Path(__file__).resolve().parents[1]
CRASH_TESTS = (
    "test_worker_crash_after_decision_before_resume",
    "test_worker_crash_after_action_before_checkpoint",
)
UNVERIFIED_CAPABILITIES = {
    "CHECK-EXPLANATION": (
        "The fixture formats and checks recorded facts; no agent explanation was evaluated."
    ),
    "CHECK-HINT": (
        "The fixture supplies the hint; no browser end-to-end hint was exercised."
    ),
}


def _failure(error):
    kind, exception, _ = error
    message = str(exception)
    dsn = os.environ.get("MAF_TEST_DATABASE_URL", "")
    if dsn:
        message = message.replace(dsn, "[redacted database URL]")
        password = urlsplit(dsn).password
        if password:
            for value in (password, unquote(password)):
                message = message.replace(value, "[redacted]")
    return {"type": kind.__name__, "message": message}


class RecordedResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.cases = {}
        self.crashes = {}
        self.suite_errors = []
        self.golden_complete = False

    def addSubTest(self, test, subtest, error):
        case_id = subtest.params.get("case")
        if case_id and getattr(test, "_testMethodName", "") == "test_application_against_golden_cases":
            record = {"outcome": "failed" if error else "passed"}
            actual = getattr(test, "case_actuals", {}).get(case_id)
            if actual is not None:
                record["actual"] = actual
            if error:
                record["failure"] = _failure(error)
            self.cases[case_id] = record
        elif error:
            self.suite_errors.append({"test": subtest.id(), "outcome": "failed", "failure": _failure(error)})
        super().addSubTest(test, subtest, error)

    def addSuccess(self, test):
        name = getattr(test, "_testMethodName", "")
        if name in CRASH_TESTS:
            self.crashes[name] = {"outcome": "passed"}
        elif name == "test_application_against_golden_cases":
            self.golden_complete = True
        super().addSuccess(test)

    def _record_problem(self, test, error):
        name = getattr(test, "_testMethodName", "")
        record = {"outcome": "failed", "failure": _failure(error)}
        if name in CRASH_TESTS:
            self.crashes[name] = record
        else:
            self.suite_errors.append({"test": test.id(), **record})

    def addError(self, test, error):
        self._record_problem(test, error)
        super().addError(test, error)

    def addFailure(self, test, error):
        self._record_problem(test, error)
        super().addFailure(test, error)

    def addSkip(self, test, reason):
        case_id = getattr(test, "params", {}).get("case")
        parent = getattr(test, "test_case", test)
        name = getattr(parent, "_testMethodName", "")
        if case_id and name == "test_application_against_golden_cases":
            self.cases[case_id] = {"outcome": "unverified", "reason": reason}
        elif name in CRASH_TESTS:
            self.crashes[name] = {"outcome": "unverified", "reason": reason}
        else:
            self.suite_errors.append({"test": test.id(), "outcome": "unverified", "reason": reason})
        super().addSkip(test, reason)


def grounded_explanation(case, actual):
    if not isinstance(actual, dict):
        return False
    required = ("decision", "state", "correlation_id", "explanation")
    if any(not isinstance(actual.get(key), str) or not actual[key] for key in required):
        return False
    inputs = case["input"]
    expected = (
        f"Case {inputs['case_id']} proposes a synthetic adjustment of {inputs['amount']} units. "
        f"Adjustments over 100 units require approval. Approval is {actual['decision']}. "
        f"Correlation ID: {actual['correlation_id']}."
    )
    if actual["state"] == "failed":
        expected += " The configured action failed."
    return actual["explanation"] == expected


def summarize(contract, cases, observed_cases, observed_crashes, suite_errors):
    checks = [check for requirement in contract["requirements"] for check in requirement["checks"]]
    results = {}
    for check in checks:
        check_id = check["id"]
        relevant = [case for case in cases if check_id in case["checks"]]
        observations = []
        for case in relevant:
            record = observed_cases.get(case["id"], {"outcome": "unverified", "reason": "Case did not run."})
            outcome = record["outcome"]
            if outcome == "passed" and "actual" not in record:
                outcome = "unverified"
            if outcome == "passed" and check_id == "CHECK-EXPLANATION":
                if not grounded_explanation(case, record["actual"]):
                    outcome = "failed"
            observations.append({"id": case["id"], "outcome": outcome})
        if check_id == "CHECK-RECOVERY":
            for name in CRASH_TESTS:
                record = observed_crashes.get(name, {"outcome": "unverified"})
                observations.append({"id": name, "outcome": record["outcome"]})
        observations.extend({"id": error["test"], "outcome": error["outcome"]} for error in suite_errors)
        if any(item["outcome"] == "failed" for item in observations):
            outcome = "failed"
            reason = "An actual observation or explanation-grounding check failed."
        elif not relevant or any(item["outcome"] != "passed" for item in observations):
            outcome = "unverified"
            reason = "A required observation was not verified."
        elif check_id in UNVERIFIED_CAPABILITIES:
            outcome = "unverified"
            reason = UNVERIFIED_CAPABILITIES[check_id]
        else:
            outcome = "passed"
            reason = "Derived from recorded synthetic acceptance and worker tests."
        results[check_id] = {"outcome": outcome, "reason": reason, "observations": observations}
    return results


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def produce(verification_root, output, revision, environment):
    scenario = verification_root / "scenarios" / "order-adjustment"
    contract = json.loads((scenario / "verification-contract.json").read_text(encoding="utf-8"))
    cases = json.loads((scenario / "golden-cases.json").read_text(encoding="utf-8"))
    checks = [check["id"] for requirement in contract["requirements"] for check in requirement["checks"]]
    required_checks = {"CHECK-APPROVAL", "CHECK-RECOVERY", "CHECK-EXPLANATION", "CHECK-HINT"}
    case_ids = [case["id"] for case in cases]
    case_checks = {check for case in cases for check in case["checks"]}
    if (
        len(checks) != len(set(checks))
        or set(checks) != required_checks
        or len(case_ids) != len(set(case_ids))
        or case_checks != required_checks
    ):
        raise ValueError("The synthetic contract and golden-case mapping are incomplete or ambiguous.")
    adapter = BLUEPRINT / "tests" / "order_adjustment_adapter.py"
    golden_test = verification_root / "tests" / "test_golden_scenario.py"
    if not adapter.is_file() or not golden_test.is_file():
        raise ValueError("The application adapter and golden test are required.")
    if not os.environ.get("MAF_TEST_DATABASE_URL"):
        raise ValueError("MAF_TEST_DATABASE_URL must identify an isolated test database.")
    if not revision.strip() or not environment.strip():
        raise ValueError("A source revision and environment are required.")
    output.mkdir(parents=True, exist_ok=False)

    old_adapter = os.environ.get("SCENARIO_ADAPTER")
    os.environ["SCENARIO_ADAPTER"] = str(adapter)
    try:
        spec = importlib.util.spec_from_file_location("golden_evidence_tests", golden_test)
        if spec is None or spec.loader is None:
            raise ValueError("The golden test could not be loaded.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite = unittest.TestSuite([
            module.GoldenScenarioTests("test_scenario_contract_and_traceability"),
            module.GoldenScenarioTests("test_unapproved_example_is_schema_valid_and_baseline_pinned"),
            module.GoldenScenarioTests("test_application_against_golden_cases"),
        ])
        suite.addTests(unittest.defaultTestLoader.loadTestsFromNames(
            [f"tests.test_core.WorkflowIntegrationTests.{name}" for name in CRASH_TESTS]
        ))
        recorded = RecordedResult()
        suite.run(recorded)
    finally:
        if old_adapter is None:
            os.environ.pop("SCENARIO_ADAPTER", None)
        else:
            os.environ["SCENARIO_ADAPTER"] = old_adapter

    summary = summarize(contract, cases, recorded.cases, recorded.crashes, recorded.suite_errors)
    observed_at = datetime.now(timezone.utc).isoformat()
    write_json(output / "runner-results.json", {
        "source_revision": revision,
        "environment": environment,
        "recorded_at": observed_at,
        "cases": recorded.cases,
        "worker_recovery": recorded.crashes,
        "suite_errors": recorded.suite_errors,
        "tests_run": recorded.testsRun,
    })
    approvals = []
    for case_id, record in recorded.cases.items():
        actual = record.get("actual")
        if isinstance(actual, dict):
            approvals.append({
                "case_id": case_id,
                "decision": actual.get("decision"),
                "state": actual.get("state"),
                "action_count": actual.get("action_count"),
            })
    write_json(output / "synthetic-approval-observations.json", {
        "synthetic": True,
        "not_a_human_approval": True,
        "observations": approvals,
    })

    def evidence(kind, filename):
        path = output / filename
        return {
            "kind": kind,
            "reference": filename,
            "revision": revision,
            "environment": environment,
            "recorded_at": observed_at,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    normalized = []
    for requirement in contract["requirements"]:
        for check in requirement["checks"]:
            check_id = check["id"]
            result = summary[check_id]
            filename = f"{check_id}.json"
            write_json(output / filename, {
                "check_id": check_id,
                "outcome": result["outcome"],
                "reason": result["reason"],
                "source_revision": revision,
                "environment": environment,
                "recorded_at": observed_at,
                "observations": result["observations"],
                "runner_artifact": "runner-results.json",
            })
            files = {
                "test_report": filename,
                "evaluation_result": filename,
                "security_report": filename,
                "trace": "runner-results.json",
                "approval_record": "synthetic-approval-observations.json",
            }
            if any(kind not in files for kind in check["evidence_types"]):
                raise ValueError(f"Unsupported evidence type for {check_id}.")
            normalized.append({
                "check_id": check_id,
                "outcome": result["outcome"],
                "reason": result["reason"],
                "implementation_refs": ["tests/order_adjustment_adapter.py", "tests/test_core.py"],
                "evidence": [evidence(kind, files[kind]) for kind in check["evidence_types"]],
            })
    assessed_at = datetime.now(timezone.utc).isoformat()
    write_json(output / "readiness-input.json", {
        "schema_version": "1.0.0",
        "context": {
            "target_maturity": "prototype",
            "source_revision": revision,
            "environment": environment,
            "assessed_at": assessed_at,
        },
        "assumptions": ["All scenario records and identities are synthetic."],
        "incomplete_integrations": [
            "Live Entra/OBO and Foundry-managed recovery are unverified.",
            "Agent explanation evaluation and browser end-to-end hint behavior are unverified.",
        ],
        "limitations": [
            "The local producer and its timestamps are not independently attested.",
            "Synthetic approval observations are not human contract approval.",
        ],
        "results": normalized,
        "decisions": [],
    })
    return summary, recorded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verification-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--environment", required=True)
    args = parser.parse_args()
    try:
        results, recorded = produce(
            args.verification_root.resolve(), args.output.resolve(), args.revision, args.environment
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Evidence run failed: {error}", file=sys.stderr)
        return 2
    for check_id, result in results.items():
        print(f"{check_id}: {result['outcome']}")
    expected_gaps_only = all(
        result["outcome"] == "passed"
        or (
            check_id in UNVERIFIED_CAPABILITIES
            and result["outcome"] == "unverified"
            and result["observations"]
            and all(item["outcome"] == "passed" for item in result["observations"])
        )
        for check_id, result in results.items()
    )
    return 0 if expected_gaps_only and recorded.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
