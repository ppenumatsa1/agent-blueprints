"""Copy the MAF workflow blueprint and its independent verification assets."""

import argparse
import ast
import shutil
import sys
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
