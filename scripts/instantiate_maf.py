"""Copy the MAF workflow blueprint and its independent verification assets."""

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "blueprints" / "maf" / "workflow"
IGNORE = shutil.ignore_patterns(
    ".git", ".env", ".env.*", ".venv", "__pycache__", "*.pyc", "node_modules", "dist", "coverage"
)


def instantiate(destination: Path) -> Path:
    destination = destination.resolve()
    if destination.is_relative_to(ROOT.resolve()):
        raise ValueError("The destination must be outside the blueprint repository.")
    if destination.exists():
        raise ValueError("The destination must not already exist.")
    if not destination.parent.is_dir():
        raise ValueError("The destination's parent directory must already exist.")

    shutil.copytree(BLUEPRINT, destination, ignore=IGNORE)
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
    (verification / "tests").mkdir()
    for name in ("test_contracts.py", "test_golden_scenario.py", "test_readiness.py"):
        shutil.copy2(ROOT / "tests" / name, verification / "tests" / name)
    (verification / "docs").mkdir()
    shutil.copy2(ROOT / "docs" / "readiness-validator.md", verification / "docs" / "readiness-validator.md")
    shutil.copy2(ROOT / "requirements-dev.txt", verification / "requirements-dev.txt")
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")
    (destination / ".gitattributes").write_text(
        "verification/scenarios/order-adjustment/verification-contract.json -text\n", encoding="utf-8"
    )
    with (destination / ".gitignore").open("a", encoding="utf-8") as file:
        file.write("\nverification/evidence/\nverification/readiness-report.json\n")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="A new directory outside this repository.")
    args = parser.parse_args()
    try:
        destination = instantiate(args.destination)
    except (OSError, ValueError) as error:
        print(f"Instantiation failed: {error}", file=sys.stderr)
        return 1
    print(f"Created independent blueprint project at {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
