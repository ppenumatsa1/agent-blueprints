"""Copy the MAF workflow blueprint and its independent verification assets."""

import argparse
import ast
import json
import re
import shutil
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprints" / "maf" / "workflow"
ORDER_RESOLUTION_PROFILE = ROOT / "profiles" / "order-resolution"
ORDER_RESOLUTION_OVERLAY = ORDER_RESOLUTION_PROFILE / "overlay"
ORDER_RESOLUTION_HOSTED_AGENT = ORDER_RESOLUTION_PROFILE / "hosted-agent"
ORDER_RESOLUTION_FOUNDRY_SCRIPT = (
    ROOT / "scripts" / "foundry" / "publish_order_resolution_hosted.py"
)
ORDER_RESOLUTION_CONTRACT = (
    ROOT / "scenarios" / "order-resolution" / "acceptance-contract.json"
)
ORDER_RESOLUTION_CASES = ROOT / "scenarios" / "order-resolution" / "golden-cases.json"
ORDER_RESOLUTION_TEST = ROOT / "tests" / "test_order_resolution_contract.py"
ORDER_RESOLUTION_API_BRIDGE_ENTRYPOINT = "bridge.py"
ORDER_RESOLUTION_API_BRIDGE_MODULES: tuple[str, ...] = (
    "bridge.py",
    "client.py",
    "credentials.py",
)
IGNORE = shutil.ignore_patterns(
    ".git",
    ".env",
    ".env.*",
    ".venv",
    ".uv-cache",
    ".ruff_cache",
    "__pycache__",
    "*.pyc",
    "node_modules",
    "dist",
    "coverage",
)

CATALOG_SCHEMA = "workflow-use-cases/1"
ORDER_RESOLUTION_SCENARIO_SET = "order-resolution-spec/0.1.0"


def _unavailable_catalog() -> dict:
    return {
        "schema_version": CATALOG_SCHEMA,
        "status": "unavailable",
        "scenario_set": None,
        "cases": [],
    }


def _catalog_evidence(item: object, invalid_reason: str | None = None) -> dict:
    if not isinstance(item, dict):
        raise ValueError("Invalid synthetic policy input.")
    policy = item.get("policy")
    if not isinstance(policy, str) or not re.fullmatch(
        r"POLICY-[A-Za-z0-9._-]{1,80}@[0-9]{1,4}", policy
    ):
        raise ValueError("Invalid synthetic policy identifier.")
    result: dict[str, object] = {"policy": policy}
    for key, invalid in (
        ("current", "expired"),
        ("applicable", "non-applicable"),
        ("digest_valid", "digest-invalid"),
    ):
        value = item.get(key, True if invalid_reason is not None else None)
        if not isinstance(value, bool):
            raise ValueError("Invalid synthetic policy assertion.")
        result[key] = value and invalid_reason != invalid
    if "asserted_action" in item:
        action = item["asserted_action"]
        if action not in ("partial_refund_10", "replacement_shipment"):
            raise ValueError("Invalid synthetic action assertion.")
        result["asserted_action"] = action
    if "asserted_approval_required" in item:
        approval = item["asserted_approval_required"]
        if not isinstance(approval, bool):
            raise ValueError("Invalid synthetic approval assertion.")
        result["asserted_approval_required"] = approval
    return result


def _order_resolution_catalog(contract_path: Path, cases_path: Path) -> dict:
    """Project selected fixture inputs to inert browser data; never export commands."""
    try:
        if contract_path.stat().st_size > 1_000_000 or cases_path.stat().st_size > 1_000_000:
            raise ValueError("Synthetic assets are too large.")
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        golden = json.loads(cases_path.read_text(encoding="utf-8"))
        if (
            not isinstance(contract, dict)
            or contract.get("contract_id") != "order-resolution-spec"
            or contract.get("contract_version") != "0.1.0"
            or contract.get("scenario_set") != ORDER_RESOLUTION_SCENARIO_SET
            or not isinstance(golden, dict)
            or golden.get("scenario_set") != ORDER_RESOLUTION_SCENARIO_SET
            or not isinstance(contract.get("orders"), dict)
            or not isinstance(contract.get("amounts"), dict)
            or contract["amounts"].get("currency") != "USD"
            or not isinstance(golden.get("cases"), list)
            or not 1 <= len(golden["cases"]) <= 64
        ):
            raise ValueError("Unsupported synthetic assets.")

        catalog_cases = []
        seen: set[str] = set()
        for case in golden["cases"]:
            if not isinstance(case, dict) or not isinstance(case.get("input"), dict):
                raise ValueError("Invalid synthetic case.")
            case_id = case.get("id")
            title = case.get("title")
            if (
                not isinstance(case_id, str)
                or not re.fullmatch(r"ORS-[0-9]{3}", case_id)
                or case_id in seen
                or not isinstance(title, str)
                or not 1 <= len(title) <= 120
                or not title.isprintable()
            ):
                raise ValueError("Invalid synthetic case identity.")
            seen.add(case_id)
            inputs = case["input"]
            order_id = inputs.get("order")
            if not isinstance(order_id, str) or not re.fullmatch(
                r"ORDER-[A-Za-z0-9][A-Za-z0-9._-]{0,99}", order_id
            ):
                raise ValueError("Invalid synthetic order identifier.")
            facts = contract["orders"].get(order_id)
            if not isinstance(facts, dict):
                raise ValueError("Synthetic order facts are unavailable.")
            amount = facts.get("amount")
            issue = facts.get("issue")
            if (
                not isinstance(amount, str)
                or not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,2})?", amount)
                or Decimal(amount) <= 0
                or issue not in ("late_delivery", "damaged_item")
            ):
                raise ValueError("Invalid synthetic order facts.")
            order: dict[str, object] = {
                "id": order_id,
                "amount": amount,
                "currency": "USD",
                "issue": issue,
            }
            if issue == "late_delivery":
                delay = facts.get("delay_days")
                if not isinstance(delay, int) or isinstance(delay, bool) or delay <= 3:
                    raise ValueError("Invalid synthetic delay.")
                order["delay_days"] = delay
            elif "delay_days" in facts:
                raise ValueError("Invalid damaged-order facts.")

            variants: list[tuple[str | None, list[dict]]]
            if "policy_evidence_variants" in inputs:
                source = inputs["policy_evidence_variants"]
                if (
                    "policy_evidence" in inputs
                    or not isinstance(source, list)
                    or not 1 <= len(source) <= 10
                ):
                    raise ValueError("Invalid synthetic evidence variants.")
                variants = []
                reasons: set[str] = set()
                for item in source:
                    if not isinstance(item, dict):
                        raise ValueError("Invalid synthetic evidence variant.")
                    reason = item.get("invalid_reason")
                    if reason not in ("digest-invalid", "expired", "non-applicable") or reason in reasons:
                        raise ValueError("Unsupported synthetic evidence variant.")
                    reasons.add(reason)
                    variants.append((reason, [_catalog_evidence(item, reason)]))
            else:
                evidence = inputs.get("policy_evidence")
                if not isinstance(evidence, list) or len(evidence) > 16:
                    raise ValueError("Invalid synthetic evidence inputs.")
                variants = [(None, [_catalog_evidence(item) for item in evidence])]

            for reason, evidence in variants:
                identifier = f"{case_id}-{reason}" if reason else case_id
                fields = [
                    {"label": "Order", "value": order_id},
                    {"label": "Issue", "value": issue.replace("_", " ")},
                    {"label": "Order amount", "value": f"USD {amount}"},
                    {"label": "Synthetic policy inputs", "value": str(len(evidence))},
                ]
                if "delay_days" in order:
                    fields.append({"label": "Delay", "value": f"{order['delay_days']} days"})
                if reason:
                    fields.append({"label": "Synthetic variation", "value": reason})
                catalog_cases.append(
                    {
                        "id": identifier,
                        "title": f"{title} ({reason})" if reason else title,
                        "payload": {"order": order, "policy_evidence": evidence},
                        "fields": fields,
                    }
                )
        return {
            "schema_version": CATALOG_SCHEMA,
            "status": "available",
            "scenario_set": ORDER_RESOLUTION_SCENARIO_SET,
            "cases": catalog_cases,
        }
    except (OSError, UnicodeError, json.JSONDecodeError, InvalidOperation, ValueError, TypeError):
        # A caller-selected unsupported fixture must never fall back to another catalog.
        return _unavailable_catalog()


def _relative_sibling_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level != 1:
            continue
        imported = (
            (node.module.split(".", 1)[0],)
            if node.module
            else tuple(alias.name.split(".", 1)[0] for alias in node.names)
        )
        modules.update(f"{name}.py" for name in imported)
    return modules


def _order_resolution_api_bridge_files(source: Path) -> tuple[str, ...]:
    pending = [ORDER_RESOLUTION_API_BRIDGE_ENTRYPOINT]
    required: set[str] = set()
    while pending:
        name = pending.pop()
        if name in required:
            continue
        path = source / name
        if not path.is_file():
            raise ValueError(
                f"The Order Resolution API bridge source is missing: {name}"
            )
        required.add(name)
        for dependency in _relative_sibling_modules(path):
            if not (source / dependency).is_file():
                raise ValueError(
                    "The Order Resolution API bridge has a missing sibling "
                    f"dependency: {name} -> {dependency}"
                )
            pending.append(dependency)

    manifest = set(ORDER_RESOLUTION_API_BRIDGE_MODULES)
    if required != manifest:
        missing = sorted(required - manifest)
        unrelated = sorted(manifest - required)
        raise ValueError(
            "The Order Resolution API bridge manifest does not match its local "
            f"import graph; missing={missing}, unrelated={unrelated}."
        )
    return ORDER_RESOLUTION_API_BRIDGE_MODULES


def _order_resolution_asset(
    override: Path | None, canonical: Path, option: str
) -> Path:
    source = override.resolve() if override is not None else canonical
    if not source.is_file():
        raise ValueError(
            f"The Order Resolution profile requires {canonical.name}. "
            f"Pass {option} until the canonical scenario asset is available."
        )
    return source


def _configure_order_resolution(destination: Path) -> None:
    compose = destination / "compose.yaml"
    text = compose.read_text(encoding="utf-8")
    required = (
        "BLUEPRINT_APPLICATION: ${BLUEPRINT_APPLICATION:?Select an application factory}"
    )
    selected = (
        "BLUEPRINT_APPLICATION: "
        "${BLUEPRINT_APPLICATION:-app.order_resolution.application:build_application}"
    )
    if text.count(required) != 1:
        raise ValueError("The base Compose application selection is not recognized.")
    compose.write_text(text.replace(required, selected), encoding="utf-8")


def _merge_order_resolution_backend(destination: Path) -> None:
    source = ORDER_RESOLUTION_PROFILE / "backend"
    if source.is_dir():
        shutil.copytree(
            source, destination / "backend", dirs_exist_ok=True, ignore=IGNORE
        )


def _merge_order_resolution_verification(verification: Path) -> None:
    source = ORDER_RESOLUTION_PROFILE / "verification"
    if source.is_dir():
        shutil.copytree(source, verification, dirs_exist_ok=True, ignore=IGNORE)


def _merge_order_resolution_hosted_agent(destination: Path) -> None:
    if not ORDER_RESOLUTION_HOSTED_AGENT.is_dir():
        raise ValueError("The Order Resolution hosted-agent package is missing.")
    shutil.copytree(
        ORDER_RESOLUTION_HOSTED_AGENT,
        destination / "hosted-agent",
        dirs_exist_ok=True,
        ignore=IGNORE,
    )
    if not ORDER_RESOLUTION_FOUNDRY_SCRIPT.is_file():
        raise ValueError("The Order Resolution Foundry publisher is missing.")
    scripts = destination / "scripts" / "foundry"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ORDER_RESOLUTION_FOUNDRY_SCRIPT,
        scripts / ORDER_RESOLUTION_FOUNDRY_SCRIPT.name,
    )


def _merge_order_resolution_api_bridge(destination: Path) -> None:
    source = ORDER_RESOLUTION_HOSTED_AGENT / "src" / "order_resolution_hosted"
    target = destination / "backend" / "order_resolution_hosted"
    target.mkdir(parents=True, exist_ok=True)
    for name in _order_resolution_api_bridge_files(source):
        path = source / name
        shutil.copy2(path, target / name)
    (target / "__init__.py").write_text(
        '"""API-only Responses bridge; the full hosted runtime is packaged separately."""\n',
        encoding="utf-8",
    )

    dockerfile = destination / "backend" / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    app_copy = "COPY --chown=blueprint:blueprint app/ app/"
    bridge_copy = (
        f"{app_copy}\n"
        "COPY --chown=blueprint:blueprint order_resolution_hosted/ order_resolution_hosted/"
    )
    if text.count(app_copy) != 1 or "order_resolution_hosted/" in text:
        raise ValueError(
            "The generated backend Docker copy contract is not recognized."
        )
    dockerfile.write_text(text.replace(app_copy, bridge_copy), encoding="utf-8")


def instantiate(
    destination: Path,
    *,
    profile: str | None = None,
    order_resolution_contract: Path | None = None,
    order_resolution_cases: Path | None = None,
    order_resolution_test: Path | None = None,
) -> Path:
    destination = destination.resolve()
    if destination.is_relative_to(ROOT.resolve()):
        raise ValueError("The destination must be outside the blueprint repository.")
    if destination.exists():
        raise ValueError("The destination must not already exist.")
    if not destination.parent.is_dir():
        raise ValueError("The destination's parent directory must already exist.")
    if profile not in (None, "order-resolution"):
        raise ValueError(f"Unknown profile: {profile}")
    if (
        order_resolution_contract is not None
        or order_resolution_cases is not None
        or order_resolution_test is not None
    ) and profile != "order-resolution":
        raise ValueError(
            "Order Resolution scenario overrides require --profile order-resolution."
        )
    contract = (
        _order_resolution_asset(
            order_resolution_contract,
            ORDER_RESOLUTION_CONTRACT,
            "--order-resolution-contract",
        )
        if profile == "order-resolution"
        else None
    )
    cases = (
        _order_resolution_asset(
            order_resolution_cases,
            ORDER_RESOLUTION_CASES,
            "--order-resolution-cases",
        )
        if profile == "order-resolution"
        else None
    )
    contract_test = (
        _order_resolution_asset(
            order_resolution_test,
            ORDER_RESOLUTION_TEST,
            "--order-resolution-test",
        )
        if profile == "order-resolution"
        else None
    )

    shutil.copytree(BLUEPRINT, destination, ignore=IGNORE)
    if profile == "order-resolution":
        shutil.copytree(
            ORDER_RESOLUTION_OVERLAY, destination, dirs_exist_ok=True, ignore=IGNORE
        )
        _merge_order_resolution_backend(destination)
        _merge_order_resolution_hosted_agent(destination)
        _merge_order_resolution_api_bridge(destination)
        _configure_order_resolution(destination)
    verification = destination / "verification"
    verification.mkdir()
    for name in ("readiness", "contracts"):
        shutil.copytree(ROOT / name, verification / name, ignore=IGNORE)
    (verification / "scenarios").mkdir()
    shutil.copytree(
        ROOT / "scenarios" / "order-adjustment",
        verification / "scenarios" / "order-adjustment",
        ignore=IGNORE,
    )
    if contract is not None and cases is not None:
        order_resolution = verification / "scenarios" / "order-resolution"
        order_resolution.mkdir()
        shutil.copy2(contract, order_resolution / "acceptance-contract.json")
        shutil.copy2(cases, order_resolution / "golden-cases.json")
        catalog = destination / "frontend" / "src" / "order-resolution-use-cases.json"
        catalog.write_text(
            json.dumps(_order_resolution_catalog(contract, cases), ensure_ascii=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        _merge_order_resolution_verification(verification)
    (verification / "tests").mkdir()
    for name in (
        "test_contracts.py",
        "test_golden_scenario.py",
        "test_readiness.py",
        "test_release_evidence.py",
    ):
        shutil.copy2(ROOT / "tests" / name, verification / "tests" / name)
    if contract_test is not None:
        shutil.copy2(
            contract_test,
            verification / "tests" / "test_order_resolution_contract.py",
        )
    (verification / "docs").mkdir()
    shutil.copy2(
        ROOT / "docs" / "readiness-validator.md",
        verification / "docs" / "readiness-validator.md",
    )
    shutil.copy2(ROOT / "requirements-dev.txt", verification / "requirements-dev.txt")
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")
    attributes = [
        "verification/scenarios/order-adjustment/verification-contract.json -text",
    ]
    if profile == "order-resolution":
        attributes.append(
            "verification/scenarios/order-resolution/verification-contract.json -text"
        )
    (destination / ".gitattributes").write_text(
        "\n".join(attributes) + "\n",
        encoding="utf-8",
    )
    with (destination / ".gitignore").open("a", encoding="utf-8") as file:
        file.write("\nverification/evidence/\nverification/readiness-report.json\n")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "destination", type=Path, help="A new directory outside this repository."
    )
    parser.add_argument(
        "--profile",
        choices=("order-resolution",),
        help="Apply one explicit application overlay after copying the base MAF workflow.",
    )
    parser.add_argument(
        "--order-resolution-contract",
        type=Path,
        help="Order Resolution acceptance contract to copy into generated verification assets.",
    )
    parser.add_argument(
        "--order-resolution-cases",
        type=Path,
        help="Order Resolution golden cases to copy into generated verification assets.",
    )
    parser.add_argument(
        "--order-resolution-test",
        type=Path,
        help="Order Resolution contract test to copy into generated verification assets.",
    )
    args = parser.parse_args()
    try:
        destination = instantiate(
            args.destination,
            profile=args.profile,
            order_resolution_contract=args.order_resolution_contract,
            order_resolution_cases=args.order_resolution_cases,
            order_resolution_test=args.order_resolution_test,
        )
    except (OSError, ValueError) as error:
        print(f"Instantiation failed: {error}", file=sys.stderr)
        return 1
    print(f"Created independent blueprint project at {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
