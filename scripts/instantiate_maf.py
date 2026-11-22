"""Copy the MAF workflow blueprint and its independent verification assets."""

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprints" / "maf" / "workflow"
ORDER_RESOLUTION_PROFILE = ROOT / "profiles" / "order-resolution"
ORDER_RESOLUTION_OVERLAY = ORDER_RESOLUTION_PROFILE / "overlay"
ORDER_RESOLUTION_CONTRACT = (
    ROOT / "scenarios" / "order-resolution" / "acceptance-contract.json"
)
ORDER_RESOLUTION_CASES = ROOT / "scenarios" / "order-resolution" / "golden-cases.json"
ORDER_RESOLUTION_TEST = ROOT / "tests" / "test_order_resolution_contract.py"
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
