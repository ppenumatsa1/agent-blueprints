"""Validate revision-bound implementation, Azure runtime, and production evidence."""

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .validator import InputError, local_path, parse_json, read_bytes, sha256, timestamp


ROOT = Path(__file__).resolve().parents[1]
AZURE_REQUIRED_KINDS = {
    "active_revision",
    "hosted_test",
    "evaluation_result",
    "browser_test",
    "failure_injection",
    "telemetry_query",
}
PRODUCTION_REQUIRED_KINDS = {"security_report", "cost_report", "human_review"}
STATE_PRECEDENCE = ("failed", "blocked", "unverified", "passed")


def _schema():
    return parse_json(
        read_bytes(ROOT / "contracts" / "release-evidence.schema.json"),
        "release-evidence.schema.json",
    )


def _validate_schema(manifest):
    errors = sorted(
        Draft202012Validator(
            _schema(),
            format_checker=FormatChecker(),
        ).iter_errors(manifest),
        key=lambda error: list(map(str, error.path)),
    )
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.path)) or "$"
        raise InputError(f"Invalid release evidence at {location}: {error.message}")


def _success_issue(kind, artifact):
    if kind in {"hosted_test", "failure_injection"}:
        scenarios = artifact.get("scenarios")
        if not isinstance(scenarios, dict) or not scenarios:
            return "hosted evidence does not contain scenario results"
        if any(
            not isinstance(result, dict) or result.get("status") != "passed"
            for result in scenarios.values()
        ):
            return "one or more hosted scenarios did not pass"
        return None
    if kind == "local_test" and isinstance(artifact.get("cases"), dict):
        cases = artifact["cases"]
        if not cases or any(
            not isinstance(result, dict) or result.get("outcome") != "passed"
            for result in cases.values()
        ):
            return "one or more local test cases did not pass"
        return None
    if artifact.get("outcome") != "passed":
        return "artifact does not report a passed outcome"
    return None


def _artifact_issues(manifest, item, root, dimension):
    issues = []
    if item["source_revision"] != manifest["source_revision"]:
        issues.append(f"{item['reference']}: source_revision mismatch")
    if dimension != "implementation" and item["environment"] != manifest["environment"]:
        issues.append(f"{item['reference']}: environment mismatch")
    if (
        dimension != "implementation"
        and item["deployment_revision"] != manifest["deployment_revision"]
    ):
        issues.append(f"{item['reference']}: deployment_revision mismatch")
    if timestamp(item["recorded_at"]) > timestamp(manifest["recorded_at"]):
        issues.append(f"{item['reference']}: evidence is future-dated")
    try:
        data = read_bytes(local_path(root, item["reference"]))
        if sha256(data) != item["sha256"]:
            issues.append(f"{item['reference']}: SHA-256 mismatch")
            return issues
        if item["reference"].lower().endswith(".json"):
            artifact = parse_json(data, item["reference"])
            if not isinstance(artifact, dict):
                issues.append(f"{item['reference']}: JSON evidence is not an object")
                return issues
            if artifact.get("source_revision") != manifest["source_revision"]:
                issues.append(
                    f"{item['reference']}: artifact source_revision does not corroborate the manifest"
                )
            if (
                dimension != "implementation"
                and artifact.get("environment") != manifest["environment"]
            ):
                issues.append(
                    f"{item['reference']}: artifact environment does not corroborate the manifest"
                )
            if (
                dimension != "implementation"
                and manifest["deployment_revision"] is not None
                and artifact.get("deployment_revision")
                != manifest["deployment_revision"]
            ):
                issues.append(
                    f"{item['reference']}: artifact deployment_revision does not corroborate the manifest"
                )
            success_issue = _success_issue(item["kind"], artifact)
            if success_issue:
                issues.append(f"{item['reference']}: {success_issue}")
        else:
            issues.append(
                f"{item['reference']}: passing evidence must be a JSON object"
            )
    except InputError as error:
        issues.append(str(error))
    return issues


def validate_release_evidence(manifest_path, evidence_root):
    manifest = parse_json(read_bytes(manifest_path), manifest_path)
    _validate_schema(manifest)
    root = Path(evidence_root)
    if not root.is_dir():
        raise InputError("Evidence root is not an accessible directory")

    report = {
        "schema_version": "1.0.0",
        "source_revision": manifest["source_revision"],
        "environment": manifest["environment"],
        "agent_version": manifest["agent_version"],
        "deployment_revision": manifest["deployment_revision"],
        "recorded_at": manifest["recorded_at"],
        "dimensions": {},
        "overall_status": "unverified",
    }
    for name in ("implementation", "azure_runtime", "production"):
        dimension = manifest["dimensions"][name]
        issues = []
        valid_checks = set()
        valid_kinds = set()
        for item in dimension["evidence"]:
            item_issues = _artifact_issues(manifest, item, root, name)
            issues.extend(item_issues)
            if not item_issues:
                valid_checks.add(item["check_id"])
                valid_kinds.add(item["kind"])
        if dimension["status"] == "passed":
            missing_checks = set(dimension["required_checks"]) - valid_checks
            if missing_checks:
                issues.append(
                    "Missing valid evidence for checks: "
                    + ", ".join(sorted(missing_checks))
                )
            if name == "azure_runtime":
                if manifest["deployment_revision"] is None:
                    issues.append(
                        "Azure runtime evidence requires an exact deployment revision."
                    )
                missing_kinds = AZURE_REQUIRED_KINDS - valid_kinds
                if missing_kinds:
                    issues.append(
                        "Azure runtime evidence is missing kinds: "
                        + ", ".join(sorted(missing_kinds))
                    )
            elif name == "implementation" and "local_test" not in valid_kinds:
                issues.append("Implementation readiness requires local_test evidence.")
            elif name == "production":
                missing_kinds = PRODUCTION_REQUIRED_KINDS - valid_kinds
                if missing_kinds:
                    issues.append(
                        "Production evidence is missing kinds: "
                        + ", ".join(sorted(missing_kinds))
                    )
                dependencies = report["dimensions"]
                if any(
                    dependencies[dependency]["status"] != "passed"
                    for dependency in ("implementation", "azure_runtime")
                ):
                    issues.append(
                        "Production readiness requires passed implementation and Azure runtime readiness."
                    )

        status = dimension["status"]
        if status == "passed" and issues:
            status = "blocked" if name == "production" else "unverified"
        report["dimensions"][name] = {
            "status": status,
            "claimed_status": dimension["status"],
            "reason": dimension["reason"],
            "blockers": dimension["blockers"],
            "issues": issues,
            "validated_checks": sorted(valid_checks),
            "validated_evidence_kinds": sorted(valid_kinds),
        }

    statuses = {dimension["status"] for dimension in report["dimensions"].values()}
    report["overall_status"] = next(
        state for state in STATE_PRECEDENCE if state in statuses
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = validate_release_evidence(
            args.manifest.resolve(),
            args.evidence_root.resolve(),
        )
        code = 0 if report["overall_status"] == "passed" else 1
    except InputError as error:
        report = {"error": str(error)}
        code = 2
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        try:
            args.output.write_text(text, encoding="utf-8")
        except OSError as error:
            print(
                json.dumps({"error": f"Cannot write report: {error}"}), file=sys.stderr
            )
            return 2
    else:
        print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
