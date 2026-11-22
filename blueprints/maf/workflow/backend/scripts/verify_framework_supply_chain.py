"""Verify the approved Microsoft Agent Framework core wheel before installation."""

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path


CORE_PIN = re.compile(r"^agent-framework-core==(?P<version>[A-Za-z0-9.!+_-]+)$")
UMBRELLA_PACKAGE = re.compile(r"^agent-framework(?:\[[^\]]+\])?(?:$|[<>=!~])", re.IGNORECASE)


def verify_manifests(backend_root: Path) -> str:
    pins: list[str] = []
    for manifest in sorted(backend_root.glob("requirements*.txt")):
        for raw_line in manifest.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            if UMBRELLA_PACKAGE.match(line):
                raise ValueError(f"Disallowed umbrella distribution in {manifest.name}: {line}")
            match = CORE_PIN.fullmatch(line)
            if match:
                pins.append(match.group("version"))
    if pins != ["1.26.0"]:
        raise ValueError("requirements.txt must contain exactly agent-framework-core==1.26.0")
    return pins[0]


def read_approval(backend_root: Path, version: str) -> tuple[str, str]:
    approval = backend_root / "agent-framework-core.sha256"
    fields = approval.read_text(encoding="ascii").strip().split()
    expected_filename = f"agent_framework_core-{version}-py3-none-any.whl"
    if len(fields) != 2 or fields[1] != expected_filename:
        raise ValueError("The approved Agent Framework core hash entry is malformed.")
    digest = fields[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("The approved Agent Framework core SHA-256 is malformed.")
    return expected_filename, digest


def verify_wheel(wheel: Path, expected_digest: str) -> None:
    actual_digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if actual_digest != expected_digest:
        raise ValueError(
            f"Agent Framework core wheel digest mismatch: expected {expected_digest}, "
            f"received {actual_digest}"
        )


def download_and_verify(
    backend_root: Path,
    output_dir: Path,
    index_url: str | None,
) -> Path:
    version = verify_manifests(backend_root)
    filename, digest = read_approval(backend_root, version)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError(f"Output directory must be empty: {output_dir}")
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--no-deps",
        "--dest",
        str(output_dir),
    ]
    if index_url:
        command.extend(["--index-url", index_url])
    command.append(f"agent-framework-core=={version}")
    subprocess.run(command, check=True)
    wheel = output_dir / filename
    if not wheel.is_file() or len(list(output_dir.iterdir())) != 1:
        raise ValueError("The approved Agent Framework core wheel was not downloaded exactly once.")
    verify_wheel(wheel, digest)
    print(f"Verified agent-framework-core=={version} ({digest}).")
    return wheel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Backend directory containing requirements and the approved hash.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Empty directory in which to retain the verified wheel.",
    )
    parser.add_argument("--index-url", help="Optional package index URL.")
    args = parser.parse_args()
    try:
        if args.output_dir:
            download_and_verify(args.backend_root.resolve(), args.output_dir.resolve(), args.index_url)
        else:
            with tempfile.TemporaryDirectory() as temporary:
                download_and_verify(
                    args.backend_root.resolve(),
                    Path(temporary),
                    args.index_url,
                )
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Agent Framework supply-chain verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
