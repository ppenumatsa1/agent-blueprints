"""Verify bounded local evidence and independently administered signed decisions."""

import base64
import binascii
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5 * 1024 * 1024
RESULT_KINDS = {"test_report", "evaluation_result", "security_report"}
CONTROL_CHECKS = {
    "security": ({"security", "integration", "e2e", "contract"}, {"security_report", "test_report"}),
    "integration": ({"integration", "e2e"}, {"test_report"}),
    "operations": ({"smoke", "integration", "e2e"}, {"test_report"}),
    "evaluation": ({"agent_evaluation"}, {"evaluation_result"}),
}


class InputError(ValueError):
    """The contract, context, or trust anchor cannot be safely identified."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read_bytes(path):
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
    except (OSError, ValueError) as error:
        raise InputError(f"Cannot read {path}: {error}") from error
    if len(data) > MAX_BYTES:
        raise InputError(f"File exceeds {MAX_BYTES} bytes: {path}")
    return data


def parse_json(data, label):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise InputError(f"Invalid JSON in {label}: {error}") from error


def load_json(path):
    return parse_json(read_bytes(path), path)


def check_schema(document, name):
    schema = load_json(ROOT / "contracts" / f"{name}.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(map(str, error.path)))
    if errors:
        error = errors[0]
        location = "/".join(map(str, error.path)) or "$"
        raise InputError(f"Invalid {name} at {location}: {error.message}")


def local_path(root, reference):
    path = Path(reference)
    if path.is_absolute() or "://" in reference:
        raise InputError(f"Not a relative local path: {reference}")
    try:
        root = Path(root).resolve()
        resolved = (root / path).resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise InputError(f"Cannot resolve {reference}: {error}") from error
    if not resolved.is_relative_to(root) or resolved == root:
        raise InputError(f"Path escapes its trusted root: {reference}")
    return resolved


def unique_contract_ids(contract):
    requirements = [requirement["id"] for requirement in contract["requirements"]]
    checks = [check["id"] for requirement in contract["requirements"] for check in requirement["checks"]]
    if len(requirements) != len(set(requirements)) or len(checks) != len(set(checks)):
        raise InputError("Contract contains duplicate requirement or check IDs")


class Decisions:
    def __init__(self, trust, trust_root, decisions, assessed_at, diagnostics):
        self.keys = {}
        self.root = trust_root
        self.assessed_at = assessed_at
        self.diagnostics = diagnostics
        self.decisions = decisions
        self.verified = []
        for key in trust["keys"]:
            if key["id"] in self.keys:
                raise InputError(f"Duplicate trusted key ID: {key['id']}")
            self.keys[key["id"]] = key

    def find(self, kind, scope, decision="approved", needs_rationale=False, diagnose=True):
        matches = []
        for envelope in self.decisions:
            payload = envelope["payload"]
            if payload["kind"] != kind or payload["scope"] != scope:
                continue
            key = self.keys.get(payload["key_id"])
            if not key or kind not in key["roles"]:
                continue
            if not (timestamp(payload["decided_at"]) <= self.assessed_at < timestamp(payload["expires_at"])):
                continue
            if "revoked_at" in key and timestamp(key["revoked_at"]) <= self.assessed_at:
                continue
            if needs_rationale and not payload.get("rationale"):
                continue
            if kind == "risk" and "compensating_controls" not in payload:
                continue
            try:
                signature = base64.b64decode(envelope["signature"], validate=True)
                public_key = local_path(self.root, key["public_key"])
                read_bytes(public_key)
                with tempfile.TemporaryDirectory() as temporary:
                    signature_file = Path(temporary) / "decision.sig"
                    signature_file.write_bytes(signature)
                    verified = subprocess.run(
                        ["openssl", "dgst", "-sha256", "-verify", str(public_key),
                         "-signature", str(signature_file)],
                        input=canonical(payload), capture_output=True, check=False,
                        timeout=10,
                    )
                if verified.returncode != 0:
                    continue
            except (InputError, binascii.Error, OSError, subprocess.TimeoutExpired):
                continue
            matches.append((payload, key))
        if len(matches) != 1 or matches[0][0]["decision"] != decision:
            if diagnose:
                self.diagnostics.append(f"Missing, invalid, rejected, or ambiguous {kind} decision for {scope}")
            return None
        payload, key = matches[0]
        self.verified.append({
            "kind": kind, "decision": payload["decision"], "reviewer": key["reviewer"],
            "reference": payload["reference"], "decided_at": payload["decided_at"],
            "expires_at": payload["expires_at"], "scope": payload["scope"],
            **({"rationale": payload["rationale"]} if "rationale" in payload else {}),
        })
        return matches[0]


def approval(record):
    payload, key = record
    return {"decision": payload["decision"], "reviewer": key["reviewer"],
            "reference": payload["reference"], "decided_at": payload["decided_at"]}


def evidence_check(check, result, context, root):
    issues = []
    kinds = set()
    corroborated = False
    for item in result["evidence"]:
        kinds.add(item["kind"])
        if item["revision"] != context["source_revision"]:
            issues.append(f"{item['reference']}: revision mismatch")
        if item["environment"] != context["environment"]:
            issues.append(f"{item['reference']}: environment mismatch")
        age = (timestamp(context["assessed_at"]) - timestamp(item["recorded_at"])).total_seconds()
        if age < 0 or age > check["evidence_max_age_seconds"]:
            issues.append(f"{item['reference']}: evidence is future-dated or stale")
        try:
            data = read_bytes(local_path(root, item["reference"]))
            if sha256(data) != item["sha256"]:
                issues.append(f"{item['reference']}: SHA-256 mismatch")
                continue
            if item["kind"] in RESULT_KINDS:
                artifact = parse_json(data, item["reference"])
                expected = {"check_id": check["id"], "outcome": result["outcome"],
                            "source_revision": context["source_revision"],
                            "environment": context["environment"],
                            "recorded_at": item["recorded_at"]}
                if isinstance(artifact, dict) and all(artifact.get(k) == v for k, v in expected.items()):
                    corroborated = True
                else:
                    issues.append(f"{item['reference']}: result artifact does not corroborate the check")
        except InputError as error:
            issues.append(str(error))
    missing = set(check["evidence_types"]) - kinds
    if missing:
        issues.append(f"Missing evidence types: {', '.join(sorted(missing))}")
    if not corroborated:
        issues.append("No matching normalized result artifact")
    return issues


def classification_changes(baseline, contract):
    current = {item["id"]: item for item in contract["requirements"]}
    changes = []
    for old in baseline["requirements"]:
        new = current.get(old["id"])
        items = []
        if new is None:
            items.append("requirement removed")
        else:
            if old["critical"] and not new["critical"]:
                items.append("critical classification removed")
            if old["security_critical"] and not new["security_critical"]:
                items.append("security-critical classification removed")
            for target, gate in old["gates"].items():
                if gate != "not_applicable" and new["gates"][target] == "not_applicable":
                    items.append(f"{target} changed to not_applicable")
                elif gate == "blocking" and new["gates"][target] == "non_blocking":
                    items.append(f"{target} blocking gate relaxed")
            if old["critical"] and old != new:
                items.append("critical requirement changed")
            old_checks = {check["id"]: check for check in old["checks"]}
            new_checks = {check["id"]: check for check in new["checks"]}
            for check_id, old_check in old_checks.items():
                new_check = new_checks.get(check_id)
                if new_check is None:
                    items.append(f"{check_id} removed")
                elif (not set(old_check["evidence_types"]).issubset(new_check["evidence_types"])
                      or new_check["evidence_max_age_seconds"] > old_check["evidence_max_age_seconds"]):
                    items.append(f"{check_id} evidence policy relaxed")
        if items:
            changes.append(("requirement", old["id"], sorted(items)))
    if "production_controls" in baseline and baseline["production_controls"] != contract.get("production_controls"):
        changes.append(("production_controls", None, ["production controls changed"]))
    return changes


def validate(contract_path, baseline_path, input_path, trust_path, evidence_root):
    contract_bytes = read_bytes(contract_path)
    baseline_bytes = read_bytes(baseline_path)
    contract = parse_json(contract_bytes, contract_path)
    baseline = parse_json(baseline_bytes, baseline_path)
    inputs = load_json(input_path)
    trust = load_json(trust_path)
    for document, name in ((contract, "verification-contract"), (baseline, "verification-contract"),
                           (inputs, "readiness-input"), (trust, "readiness-trust")):
        check_schema(document, name)
    unique_contract_ids(contract)
    unique_contract_ids(baseline)
    if sha256(baseline_bytes) != trust["baseline_sha256"]:
        raise InputError("Baseline contract does not match the independently administered trust anchor")
    if baseline["contract_id"] != contract["contract_id"]:
        raise InputError("Baseline and assessed contract IDs differ")
    root = Path(evidence_root)
    if not root.is_dir():
        raise InputError("Evidence root is not an accessible directory")

    context = inputs["context"]
    target = context["target_maturity"]
    contract_hash = sha256(contract_bytes)
    diagnostics = []
    decisions = Decisions(trust, Path(trust_path).resolve().parent, inputs["decisions"],
                          timestamp(context["assessed_at"]), diagnostics)
    contract_decision = decisions.find("contract", {"contract_sha256": contract_hash})
    for subject, requirement_id, changes in classification_changes(baseline, contract):
        scope = {"baseline_sha256": sha256(baseline_bytes), "contract_sha256": contract_hash,
                 "changes": changes}
        scope["requirement_id" if subject == "requirement" else "production_controls"] = (
            requirement_id if subject == "requirement" else True
        )
        decisions.find("classification", scope, needs_rationale=True)

    known_checks = {check["id"] for req in contract["requirements"] for check in req["checks"]}
    indexed = {}
    for result in inputs["results"]:
        check_id = result["check_id"]
        if check_id not in known_checks:
            diagnostics.append(f"Unknown check ID: {check_id}")
        elif check_id in indexed:
            diagnostics.append(f"Duplicate check ID: {check_id}")
        else:
            indexed[check_id] = result

    report = {
        "schema_version": "0.3.0", "contract_id": contract["contract_id"],
        "contract_version": contract["contract_version"], "contract_sha256": contract_hash,
        **context, "gate_status": "unverified",
        "assumptions": inputs["assumptions"], "incomplete_integrations": inputs["incomplete_integrations"],
        "limitations": inputs["limitations"], "results": [],
    }
    if contract_decision:
        report["contract_approval"] = approval(contract_decision)
    for requirement in contract["requirements"]:
        req_id = requirement["id"]
        gate = requirement["gates"][target]
        result = {"requirement_id": req_id, "gate": gate}
        if gate == "not_applicable":
            scope = {"contract_sha256": contract_hash, "target_maturity": target,
                     "source_revision": context["source_revision"], "environment": context["environment"],
                     "requirement_id": req_id}
            decision = decisions.find("applicability", scope, needs_rationale=True)
            if decision:
                result.update(status="not_applicable", reason=decision[0]["rationale"],
                              applicability_review={"reviewer": decision[1]["reviewer"],
                                                    "reference": decision[0]["reference"]})
            else:
                result.update(status="unverified", reason="Applicability decision not verified.")
            report["results"].append(result)
            continue
        check_results = []
        implementation_refs = set()
        for check in requirement["checks"]:
            supplied = indexed.get(check["id"])
            if supplied is None:
                check_results.append({"check_id": check["id"], "outcome": "unverified",
                                      "reason": "Required check result is missing."})
                continue
            implementation_refs.update(supplied.get("implementation_refs", []))
            issues = evidence_check(check, supplied, context, root)
            scope = {"contract_sha256": contract_hash, "target_maturity": target,
                     "source_revision": context["source_revision"], "environment": context["environment"],
                     "check_id": check["id"], "result_sha256": sha256(canonical(supplied))}
            if not decisions.find("result", scope, decision="attested", diagnose=False):
                issues.append("Result producer attestation is missing or invalid")
            outcome = supplied["outcome"]
            if outcome == "passed" and issues:
                outcome = "unverified"
            item = {"check_id": check["id"], "outcome": outcome}
            if supplied["evidence"]:
                item["evidence"] = supplied["evidence"]
            if outcome != "passed":
                item["reason"] = "; ".join(filter(None, [supplied.get("reason"), *issues])) or "Check not passed."
            check_results.append(item)
        statuses = {item["outcome"] for item in check_results}
        status = "failed" if "failed" in statuses else "unverified" if "unverified" in statuses else "passed"
        result.update(status=status, check_results=check_results)
        if implementation_refs:
            result["implementation_refs"] = sorted(implementation_refs)
        if status != "passed":
            result["reason"] = "; ".join(f"{item['check_id']}: {item['reason']}"
                                         for item in check_results if item["outcome"] != "passed")
        report["results"].append(result)

    for result in report["results"]:
        if target == "prototype" or result["gate"] != "non_blocking" or result["status"] not in ("failed", "unverified"):
            continue
        check_ids = sorted(item["check_id"] for item in result["check_results"] if item["outcome"] != "passed")
        finding_hash = sha256(canonical(result["check_results"]))
        scope = {"requirement_id": result["requirement_id"], "check_ids": check_ids,
                 "requirement_status": result["status"], "contract_sha256": contract_hash,
                 "target_maturity": target, "source_revision": context["source_revision"],
                 "environment": context["environment"], "finding_sha256": finding_hash}
        record = decisions.find("risk", scope, decision="accepted", needs_rationale=True)
        if record:
            payload, key = record
            report_scope = {k: v for k, v in scope.items() if k != "finding_sha256"}
            result["risk_acceptance"] = {
                "decision": "accepted", "reviewer": key["reviewer"], "reference": payload["reference"],
                "decided_at": payload["decided_at"], "expires_at": payload["expires_at"],
                "rationale": payload["rationale"], "compensating_controls": payload["compensating_controls"],
                "scope": report_scope,
            }

    if target != "prototype":
        controls = contract.get("production_controls")
        if controls is None:
            diagnostics.append("Production controls are missing.")
        else:
            for domain, control in controls.items():
                if control["applicability"] == "not_applicable":
                    scope = {"contract_sha256": contract_hash, "target_maturity": target,
                             "source_revision": context["source_revision"], "environment": context["environment"],
                             "domain": domain, "reason": control["reason"],
                             "reference": control["review"]["reference"],
                             "reviewer": control["review"]["reviewer"]}
                    record = decisions.find("applicability", scope, needs_rationale=True)
                    if record and (record[1]["reviewer"] != control["review"]["reviewer"]
                                   or record[0]["reference"] != control["review"]["reference"]):
                        diagnostics.append(f"Production {domain} review identity does not match.")
                elif not any(
                    domain in req["domains"] and req["gates"][target] == "blocking"
                    and any(check["method"] in CONTROL_CHECKS[domain][0]
                            and set(check["evidence_types"]) & CONTROL_CHECKS[domain][1]
                            for check in req["checks"])
                    for req in contract["requirements"]
                ):
                    diagnostics.append(f"Production {domain} lacks a blocking requirement with an appropriate check and evidence type.")

    blocking = [result for result in report["results"] if result["gate"] == "blocking"]
    failed = any(result["status"] == "failed" for result in blocking)
    unverified = not blocking or any(result["status"] != "passed" for result in blocking)
    if target != "prototype":
        failed |= any(result["gate"] == "non_blocking" and result["status"] == "failed"
                      and "risk_acceptance" not in result for result in report["results"])
        unverified |= any(result["gate"] == "non_blocking" and result["status"] == "unverified"
                          and "risk_acceptance" not in result for result in report["results"])
    if target == "customer_validated":
        scope = {"contract_sha256": contract_hash, "target_maturity": target,
                 "source_revision": context["source_revision"], "environment": context["environment"],
                 "results_sha256": sha256(canonical(report["results"]))}
        record = decisions.find("customer", scope, needs_rationale=True)
        if record:
            report["customer_approval"] = approval(record)
    if not blocking:
        diagnostics.append("No applicable blocking requirements.")
    report["gate_status"] = "failed" if failed else "unverified" if unverified or diagnostics else "passed"
    report["extensions"] = {"validator": {"diagnostics": diagnostics, "verified_decisions": decisions.verified}}
    check_schema(report, "readiness-report")
    return report
