#!/usr/bin/env python3
"""Rebuild strict normalized deployment values from acknowledged live Azure state."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit


AGENT_CONSUMER_ROLE_ID = "eed3b665-ab3a-47b6-8f48-c9382fb1dad6"
MONITORING_METRICS_PUBLISHER_ROLE_ID = "3913510d-42f4-4e42-8a64-420c390055eb"


class ReconciliationError(RuntimeError):
    pass


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReconciliationError(f"{path.name} must contain one object.")
    return value


def _required(value: dict, name: str) -> str:
    result = value.get(name)
    if not isinstance(result, str) or not result:
        raise ReconciliationError(f"Missing deployment value: {name}")
    return result


def _endpoint(value: str, agent_name: str, resource: str) -> str:
    parsed = urlsplit(value)
    expected_path = f"/agents/{agent_name}/endpoint/protocols/openai/{resource}"
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not parsed.path.rstrip("/").endswith(expected_path)
        or not parsed.query.startswith("api-version=")
    ):
        raise ReconciliationError(
            "Hosted endpoint must target the selected agent's explicit HTTPS "
            f"{resource} protocol endpoint."
        )
    return value


def _container(app: dict, label: str) -> tuple[str, str, dict[str, str]]:
    properties = app.get("properties") or {}
    revision = properties.get("latestReadyRevisionName")
    containers = (properties.get("template") or {}).get("containers") or []
    image = containers[0].get("image") if containers else None
    if not isinstance(revision, str) or not revision:
        raise ReconciliationError(f"{label} has no latest ready revision.")
    if not isinstance(image, str) or "@sha256:" not in image:
        raise ReconciliationError(f"{label} is not running an immutable image.")
    environment = {
        str(item.get("name")): str(item.get("value"))
        for item in containers[0].get("env", [])
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("value"), str)
    }
    return revision, image, environment


def reconcile(
    values: dict,
    journal: dict,
    *,
    source_revision: str,
    deployment_revision: str,
    agent_name: str,
    responses_endpoint: str,
    conversation_endpoint: str,
    api_app: dict,
    web_app: dict,
    agent_role_assignments: list[dict],
    hosted_monitoring_role_assignments: list[dict],
    hosted_app_role_assignments: list[dict],
    acceptance_mode: bool,
) -> dict:
    if len(source_revision) != 40 or any(
        character not in "0123456789abcdef" for character in source_revision
    ):
        raise ReconciliationError(
            "Source revision must be one lowercase 40-character SHA."
        )
    if not deployment_revision or len(deployment_revision) > 128:
        raise ReconciliationError("Deployment revision must be a bounded identifier.")
    if (
        journal.get("status") != "acknowledged"
        or journal.get("provisioning_status") != "active"
    ):
        raise ReconciliationError("Hosted publication is not acknowledged and active.")
    for name in (
        "agent_version",
        "agent_version_id",
        "agent_guid",
        "identity_principal_id",
        "identity_client_id",
    ):
        _required(journal, name)
    responses_endpoint = _endpoint(responses_endpoint, agent_name, "responses")
    conversation_endpoint = _endpoint(
        conversation_endpoint, agent_name, "conversations"
    )
    if len(agent_role_assignments) != 1:
        raise ReconciliationError("Expected one exact Agent Consumer role assignment.")
    if len(hosted_monitoring_role_assignments) != 1:
        raise ReconciliationError(
            "Expected one exact hosted Monitoring Metrics Publisher role assignment."
        )
    if len(hosted_app_role_assignments) != 1:
        raise ReconciliationError("Expected one hosted-service app-role assignment.")
    api_revision, api_image, api_environment = _container(api_app, "API Container App")
    web_revision, web_image, _ = _container(web_app, "web Container App")

    normalized = {str(name).upper(): value for name, value in values.items()}
    project_id = _required(normalized, "AZURE_AI_PROJECT_ID").rstrip("/")
    expected_scope = f"{project_id}/agents/{agent_name}"
    if (
        str(agent_role_assignments[0].get("scope", "")).casefold()
        != expected_scope.casefold()
    ):
        raise ReconciliationError(
            "Agent Consumer assignment is not exact-agent scoped."
        )
    if api_environment.get("HOSTED_AGENT_VERSION") != journal["agent_version"]:
        raise ReconciliationError(
            "API HOSTED_AGENT_VERSION does not match the active hosted version."
        )
    application_insights_scope = _required(
        normalized, "APPLICATIONINSIGHTS_RESOURCE_ID"
    )
    expected_monitoring_role = (
        f"/subscriptions/{_required(normalized, 'AZURE_SUBSCRIPTION_ID')}/providers/"
        "Microsoft.Authorization/roleDefinitions/"
        f"{MONITORING_METRICS_PUBLISHER_ROLE_ID}"
    )
    monitoring_assignment = hosted_monitoring_role_assignments[0]
    if (
        str(monitoring_assignment.get("scope", "")).casefold()
        != application_insights_scope.casefold()
        or str(monitoring_assignment.get("roleDefinitionId", "")).casefold()
        != expected_monitoring_role.casefold()
        or str(monitoring_assignment.get("principalId", "")).casefold()
        != str(journal["identity_principal_id"]).casefold()
    ):
        raise ReconciliationError(
            "Hosted Monitoring Metrics Publisher assignment is not exact-component scoped."
        )
    api_fqdn = _required(normalized, "AZURE_API_FQDN")
    web_fqdn = _required(normalized, "AZURE_WEB_FQDN")
    database_host = _required(normalized, "AZURE_POSTGRESQL_HOST")
    database = _required(normalized, "AZURE_POSTGRESQL_DATABASE")
    database_user = _required(normalized, "AZURE_API_IDENTITY_NAME")
    migration_user = _required(normalized, "AZURE_POSTGRES_ADMIN_PRINCIPAL_NAME")
    app_id_uri = _required(normalized, "AZURE_API_ENTRA_APP_ID_URI")
    normalized.update(
        {
            "SOURCE_REVISION": source_revision,
            "DEPLOYMENT_REVISION": deployment_revision,
            "AGENT_VERSION": journal["agent_version"],
            "ACCEPTANCE_MODE": str(acceptance_mode).lower(),
            "AZURE_API_IMAGE": api_image,
            "AZURE_WEB_IMAGE": web_image,
            "AZURE_API_REVISION": api_revision,
            "AZURE_WEB_REVISION": web_revision,
            "AZURE_HOSTED_AGENT_NAME": agent_name,
            "AZURE_HOSTED_AGENT_VERSION": journal["agent_version"],
            "AZURE_HOSTED_AGENT_VERSION_ID": journal["agent_version_id"],
            "AZURE_HOSTED_AGENT_GUID": journal["agent_guid"],
            "AZURE_HOSTED_AGENT_PRINCIPAL_ID": journal["identity_principal_id"],
            "AZURE_HOSTED_AGENT_CLIENT_ID": journal["identity_client_id"],
            "AZURE_HOSTED_AGENT_PROVISIONING_STATUS": journal["provisioning_status"],
            "AZURE_HOSTED_AGENT_RESPONSES_ENDPOINT": responses_endpoint,
            "AZURE_HOSTED_AGENT_CONVERSATION_ENDPOINT": conversation_endpoint,
            "AZURE_HOSTED_AGENT_ADAPTER_ENDPOINT": responses_endpoint,
            "AZURE_HOSTED_AGENT_RBAC_SCOPE": expected_scope,
            "AZURE_HOSTED_AGENT_RBAC_SCOPE_SOURCE": "official-foundry-agent-scope",
            "AZURE_API_HOSTED_AGENT_ROLE_ASSIGNMENT_ID": agent_role_assignments[0][
                "id"
            ],
            "AZURE_HOSTED_APPINSIGHTS_ROLE_ASSIGNMENT_ID": monitoring_assignment["id"],
            "AZURE_HOSTED_APPINSIGHTS_RBAC_SCOPE": application_insights_scope,
            "AZURE_HOSTED_APPINSIGHTS_RBAC_ROLE_ID": (
                MONITORING_METRICS_PUBLISHER_ROLE_ID
            ),
            "AZURE_HOSTED_API_APP_ROLE_ASSIGNMENT_ID": hosted_app_role_assignments[0][
                "id"
            ],
            "ORDER_RESOLUTION_API_ENDPOINT": f"https://{api_fqdn}/api/internal/hosted/v1",
            "ORDER_RESOLUTION_API_SCOPE": f"{app_id_uri}/.default",
            "HOSTED_WORKFLOW_ENDPOINT": responses_endpoint,
            "AZURE_API_URL": f"https://{api_fqdn}",
            "AZURE_WEB_URL": f"https://{web_fqdn}",
            "AZURE_API_DATABASE_URL": (
                f"postgresql://{quote(database_user, safe='')}@{database_host}:5432/{database}"
                "?sslmode=verify-full&sslrootcert=system"
            ),
            "AZURE_API_DATABASE_USER": database_user,
            "MIGRATION_DATABASE_URL": (
                f"postgresql://{quote(migration_user, safe='')}@{database_host}:5432/{database}"
                "?sslmode=verify-full&sslrootcert=system"
            ),
            "MIGRATION_DATABASE_USER": migration_user,
            "MIGRATION_DATABASE_PASSWORD_REFERENCE": (
                "transient-ref:azure-postgresql-access-token"
            ),
            "DATABASE_POOL_MIN_SIZE": "0",
            "DATABASE_POOL_MAX_SIZE": "8",
            "DATABASE_POOL_TIMEOUT_SECONDS": "30",
            "DATABASE_CONNECTION_MAX_LIFETIME_SECONDS": "900",
            "CORS_ORIGINS": f"https://{web_fqdn}",
            "APPLICATIONINSIGHTS_CONNECTION_STRING_REFERENCE": (
                "secretref:applicationinsights-connection-string"
            ),
        }
    )
    return normalized


def _az_json(arguments: list[str]) -> object:
    az = shutil.which("az")
    if az is None:
        raise ReconciliationError("Azure CLI is unavailable.")
    result = subprocess.run(
        [az, *arguments, "--output", "json", "--only-show-errors"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise ReconciliationError("Azure read failed: " + " ".join(arguments[:4]))
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values-file", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--deployment-revision", required=True)
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--responses-endpoint", required=True)
    parser.add_argument("--conversation-endpoint", required=True)
    parser.add_argument("--acceptance-mode", choices=("true", "false"), required=True)
    args = parser.parse_args()
    try:
        values = {
            str(name).upper(): value for name, value in _read(args.values_file).items()
        }
        journal = _read(args.journal)
        subscription = _required(values, "AZURE_SUBSCRIPTION_ID")
        resource_group = _required(values, "AZURE_RESOURCE_GROUP")
        api_name = _required(values, "AZURE_API_CONTAINER_APP_NAME")
        web_name = _required(values, "AZURE_WEB_CONTAINER_APP_NAME")
        project_id = _required(values, "AZURE_AI_PROJECT_ID").rstrip("/")
        scope = f"{project_id}/agents/{args.agent_name}"
        api_app = _az_json(
            [
                "containerapp",
                "show",
                "--subscription",
                subscription,
                "--resource-group",
                resource_group,
                "--name",
                api_name,
            ]
        )
        web_app = _az_json(
            [
                "containerapp",
                "show",
                "--subscription",
                subscription,
                "--resource-group",
                resource_group,
                "--name",
                web_name,
            ]
        )
        agent_assignments = _az_json(
            [
                "role",
                "assignment",
                "list",
                "--subscription",
                subscription,
                "--assignee-object-id",
                _required(values, "AZURE_API_IDENTITY_PRINCIPAL_ID"),
                "--scope",
                scope,
                "--query",
                f"[?roleDefinitionId=='/subscriptions/{subscription}/providers/"
                f"Microsoft.Authorization/roleDefinitions/{AGENT_CONSUMER_ROLE_ID}']",
            ]
        )
        api_sp = _required(values, "AZURE_API_ENTRA_SERVICE_PRINCIPAL_ID")
        app_role_id = _required(values, "AZURE_HOSTED_API_APP_ROLE_ID")
        hosted_principal = _required(journal, "identity_principal_id")
        assignments_payload = _az_json(
            [
                "rest",
                "--method",
                "get",
                "--url",
                "https://graph.microsoft.com/v1.0/servicePrincipals/"
                f"{hosted_principal}/appRoleAssignments",
            ]
        )
        hosted_assignments = [
            item
            for item in assignments_payload.get("value", [])
            if item.get("resourceId") == api_sp and item.get("appRoleId") == app_role_id
        ]
        application_insights_scope = _required(
            values, "APPLICATIONINSIGHTS_RESOURCE_ID"
        )
        monitoring_assignments = _az_json(
            [
                "role",
                "assignment",
                "list",
                "--subscription",
                subscription,
                "--assignee-object-id",
                hosted_principal,
                "--scope",
                application_insights_scope,
                "--query",
                f"[?roleDefinitionId=='/subscriptions/{subscription}/providers/"
                "Microsoft.Authorization/roleDefinitions/"
                f"{MONITORING_METRICS_PUBLISHER_ROLE_ID}']",
            ]
        )
        normalized = reconcile(
            values,
            journal,
            source_revision=args.source_revision,
            deployment_revision=args.deployment_revision,
            agent_name=args.agent_name,
            responses_endpoint=args.responses_endpoint,
            conversation_endpoint=args.conversation_endpoint,
            api_app=api_app,
            web_app=web_app,
            agent_role_assignments=agent_assignments,
            hosted_monitoring_role_assignments=monitoring_assignments,
            hosted_app_role_assignments=hosted_assignments,
            acceptance_mode=args.acceptance_mode == "true",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(normalized, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        ReconciliationError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"Deployment value reconciliation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
