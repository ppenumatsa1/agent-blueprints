"""Operator-only Docker boundary for the bundled synthetic native MAF test."""

import argparse
from functools import cache
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
BUILD_FILES = (
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/.python-version",
    "backend/agent-framework-core.sha256",
    "backend/scripts/verify_framework_supply_chain.py",
    "backend/app/__init__.py",
    "backend/app/domain/__init__.py",
    "backend/app/domain/models.py",
    "backend/app/workflows/__init__.py",
    "backend/app/workflows/workflow.py",
    "scripts/offline/Dockerfile",
    "scripts/offline/LICENSE",
    "scripts/offline/runner.py",
)


def _client(*arguments: str, timeout: int = 60) -> str:
    # Docker's selected local context is operator-owned. Never forward app credentials,
    # proxy settings, PYTHONPATH, or Docker endpoint overrides from the caller.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
    }
    try:
        return subprocess.run(
            ["docker", *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env=environment,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"Docker {arguments[0]} failed:\n{error.stdout}\n{error.stderr}"
        ) from error


@cache
def local_endpoint() -> str:
    endpoint = json.loads(
        _client("context", "inspect", "--format", "{{json .Endpoints.docker.Host}}")
    )
    if not isinstance(endpoint, str) or not (
        endpoint.startswith("unix:///") or endpoint.startswith("npipe:////./pipe/")
    ):
        raise RuntimeError("Only an operator-owned local Unix socket or named pipe is supported")
    return endpoint


def docker(*arguments: str, timeout: int = 60) -> str:
    return _client("--host", local_endpoint(), *arguments, timeout=timeout)


def build_image(package_index: str = "https://pypi.org/simple") -> str:
    parsed = urlsplit(package_index)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("The package index must be an HTTPS URL without credentials or query")
    with tempfile.TemporaryDirectory(prefix="maf-offline-build-") as directory:
        context = Path(directory)
        for name in BUILD_FILES:
            source = ROOT / name
            if source.is_symlink() or not source.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError(f"Build input must be a regular in-project file: {name}")
            target = context / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        iid = context / "image-id"
        docker(
            "build",
            "--build-arg",
            f"PYTHON_PACKAGE_INDEX={package_index}",
            "--file",
            str(context / "scripts" / "offline" / "Dockerfile"),
            "--iidfile",
            str(iid),
            str(context),
            timeout=900,
        )
        image = iid.read_text(encoding="ascii").strip()
        if not image.startswith("sha256:") or len(image) != 71:
            raise RuntimeError("Docker did not return an immutable image ID")
        return image


def create_container(image: str, decision: str) -> str:
    if decision not in ("approved", "rejected"):
        raise ValueError("Only bundled approval/rejection decisions are supported")
    return docker(
        "create",
        "--network",
        "none",
        "--read-only",
        "--user",
        "65534:65534",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--memory",
        "512m",
        "--memory-swap",
        "512m",
        "--cpus",
        "1",
        "--pids-limit",
        "64",
        "--ulimit",
        "nofile=256:256",
        "--log-driver",
        "none",
        image,
        decision,
    )


def verify_container(container: dict, image: str, decision: str) -> None:
    host = container["HostConfig"]
    config = container["Config"]
    expected = {
        "NetworkMode": "none",
        "ReadonlyRootfs": True,
        "Privileged": False,
        "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges=true"],
        "Memory": 512 * 1024 * 1024,
        "MemorySwap": 512 * 1024 * 1024,
        "NanoCpus": 1_000_000_000,
        "PidsLimit": 64,
    }
    if any(host.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Container isolation settings do not match the fixed policy")
    if (
        container["Image"] != image
        or container["State"]["Status"] != "created"
        or container.get("Mounts")
        or config.get("Volumes")
        or config.get("ExposedPorts")
        or config.get("OpenStdin")
        or config.get("Tty")
        or config.get("User") != "65534:65534"
        or config.get("Entrypoint") != ["/usr/local/bin/python", "-I", "-B", "/offline/runner.py"]
        or config.get("Cmd") != [decision]
        or any(
            entry.split("=", 1)[0]
            not in {
                "PATH",
                "LANG",
                "GPG_KEY",
                "PYTHON_VERSION",
                "PYTHON_SHA256",
                "PYTHONDONTWRITEBYTECODE",
            }
            for entry in config.get("Env", [])
        )
        or any(
            host.get(key)
            for key in (
                "Binds",
                "Mounts",
                "Tmpfs",
                "PortBindings",
                "CapAdd",
                "Devices",
                "DeviceRequests",
                "VolumesFrom",
                "ExtraHosts",
                "Links",
                "PidMode",
                "UTSMode",
            )
        )
        or host.get("IpcMode") != "private"
        or host.get("LogConfig", {}).get("Type") != "none"
    ):
        raise RuntimeError("Container includes an unexpected execution capability")


def run_test(image: str, decision: str) -> dict:
    identifier = create_container(image, decision)
    try:
        container = json.loads(docker("inspect", identifier))[0]
        verify_container(container, image, decision)
        output = docker("start", "--attach", identifier, timeout=60)
        state = json.loads(docker("inspect", identifier))[0]["State"]
        if state["ExitCode"] != 0 or state["OOMKilled"]:
            raise RuntimeError("Synthetic runner failed; no successful result is available")
        result = json.loads(output)
        if result != {
            "kind": "offline-synthetic-native-approval",
            "decision": decision,
            "requests": 1,
            "records": 1,
            "business_effects": 0,
            "isolation_probes": "passed",
            "durable": False,
        }:
            raise RuntimeError("Unexpected synthetic runner output")
        return result
    finally:
        # Also terminates a timed-out runner; cleanup failure is not hidden.
        docker("rm", "--force", identifier)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", choices=("approved", "rejected", "both"), default="both")
    parser.add_argument("--package-index", default="https://pypi.org/simple")
    arguments = parser.parse_args()
    image = build_image(arguments.package_index)
    decisions = ("approved", "rejected") if arguments.decision == "both" else (arguments.decision,)
    for decision in decisions:
        print(json.dumps({"image": image, **run_test(image, decision)}, sort_keys=True))


if __name__ == "__main__":
    main()
