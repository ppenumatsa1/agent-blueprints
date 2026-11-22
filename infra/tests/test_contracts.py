import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"


def build_template():
    az = shutil.which("az")
    if not az:
        raise AssertionError("Azure CLI is required for Bicep compilation.")
    result = subprocess.run(
        [az, "bicep", "build", "--file", str(INFRA / "main.bicep"), "--stdout"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def resources(template):
    collection = template.get("resources", {})
    items = collection.values() if isinstance(collection, dict) else collection
    for resource in items:
        yield resource
        properties = resource.get("properties")
        nested = properties.get("template") if isinstance(properties, dict) else None
        if nested:
            yield from resources(nested)


def environment_names(environment):
    if isinstance(environment, list):
        return {
            item["name"]
            for item in environment
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
    if isinstance(environment, str):
        return set(re.findall(r"createObject\('name', '([^']+)'", environment))
    raise AssertionError(f"Unexpected Container App environment shape: {type(environment)}")


class InfrastructureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = build_template()
        cls.resources = list(resources(cls.template))
        cls.serialized = json.dumps(cls.template)

    def of_type(self, resource_type):
        return [
            resource for resource in self.resources if resource.get("type") == resource_type
        ]

    def test_public_topology_has_no_private_network_resources(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in INFRA.rglob("*.bicep")
        )
        for marker in (
            "Microsoft.Network/privateEndpoints",
            "Microsoft.Network/privateDnsZones",
            "Microsoft.Network/virtualNetworks",
            "delegatedSubnetResourceId",
            "privateDnsZoneArmResourceId",
        ):
            self.assertNotIn(marker, source)

    def test_foundry_model_is_explicit_and_local_auth_is_disabled(self):
        accounts = self.of_type("Microsoft.CognitiveServices/accounts")
        self.assertEqual(len(accounts), 1)
        account = accounts[0]
        self.assertEqual(account["kind"], "AIServices")
        self.assertTrue(account["properties"]["disableLocalAuth"])
        self.assertEqual(account["properties"]["publicNetworkAccess"], "Enabled")

        deployments = self.of_type("Microsoft.CognitiveServices/accounts/deployments")
        self.assertEqual(len(deployments), 1)
        model = deployments[0]["properties"]["model"]
        self.assertEqual(model["format"], "[parameters('modelFormat')]")
        self.assertEqual(model["name"], "[parameters('modelName')]")
        self.assertEqual(model["version"], "[parameters('modelVersion')]")
        self.assertEqual(deployments[0]["sku"]["name"], "[parameters('modelSkuName')]")
        self.assertEqual(deployments[0]["sku"]["capacity"], "[parameters('modelCapacity')]")

    def test_postgres_is_entra_only_public_and_tls_enforced(self):
        servers = self.of_type("Microsoft.DBforPostgreSQL/flexibleServers")
        self.assertEqual(len(servers), 1)
        properties = servers[0]["properties"]
        self.assertEqual(properties["authConfig"]["activeDirectoryAuth"], "Enabled")
        self.assertEqual(properties["authConfig"]["passwordAuth"], "Disabled")
        self.assertEqual(properties["network"]["publicNetworkAccess"], "Enabled")
        self.assertNotIn("administratorLogin", self.serialized)
        self.assertNotIn("administratorLoginPassword", self.serialized)

        configurations = self.of_type(
            "Microsoft.DBforPostgreSQL/flexibleServers/configurations"
        )
        values = {resource["name"]: resource["properties"]["value"] for resource in configurations}
        self.assertTrue(
            any("require_secure_transport" in name and value == "ON" for name, value in values.items())
        )
        self.assertTrue(
            any("ssl_min_protocol_version" in name and value == "TLSv1.2" for name, value in values.items())
        )

    def test_container_apps_are_tls_only_bounded_and_api_authenticated(self):
        environments = self.of_type("Microsoft.App/managedEnvironments")
        self.assertEqual(len(environments), 1)
        self.assertEqual(environments[0]["properties"]["publicNetworkAccess"], "Enabled")
        self.assertFalse(environments[0]["properties"]["zoneRedundant"])

        apps = self.of_type("Microsoft.App/containerApps")
        self.assertEqual(len(apps), 2)
        for app in apps:
            ingress = app["properties"]["configuration"]["ingress"]
            self.assertTrue(ingress["external"])
            self.assertFalse(ingress["allowInsecure"])
            scale = app["properties"]["template"]["scale"]
            self.assertEqual(scale["minReplicas"], "[parameters('minReplicas')]")
            self.assertEqual(scale["maxReplicas"], "[parameters('maxReplicas')]")

        api_app = next(
            app
            for app in apps
            if app["properties"]["template"]["containers"][0]["name"] == "api"
        )
        api_environment = environment_names(
            api_app["properties"]["template"]["containers"][0]["env"]
        )
        for name in (
            "APPLICATIONINSIGHTS_AUTHENTICATION_STRING",
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "API_MANAGED_IDENTITY_CLIENT_ID",
            "AZURE_AI_MODEL_DEPLOYMENT_NAME",
            "AZURE_AI_PROJECT_ENDPOINT",
            "AZURE_CLIENT_ID",
            "CORS_ORIGINS",
            "DATABASE_AUTH_MODE",
            "DATABASE_CONNECTION_MAX_LIFETIME_SECONDS",
            "DATABASE_MANAGED_IDENTITY_CLIENT_ID",
            "DATABASE_POOL_MAX_SIZE",
            "DATABASE_POOL_MIN_SIZE",
            "DATABASE_POOL_TIMEOUT_SECONDS",
            "DATABASE_TLS_MODE",
            "DATABASE_URL",
            "ENTRA_API_CLIENT_ID",
            "ENTRA_TENANT_ID",
            "HOSTED_WORKFLOW_ENDPOINT",
            "HOSTED_WORKFLOW_SCOPE",
            "TELEMETRY_MODE",
            "WORKFLOW_HOST",
        ):
            self.assertIn(name, api_environment)
        self.assertNotIn("BLUEPRINT_APPLICATION", api_environment)
        self.assertNotIn("CHECKPOINT_ROOT", api_environment)
        api_environment_expression = api_app["properties"]["template"]["containers"][0][
            "env"
        ]
        self.assertIn("'WORKFLOW_HOST', 'value', 'hosted'", api_environment_expression)
        self.assertNotIn("'WORKFLOW_HOST', 'value', 'local'", api_environment_expression)

        auth = self.of_type("Microsoft.App/containerApps/authConfigs")
        self.assertEqual(len(auth), 1)
        properties = auth[0]["properties"]
        self.assertTrue(properties["platform"]["enabled"])
        self.assertTrue(properties["httpSettings"]["requireHttps"])
        self.assertEqual(
            properties["globalValidation"]["unauthenticatedClientAction"], "Return401"
        )
        self.assertEqual(properties["globalValidation"]["excludedPaths"], ["/healthz"])
        self.assertIn(
            "[parameters('apiEntraAppIdUri')]",
            properties["identityProviders"]["azureActiveDirectory"]["validation"][
                "allowedAudiences"
            ],
        )

    def test_registry_key_vault_and_outputs_do_not_enable_secret_bypass(self):
        registries = [
            resource
            for resource in self.of_type("Microsoft.ContainerRegistry/registries")
            if isinstance(resource.get("properties"), dict)
        ]
        self.assertEqual(len(registries), 1)
        properties = registries[0]["properties"]
        self.assertEqual(properties["adminUserEnabled"], "[parameters('acrAdminUserEnabled')]")
        self.assertEqual(
            properties["anonymousPullEnabled"], "[parameters('anonymousPullEnabled')]"
        )
        registry_source = (INFRA / "modules" / "registry.bicep").read_text(
            encoding="utf-8"
        )
        self.assertIn("acrAdminUserEnabled: false", registry_source)
        self.assertIn("anonymousPullEnabled: false", registry_source)

        vaults = [
            resource
            for resource in self.of_type("Microsoft.KeyVault/vaults")
            if isinstance(resource.get("properties"), dict)
            and "enableRbacAuthorization" in resource["properties"]
        ]
        self.assertEqual(len(vaults), 1)
        vault = vaults[0]["properties"]
        self.assertTrue(vault["enableRbacAuthorization"])
        self.assertTrue(vault["enablePurgeProtection"])

        outputs = json.dumps(self.template.get("outputs", {})).casefold()
        self.assertNotIn("listkeys", outputs)
        self.assertNotIn("connectionstring", outputs)
        self.assertNotIn("password", outputs)
        self.assertNotIn("eed3b665-ab3a-47b6-8f48-c9382fb1dad6", self.serialized)
        self.assertNotIn("53ca6127-db72-4b80-b1b0-d745d6d5456d", self.serialized)

    def test_azd_configuration_is_infrastructure_only(self):
        text = (ROOT / "azure.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?m)^services:")
        self.assertNotIn("blueprints/maf/workflow", text)
        self.assertIn(
            "scripts/azure/preflight.ps1 -DeploymentMode Azd -FromAzdEnvironment",
            text,
        )

    def test_operations_fail_closed_and_teardown_is_explicit(self):
        scripts = {
            path.name: path.read_text(encoding="utf-8")
            for path in (ROOT / "scripts" / "azure").glob("*")
            if path.is_file()
        }
        combined = "\n".join(scripts.values())
        self.assertNotIn("az account set", combined)
        self.assertIn(
            "Azure CLI and azd account or tenant differ", scripts["preflight.py"]
        )
        self.assertIn('"auth", "token", "--no-prompt"', scripts["preflight.py"])
        self.assertIn('azd_claims.get("tid"', scripts["preflight.py"])
        self.assertIn('"azure-cli"', scripts["preflight.py"])
        self.assertIn("azd mode must stop", scripts["preflight.py"])
        self.assertIn('("agentsV2", "responses")', scripts["preflight.py"])
        self.assertIn("firewall-rule delete", scripts["configure-postgres.ps1"])
        self.assertIn("az containerapp show", scripts["configure-postgres.ps1"])
        self.assertIn(
            "pgaadauth_create_principal_with_oid",
            scripts["configure-postgres.ps1"],
        )
        self.assertIn("deployment-operator", scripts["common.ps1"])
        self.assertIn("configure-entra.ps1", scripts["deploy.ps1"])
        self.assertIn(
            "scripts\\instantiate_maf.py --profile order-resolution",
            scripts["deploy.ps1"],
        )
        self.assertIn("Assert-GeneratedOrderResolutionProject", scripts["deploy.ps1"])
        self.assertIn("publish_order_resolution_hosted.py", combined)
        self.assertIn("az deployment sub create", scripts["deploy.ps1"])
        self.assertIn("az acr build", scripts["deploy.ps1"])
        self.assertIn("'WORKFLOW_HOST=hosted'", scripts["deploy.ps1"])
        self.assertIn(
            "eed3b665-ab3a-47b6-8f48-c9382fb1dad6",
            scripts["deploy.ps1"],
        )
        self.assertIn("HostedDatabaseRoleName", scripts["deploy.ps1"])
        self.assertIn("publishRecord.identity_principal_id", scripts["deploy.ps1"])
        self.assertIn("publishRecord.identity_client_id", scripts["deploy.ps1"])
        self.assertIn("publishRecord.provisioning_status", scripts["deploy.ps1"])
        self.assertNotIn("publishRecord.principal_id", scripts["deploy.ps1"])
        self.assertIn(
            '"AZURE_HOSTED_AGENT_PROVISIONING_STATUS"',
            scripts["health-check.py"],
        )
        self.assertIn(
            'environment.get("DATABASE_AUTH_MODE") != "managed-identity"',
            scripts["health-check.py"],
        )
        self.assertIn("proxy_pass http://api:8000;", scripts["deploy.ps1"])
        self.assertNotIn("blueprints\\maf\\workflow", scripts["deploy.ps1"])
        self.assertNotIn("CHECKPOINT_ROOT", scripts["deploy.ps1"])
        self.assertNotIn("BLUEPRINT_APPLICATION", scripts["deploy.ps1"])
        self.assertIn("Remove-PostgresOperatorFirewallRule", scripts["migrate.ps1"])
        self.assertIn(
            "Remove-PostgresOperatorFirewallRule", scripts["configure-postgres.ps1"]
        )
        self.assertNotIn("0.0.0.0", combined)
        self.assertNotIn("sslmode=require", combined)
        self.assertIn("sslmode=verify-full", combined)
        self.assertIn("DESTRUCTIVE", scripts["teardown.ps1"])
        self.assertIn("DESTRUCTIVE", scripts["teardown-entra.ps1"])
        self.assertIn("workflow.approve", scripts["configure-entra.ps1"])
        self.assertIn("Workflow.Approver", scripts["configure-entra.ps1"])
        self.assertNotIn("password", scripts["configure-entra.ps1"].casefold())
        self.assertIn("ConfirmEnvironmentName", scripts["teardown.ps1"])
        self.assertIn("azd down", scripts["teardown.ps1"])
        self.assertIn("az group delete", scripts["teardown.ps1"])

    def test_parameter_binding_contains_only_nonsecret_required_inputs(self):
        binding = json.loads((INFRA / "main.parameters.json").read_text(encoding="utf-8"))
        parameters = binding["parameters"]
        self.assertEqual(
            set(parameters),
            {
                "apiEntraClientId",
                "apiEntraAppIdUri",
                "environmentName",
                "hostedWorkflowEndpoint",
                "location",
                "postgresAdministratorObjectId",
                "postgresAdministratorPrincipalName",
                "spaEntraClientId",
            },
        )
        for item in parameters.values():
            self.assertRegex(item["value"], r"^\$\{[A-Z][A-Z0-9_]*\}$")

        source = (INFRA / "main.bicep").read_text(encoding="utf-8")
        self.assertIn(
            "resourceGroupName string = 'rg-agent-blueprints-ors-foundry-e2e'",
            source,
        )
        self.assertIn("uniqueString(subscription().id, resourceGroupName)", source)
        self.assertIn("param hostedWorkflowEndpoint string", source)
        self.assertNotIn("param blueprintApplication", source)


if __name__ == "__main__":
    unittest.main()
