#!/usr/bin/env python3
"""Verify exact Azure revisions, Foundry deployment identity, and public health endpoints."""

from __future__ import annotations

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


def required(values: dict[str, str], name: str) -> str:
    value = values.get(name, "")
    if not value:
        raise VerificationError(f"Missing azd environment value: {name}")
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
    return {"name": name, "revision": revision_name, "image": image, "fqdn": fqdn}


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
    try:
        values = azd_values()
        subscription = required(values, "AZURE_SUBSCRIPTION_ID")
        resource_group = required(values, "AZURE_RESOURCE_GROUP")
        api_name = required(values, "AZURE_API_CONTAINER_APP_NAME")
        web_name = required(values, "AZURE_WEB_CONTAINER_APP_NAME")
        account_name = required(values, "AZURE_AI_ACCOUNT_NAME")
        project_name = required(values, "AZURE_AI_PROJECT_NAME")
        model_name = required(values, "AZURE_AI_MODEL_DEPLOYMENT_NAME")

        api = verify_container_app(subscription, resource_group, api_name)
        web = verify_container_app(subscription, resource_group, web_name)
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
