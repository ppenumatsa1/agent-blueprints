"""Offline Bicep and azd configuration checks; never contacts Azure."""

import argparse
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
MINIMUM_BICEP = (0, 49, 2)


class ValidationError(ValueError):
    pass


def compiler_version(executable: str) -> tuple[int, int, int] | None:
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", result.stdout)
    return tuple(map(int, match.groups())) if match else None


def find_compiler() -> str:
    explicit = os.environ.get("BICEP_CLI")
    if explicit:
        if (compiler_version(explicit) or (0, 0, 0)) < MINIMUM_BICEP:
            raise ValidationError("BICEP_CLI must point to Bicep 0.49.2 or newer.")
        return explicit
    candidates = [
        shutil.which("bicep"),
        str(Path.home() / ".azure" / "bin" / ("bicep.exe" if os.name == "nt" else "bicep")),
    ]
    for candidate in candidates:
        if candidate and (compiler_version(candidate) or (0, 0, 0)) >= MINIMUM_BICEP:
            return candidate
    raise ValidationError("Bicep 0.49.2 or newer is required; no compatible compiler was found.")


def run_compiler(executable: str, *arguments: str) -> str:
    result = subprocess.run(
        [executable, *arguments, "--no-restore"],
        cwd=INFRA,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or result.stderr.strip():
        raise ValidationError(
            f"Bicep {' '.join(arguments)} failed or emitted diagnostics:\n{result.stderr.strip()}"
        )
    return result.stdout


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"Cannot read {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise ValidationError(f"{path.name} must contain an object.")
    return value


def local_path(root: Path, base: Path, value: str, kind: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{kind} must be a nonempty local path.")
    path = (base / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValidationError(f"{kind} must stay within the generated project.")
    return path


def validate_azd_configuration(root: Path, config: dict, template: dict) -> None:
    infra = config.get("infra", {})
    if infra.get("provider") != "bicep" or infra.get("module") != "main":
        raise ValidationError("azure.yaml must select the local main Bicep module.")
    infra_path = local_path(root, root, infra.get("path"), "Infrastructure path")
    if not (infra_path / "main.bicep").is_file():
        raise ValidationError("The configured Bicep entry point does not exist.")
    services = config.get("services", {})
    if set(services) != {"api", "web"}:
        raise ValidationError("The staged azd configuration must contain only the API and web services.")
    for name, service in services.items():
        if service.get("host") != "containerapp" or service.get("language") != "docker":
            raise ValidationError(f"{name} must use its local Dockerfile for Container Apps.")
        project = local_path(root, root, service.get("project"), f"{name} project")
        dockerfile = local_path(root, project, service.get("docker", {}).get("path"), f"{name} Dockerfile")
        if not project.is_dir() or not dockerfile.is_file() or not dockerfile.is_relative_to(project):
            raise ValidationError(f"{name} must have a Dockerfile inside its own project.")

    binding = read_json(infra_path / "main.parameters.json")
    parameters = binding.get("parameters", {})
    required = {name for name, item in template["parameters"].items() if "defaultValue" not in item}
    if set(parameters) != required:
        raise ValidationError("azd parameter bindings must cover exactly the required Bicep inputs.")
    for name, item in parameters.items():
        if set(item) != {"value"} or not re.fullmatch(r"\$\{[A-Z][A-Z0-9_]*\}", item["value"]):
            raise ValidationError(f"{name} must bind to a non-secret environment variable placeholder.")


def validate_networks(values: dict) -> None:
    try:
        vnet = ipaddress.ip_network(values["networkAddressPrefix"], strict=True)
        apps = ipaddress.ip_network(values["appsSubnetPrefix"], strict=True)
        postgres = ipaddress.ip_network(values["postgresSubnetPrefix"], strict=True)
    except (KeyError, ValueError, TypeError) as error:
        raise ValidationError(f"Invalid network configuration: {error}") from error
    rfc1918 = tuple(
        ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    )
    if any(network.version != 4 for network in (vnet, apps, postgres)):
        raise ValidationError("Only RFC1918 IPv4 networks are supported by this configuration.")
    if (
        not any(vnet.subnet_of(private) for private in rfc1918)
        or not apps.subnet_of(vnet)
        or not postgres.subnet_of(vnet)
        or apps.overlaps(postgres)
        or apps.prefixlen > 27
        or postgres.prefixlen > 28
    ):
        raise ValidationError("Subnets must be non-overlapping RFC1918 IPv4 ranges with sufficient capacity.")


def validate_examples(executable: str, template: dict) -> None:
    defaults = {
        name: spec["defaultValue"]
        for name, spec in template["parameters"].items()
        if "defaultValue" in spec
    }
    for filename in ("dev.example.bicepparam", "prod.example.bicepparam"):
        output = run_compiler(executable, "build-params", str(Path("environments") / filename), "--stdout")
        compiled = json.loads(output)
        parameters = json.loads(compiled["parametersJson"])["parameters"]
        values = {**defaults, **{name: item["value"] for name, item in parameters.items()}}
        validate_networks(values)
        for option in ("deployModel", "grantProjectAgentConsumer", "createRegistry", "createContainerApps"):
            if values.get(option) is not False:
                raise ValidationError(f"{filename} must leave {option} disabled.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-compiler", action="store_true", help="Only check the compiler prerequisite.")
    args = parser.parse_args()
    try:
        compiler = find_compiler()
        if args.check_compiler:
            print(f"Bicep compiler available: {compiler}")
            return 0
        output = run_compiler(compiler, "build", "main.bicep", "--stdout")
        template = json.loads(output)
        run_compiler(compiler, "lint", "main.bicep")
        validate_azd_configuration(ROOT, read_json(ROOT / "azure.yaml"), template)
        validate_examples(compiler, template)
    except (ValidationError, OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"Offline infrastructure validation failed: {error}", file=sys.stderr)
        return 1
    print("Bicep compilation, lint, parameter examples and local azd paths passed offline.")
    print("Hosted-agent binding, cloud connectivity, authorization and deployment remain unverified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
