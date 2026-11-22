#!/usr/bin/env python3
"""Read-only Azure/Foundry preflight that never changes the active subscription."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


class PreflightError(RuntimeError):
    pass


AZ = shutil.which("az") or "az"
AZD = shutil.which("azd") or "azd"


def run_json(*arguments: str) -> Any:
    command = [AZ, *arguments, "--only-show-errors", "--output", "json"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise PreflightError(f"Read-only Azure command failed: {' '.join(command[:5])}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PreflightError(f"Azure returned invalid JSON for {' '.join(command[:5])}") from error


def run_text(*arguments: str) -> str:
    environment = None
    if arguments and arguments[0] == AZD:
        environment = os.environ.copy()
        environment["AZURE_DEV_USER_AGENT"] = "microsoft_foundry_skill"
    result = subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if result.returncode:
        raise PreflightError(f"Read-only command failed: {' '.join(arguments[:4])}")
    return result.stdout.strip()


def decode_azd_token_claims(token_output: str) -> dict[str, Any]:
    token = token_output
    if token_output.lstrip().startswith("{"):
        payload = json.loads(token_output)
        token = str(payload.get("token", payload.get("accessToken", "")))
    parts = token.strip().split(".")
    if len(parts) < 2:
        raise PreflightError("azd returned an unexpected access token format.")
    encoded = parts[1] + ("=" * (-len(parts[1]) % 4))
    try:
        return json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreflightError("azd returned unreadable access token claims.") from error


def normalized(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def usage_name(item: dict[str, Any]) -> str:
    name = item.get("name", "")
    return str(name.get("value", "") if isinstance(name, dict) else name)


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


@dataclass(frozen=True)
class Configuration:
    subscription_id: str
    tenant_id: str
    expected_user: str
    regions: tuple[str, ...]
    model_name: str
    model_version: str
    model_sku: str
    model_capacity: int
    postgres_sku: str
    postgres_tier: str


REQUIRED_PROVIDERS = (
    "Microsoft.App",
    "Microsoft.Authorization",
    "Microsoft.CognitiveServices",
    "Microsoft.ContainerRegistry",
    "Microsoft.DBforPostgreSQL",
    "Microsoft.Insights",
    "Microsoft.KeyVault",
    "Microsoft.ManagedIdentity",
    "Microsoft.OperationalInsights",
    "Microsoft.Resources",
)

REGIONAL_TYPES = (
    ("Microsoft.App", "managedEnvironments"),
    ("Microsoft.App", "containerApps"),
    ("Microsoft.CognitiveServices", "accounts"),
    ("Microsoft.DBforPostgreSQL", "flexibleServers"),
    ("Microsoft.Insights", "components"),
    ("Microsoft.OperationalInsights", "workspaces"),
)


def inspect_azd_identity(active_user: str, tenant_id: str) -> dict[str, Any]:
    try:
        azd_status = run_text(AZD, "auth", "login", "--check-status")
        match = re.search(r"Logged in to Azure as\s+(\S+)", azd_status)
        azd_user = match.group(1) if match else ""
        azd_claims = decode_azd_token_claims(
            run_text(AZD, "auth", "token", "--no-prompt")
        )
    except PreflightError as error:
        return {
            "status": "unavailable",
            "matched": False,
            "message": str(error),
        }

    azd_tenant = str(azd_claims.get("tid", ""))
    token_user = str(
        azd_claims.get("preferred_username")
        or azd_claims.get("upn")
        or azd_claims.get("unique_name")
        or ""
    )
    matched = bool(
        azd_user
        and azd_user.casefold() == active_user.casefold()
        and token_user
        and token_user.casefold() == active_user.casefold()
        and azd_tenant.casefold() == tenant_id.casefold()
    )
    return {
        "status": "matched" if matched else "mismatch",
        "matched": matched,
        "statusUser": azd_user,
        "tokenUser": token_user,
        "tenantId": azd_tenant,
    }


def verify_identity(config: Configuration, identity_mode: str) -> dict[str, Any]:
    account = run_json("account", "show")
    active_user = str((account.get("user") or {}).get("name", ""))
    if str(account.get("id", "")).casefold() != config.subscription_id.casefold():
        raise PreflightError("Azure CLI active subscription does not match the authorized target.")
    if str(account.get("tenantId", "")).casefold() != config.tenant_id.casefold():
        raise PreflightError("Azure CLI tenant does not match the authorized target.")
    if active_user.casefold() != config.expected_user.casefold():
        raise PreflightError("Azure CLI user does not match the authorized target.")

    azd_identity = inspect_azd_identity(active_user, config.tenant_id)
    if identity_mode == "azd" and not azd_identity["matched"]:
        raise PreflightError(
            "Azure CLI and azd account or tenant differ; azd mode must stop."
        )
    return {
        "deploymentMode": identity_mode,
        "azureCliUser": active_user,
        "subscriptionMatched": True,
        "tenantMatched": True,
        "azdIdentity": azd_identity,
    }


def verify_permissions(config: Configuration) -> list[str]:
    principal_id = str(run_json("ad", "signed-in-user", "show").get("id", ""))
    assignments = run_json(
        "role",
        "assignment",
        "list",
        "--assignee",
        principal_id,
        "--include-groups",
        "--include-inherited",
        "--scope",
        f"/subscriptions/{config.subscription_id}",
    )
    roles = sorted(
        {
            str(item.get("roleDefinitionName", ""))
            for item in assignments
            if item.get("roleDefinitionName")
        }
    )
    can_manage_resources = "Owner" in roles or "Contributor" in roles
    can_manage_role_assignments = "Owner" in roles or bool(
        {"Role Based Access Control Administrator", "User Access Administrator"}.intersection(
            roles
        )
    )
    if not can_manage_resources or not can_manage_role_assignments:
        raise PreflightError(
            "Provisioning requires Owner or Contributor plus role-assignment authority."
        )
    return roles


def provider_metadata(config: Configuration) -> dict[str, dict[str, Any]]:
    providers: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for namespace in REQUIRED_PROVIDERS:
        item = run_json(
            "provider",
            "show",
            "--namespace",
            namespace,
            "--subscription",
            config.subscription_id,
        )
        providers[namespace] = item
        if str(item.get("registrationState", "")).casefold() != "registered":
            missing.append(namespace)
    if missing:
        raise PreflightError("Required providers are not registered: " + ", ".join(missing))
    return providers


def supports_type(provider: dict[str, Any], resource_type: str, region: str) -> bool:
    item = next(
        (
            candidate
            for candidate in provider.get("resourceTypes", [])
            if str(candidate.get("resourceType", "")).casefold() == resource_type.casefold()
        ),
        None,
    )
    return bool(item) and normalized(region) in {
        normalized(str(location)) for location in item.get("locations", [])
    }


def postgres_sku_available(payload: Any, sku_name: str, tier: str) -> bool:
    for item in walk_dicts(payload):
        if (
            str(item.get("name", "")).casefold() == sku_name.casefold()
            and str(item.get("tier", item.get("edition", ""))).casefold() == tier.casefold()
        ):
            return True
        editions = item.get("supportedServerEditions")
        if not isinstance(editions, list):
            continue
        for edition in editions:
            if not isinstance(edition, dict) or str(edition.get("name", "")).casefold() != tier.casefold():
                continue
            if any(
                isinstance(sku, dict)
                and str(sku.get("name", "")).casefold() == sku_name.casefold()
                for sku in edition.get("supportedServerSkus", [])
            ):
                return True
    return False


def verify_region(
    config: Configuration, providers: dict[str, dict[str, Any]], region: str
) -> dict[str, Any]:
    unsupported = [
        f"{namespace}/{resource_type}"
        for namespace, resource_type in REGIONAL_TYPES
        if not supports_type(providers[namespace], resource_type, region)
    ]
    if unsupported:
        return {"eligible": False, "reason": "unsupported resource types", "items": unsupported}

    models = run_json(
        "cognitiveservices",
        "model",
        "list",
        "--location",
        region,
        "--subscription",
        config.subscription_id,
    )
    model = next(
        (
            item.get("model", item)
            for item in models
            if str(item.get("model", item).get("name", "")).casefold()
            == config.model_name.casefold()
            and str(item.get("model", item).get("version", "")).casefold()
            == config.model_version.casefold()
        ),
        None,
    )
    if not model:
        return {"eligible": False, "reason": "model version unavailable"}
    capabilities = model.get("capabilities") or {}
    missing_capabilities = [
        capability
        for capability in ("agentsV2", "responses")
        if str(capabilities.get(capability, "")).casefold() != "true"
    ]
    if missing_capabilities:
        return {
            "eligible": False,
            "reason": "model lacks required Foundry capabilities",
            "items": missing_capabilities,
        }
    sku = next(
        (
            item
            for item in model.get("skus", [])
            if str(item.get("name", "")).casefold() == config.model_sku.casefold()
        ),
        None,
    )
    if not sku:
        return {"eligible": False, "reason": "model SKU unavailable"}

    usage = run_json(
        "cognitiveservices",
        "usage",
        "list",
        "--location",
        region,
        "--subscription",
        config.subscription_id,
    )
    quota_name = str(sku.get("usageName", ""))
    quota = next(
        (item for item in usage if usage_name(item).casefold() == quota_name.casefold()),
        None,
    )
    if not quota:
        return {"eligible": False, "reason": "subscription quota metadata unavailable"}
    quota_available = int(float(quota.get("limit", 0)) - float(quota.get("currentValue", 0)))

    capacity_url = (
        "https://management.azure.com/subscriptions/"
        f"{config.subscription_id}/providers/Microsoft.CognitiveServices/locations/"
        f"{region}/modelCapacities"
    )
    capacity_payload = run_json(
        "rest",
        "--method",
        "get",
        "--url",
        capacity_url,
        "--uri-parameters",
        "api-version=2024-10-01",
        "modelFormat=OpenAI",
        f"modelName={config.model_name}",
        f"modelVersion={config.model_version}",
    )
    matching_capacity = [
        item
        for item in capacity_payload.get("value", [])
        if str((item.get("properties") or {}).get("skuName", "")).casefold()
        == config.model_sku.casefold()
    ]
    platform_capacity = max(
        [
            int((item.get("properties") or {}).get("availableCapacity", 0))
            for item in matching_capacity
        ],
        default=0,
    )

    postgres_skus = run_json(
        "postgres",
        "flexible-server",
        "list-skus",
        "--location",
        region,
        "--subscription",
        config.subscription_id,
    )
    postgres_available = postgres_sku_available(
        postgres_skus, config.postgres_sku, config.postgres_tier
    )

    app_usage_url = (
        "https://management.azure.com/subscriptions/"
        f"{config.subscription_id}/providers/Microsoft.App/locations/{region}/usages"
    )
    app_usage = run_json(
        "rest",
        "--method",
        "get",
        "--url",
        app_usage_url,
        "--uri-parameters",
        "api-version=2024-03-01",
    )
    environment_quota = next(
        (
            item
            for item in app_usage.get("value", [])
            if usage_name(item).casefold() == "managedenvironmentcount"
        ),
        None,
    )
    app_environment_available = (
        int(environment_quota.get("limit", 0))
        - int(environment_quota.get("currentValue", 0))
        if environment_quota
        else 0
    )

    eligible = (
        quota_available >= config.model_capacity
        and platform_capacity >= config.model_capacity
        and postgres_available
        and app_environment_available >= 1
    )
    return {
        "eligible": eligible,
        "model": {
            "name": config.model_name,
            "version": config.model_version,
            "sku": config.model_sku,
            "requestedCapacity": config.model_capacity,
            "platformCapacity": platform_capacity,
            "subscriptionQuotaAvailable": quota_available,
            "lifecycleStatus": model.get("lifecycleStatus"),
            "inferenceDeprecation": (model.get("deprecation") or {}).get("inference"),
            "agentsV2": True,
            "responses": True,
        },
        "postgresSkuAvailable": postgres_available,
        "containerAppsEnvironmentQuotaAvailable": app_environment_available,
    }


def parse_arguments() -> tuple[Configuration, str]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--expected-user", required=True)
    parser.add_argument("--regions", nargs="+", default=["eastus2", "eastus", "centralus"])
    parser.add_argument("--model-name", default="gpt-4.1-mini")
    parser.add_argument("--model-version", default="2025-04-14")
    parser.add_argument("--model-sku", default="GlobalStandard")
    parser.add_argument("--model-capacity", type=int, default=10)
    parser.add_argument("--postgres-sku", default="Standard_B1ms")
    parser.add_argument("--postgres-tier", default="Burstable")
    parser.add_argument(
        "--identity-mode",
        choices=("azure-cli", "azd"),
        default="azure-cli",
        help="Azure CLI mode reports azd mismatch without blocking; azd mode requires a match.",
    )
    arguments = parser.parse_args()
    return (
        Configuration(
            subscription_id=arguments.subscription_id,
            tenant_id=arguments.tenant_id,
            expected_user=arguments.expected_user,
            regions=tuple(arguments.regions),
            model_name=arguments.model_name,
            model_version=arguments.model_version,
            model_sku=arguments.model_sku,
            model_capacity=arguments.model_capacity,
            postgres_sku=arguments.postgres_sku,
            postgres_tier=arguments.postgres_tier,
        ),
        arguments.identity_mode,
    )


def main() -> int:
    config, identity_mode = parse_arguments()
    try:
        identity = verify_identity(config, identity_mode)
        roles = verify_permissions(config)
        providers = provider_metadata(config)
        regions = {
            region: verify_region(config, providers, region) for region in config.regions
        }
        selected = next(
            (region for region in config.regions if regions[region].get("eligible")),
            None,
        )
        if selected is None:
            raise PreflightError("No region in the authorized order passed all checks.")
    except PreflightError as error:
        print(f"Azure preflight failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "passed",
                "mutationPerformed": False,
                "identity": identity,
                "roles": roles,
                "providersRegistered": list(REQUIRED_PROVIDERS),
                "regions": regions,
                "selectedRegion": selected,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
