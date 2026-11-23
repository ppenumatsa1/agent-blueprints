#!/usr/bin/env python3
"""Set the explicit Container Apps authentication client allowlist."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys


_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)


class AuthConfigurationError(RuntimeError):
    pass


def _run(arguments: list[str], *, body: dict | None = None) -> dict:
    az = shutil.which("az")
    if az is None:
        raise AuthConfigurationError("Azure CLI is unavailable.")
    command = [az, "rest", *arguments, "--output", "json", "--only-show-errors"]
    if body is not None:
        command.extend(["--body", json.dumps(body, separators=(",", ":"))])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise AuthConfigurationError("Container Apps authentication update failed.")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise AuthConfigurationError(
            "Container Apps authentication returned an invalid body."
        )
    return value


def configure(
    resource_url: str,
    allowed_applications: list[str],
) -> dict:
    normalized = sorted(set(allowed_applications), key=str.casefold)
    if not normalized or any(not _UUID.fullmatch(value) for value in normalized):
        raise AuthConfigurationError(
            "Allowed applications must be distinct UUID client IDs."
        )
    current = _run(["--method", "get", "--url", resource_url])
    properties = current.get("properties")
    if not isinstance(properties, dict):
        raise AuthConfigurationError(
            "Container Apps authentication properties are unavailable."
        )
    provider = properties.get("identityProviders", {}).get("azureActiveDirectory", {})
    if not provider.get("registration", {}).get("clientId"):
        raise AuthConfigurationError(
            "Microsoft Entra authentication is not configured."
        )
    validation = provider.setdefault("validation", {})
    policy = validation.setdefault("defaultAuthorizationPolicy", {})
    policy["allowedApplications"] = normalized
    updated = _run(
        ["--method", "put", "--url", resource_url],
        body={"properties": properties},
    )
    persisted = (
        updated.get("properties", {})
        .get("identityProviders", {})
        .get("azureActiveDirectory", {})
        .get("validation", {})
        .get("defaultAuthorizationPolicy", {})
        .get("allowedApplications")
    )
    if sorted(persisted or [], key=str.casefold) != normalized:
        raise AuthConfigurationError(
            "Container Apps authentication did not persist the allowlist."
        )
    return {"allowedApplications": normalized}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subscription", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--allowed-application", action="append", required=True)
    args = parser.parse_args()
    resource_url = (
        "https://management.azure.com/subscriptions/"
        f"{args.subscription}/resourceGroups/{args.resource_group}/providers/"
        f"Microsoft.App/containerApps/{args.app_name}/authConfigs/current"
        "?api-version=2024-03-01"
    )
    try:
        result = configure(resource_url, args.allowed_application)
        print(json.dumps(result, sort_keys=True))
    except (
        AuthConfigurationError,
        json.JSONDecodeError,
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"Authentication client configuration failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
