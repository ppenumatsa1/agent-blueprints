#!/usr/bin/env python3
"""Verify exact Azure revisions, Foundry deployment identity, and public health endpoints."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


class VerificationError(RuntimeError):
    pass


AZ = shutil.which("az") or "az"
AZD = shutil.which("azd") or "azd"


def command_json(*arguments: str) -> Any:
    result = subprocess.run(
        [AZ, *arguments, "--only-show-errors", "--output", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise VerificationError(f"Azure verification failed: {' '.join(arguments[:4])}")
    return json.loads(result.stdout)


def azd_values() -> dict[str, str]:
    environment = {**os.environ, "AZURE_DEV_USER_AGENT": "microsoft_foundry_skill"}
    result = subprocess.run(
        [AZD, "env", "get-values", "--no-prompt"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if result.returncode:
        raise VerificationError("Unable to read the selected azd environment.")
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, separator, raw = line.partition("=")
        if separator:
            parts = shlex.split(raw)
            values[name] = parts[0] if parts else ""
    return values


def load_values(deployment_mode: str, values_file: str | None) -> dict[str, str]:
    if deployment_mode == "azd":
        return azd_values()
    if not values_file:
        raise VerificationError("--values-file is required in azure-cli mode.")
    payload = json.loads(open(values_file, encoding="utf-8").read())
    if not isinstance(payload, dict):
        raise VerificationError("The deployment values file must contain one object.")
    return {str(name): str(value) for name, value in payload.items()}


def required(values: dict[str, str], name: str) -> str:
    value = values.get(name, "")
    if not value:
        raise VerificationError(f"Missing deployment value: {name}")
    return value


def verify_container_app(subscription: str, resource_group: str, name: str) -> dict[str, str]:
    app = command_json(
        "containerapp",
        "show",
        "--subscription",
        subscription,
        "--resource-group",
        resource_group,
        "--name",
        name,
    )
    revisions = command_json(
        "containerapp",
        "revision",
        "list",
        "--subscription",
        subscription,
        "--resource-group",
        resource_group,
        "--name",
        name,
    )
    active = [
        item
        for item in revisions
        if item.get("active") is True
        or (item.get("properties") or {}).get("active") is True
    ]
    if len(active) != 1:
        raise VerificationError(f"{name} must have exactly one active revision.")
    revision = active[0]
    properties = app.get("properties") or {}
    revision_properties = revision.get("properties") or {}
    running = str(
        revision.get("runningState") or revision_properties.get("runningState") or ""
    ).casefold()
    health = str(
        revision.get("healthState") or revision_properties.get("healthState") or ""
    ).casefold()
    latest_ready = str(properties.get("latestReadyRevisionName", ""))
    revision_name = str(revision.get("name", ""))
    if running != "running" or health != "healthy" or revision_name != latest_ready:
        raise VerificationError(f"{name} is not healthy on its latest ready revision.")
    fqdn = str(((properties.get("configuration") or {}).get("ingress") or {}).get("fqdn", ""))
    if not fqdn:
        raise VerificationError(f"{name} has no ingress FQDN.")
    image = str(
        (
            (revision.get("template") or revision_properties.get("template") or {})
            .get("containers", [{}])[0]
            .get("image", "")
        )
    )
    if "@sha256:" not in image:
        raise VerificationError(f"{name} is not running an immutable image digest.")
    return {"name": name, "revision": revision_name, "image": image, "fqdn": fqdn}


def verify_api_runtime(subscription: str, resource_group: str, name: str) -> None:
    app = command_json(
        "containerapp",
        "show",
        "--subscription",
        subscription,
        "--resource-group",
        resource_group,
        "--name",
        name,
    )
    containers = ((app.get("properties") or {}).get("template") or {}).get(
        "containers", []
    )
    environment = {
        item.get("name"): item.get("value", item.get("secretRef"))
        for item in (containers[0].get("env", []) if containers else [])
    }
    if environment.get("WORKFLOW_HOST") != "hosted":
        raise VerificationError("API WORKFLOW_HOST is not hosted.")
    for forbidden in ("CHECKPOINT_ROOT", "BLUEPRINT_APPLICATION"):
        if forbidden in environment:
            raise VerificationError(f"API must not configure {forbidden} in Azure.")
    for required_name in ("HOSTED_WORKFLOW_ENDPOINT", "HOSTED_WORKFLOW_SCOPE"):
        if not environment.get(required_name):
            raise VerificationError(f"API is missing {required_name}.")
    if environment.get("HOSTED_WORKFLOW_SCOPE") != "https://ai.azure.com/.default":
        raise VerificationError("API hosted workflow scope is not the reviewed scope.")
    if environment.get("DATABASE_AUTH_MODE") != "managed-identity":
        raise VerificationError("API database authentication is not managed identity.")
    if environment.get("DATABASE_TLS_MODE") != "verify-full":
        raise VerificationError("API database TLS verification is not enabled.")
    if environment.get("PGSSLROOTCERT") != "system":
        raise VerificationError("API database trust is not bound to the system CA store.")
    if "sslrootcert=system" not in str(environment.get("DATABASE_URL", "")):
        raise VerificationError("API database URL does not require the system CA store.")


def request_status(url: str, expected: set[int]) -> int:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    if status not in expected:
        raise VerificationError(f"{url} returned {status}; expected {sorted(expected)}.")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment-mode", choices=("azure-cli", "azd"), default="azure-cli"
    )
    parser.add_argument("--values-file")
    arguments = parser.parse_args()
    try:
        values = load_values(arguments.deployment_mode, arguments.values_file)
        subscription = required(values, "AZURE_SUBSCRIPTION_ID")
        resource_group = required(values, "AZURE_RESOURCE_GROUP")
        api_name = required(values, "AZURE_API_CONTAINER_APP_NAME")
        web_name = required(values, "AZURE_WEB_CONTAINER_APP_NAME")
        account_name = required(values, "AZURE_AI_ACCOUNT_NAME")
        project_name = required(values, "AZURE_AI_PROJECT_NAME")
        model_name = required(values, "AZURE_AI_MODEL_DEPLOYMENT_NAME")
        for hosted_name in (
            "AZURE_HOSTED_AGENT_VERSION",
            "AZURE_HOSTED_AGENT_VERSION_ID",
            "AZURE_HOSTED_AGENT_GUID",
            "AZURE_HOSTED_AGENT_PRINCIPAL_ID",
            "AZURE_HOSTED_AGENT_CLIENT_ID",
            "AZURE_HOSTED_AGENT_PROVISIONING_STATUS",
            "AZURE_HOSTED_AGENT_RESPONSES_ENDPOINT",
            "AZURE_HOSTED_AGENT_CONVERSATION_ENDPOINT",
            "AZURE_HOSTED_AGENT_ADAPTER_ENDPOINT",
        ):
            required(values, hosted_name)
        if values["AZURE_HOSTED_AGENT_PROVISIONING_STATUS"] != "active":
            raise VerificationError("Hosted Agent version is not active.")

        api = verify_container_app(subscription, resource_group, api_name)
        web = verify_container_app(subscription, resource_group, web_name)
        verify_api_runtime(subscription, resource_group, api_name)
        request_status(f"https://{api['fqdn']}/healthz", {200, 204})
        request_status(f"https://{api['fqdn']}/api/cases", {401, 403})
        request_status(f"https://{web['fqdn']}/", {200})

        project_url = (
            "https://management.azure.com/subscriptions/"
            f"{subscription}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.CognitiveServices/accounts/{account_name}/projects/{project_name}"
            "?api-version=2025-06-01"
        )
        project = command_json("rest", "--method", "get", "--url", project_url)
        deployment = command_json(
            "cognitiveservices",
            "account",
            "deployment",
            "show",
            "--subscription",
            subscription,
            "--resource-group",
            resource_group,
            "--name",
            account_name,
            "--deployment-name",
            model_name,
        )
        if str((project.get("properties") or {}).get("provisioningState", "")).casefold() not in {
            "",
            "succeeded",
        }:
            raise VerificationError("Foundry project is not provisioned successfully.")
        if str((deployment.get("properties") or {}).get("provisioningState", "")).casefold() != (
            "succeeded"
        ):
            raise VerificationError("Foundry model deployment is not provisioned successfully.")
    except (VerificationError, json.JSONDecodeError) as error:
        print(f"Azure health verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "passed", "api": api, "web": web}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
