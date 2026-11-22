import copy
import importlib.util
import json
import re
import unittest
from pathlib import Path


INFRA = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("infra_validation", INFRA / "validate.py")
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


def all_resources(template):
    for resource in template.get("resources", []):
        yield resource
        nested = resource.get("properties", {}).get("template")
        if nested:
            yield from all_resources(nested)


def role_assignments(template):
    variables = template.get("variables", {})
    for resource in template.get("resources", []):
        if resource["type"] == "Microsoft.Authorization/roleAssignments":
            expression = resource["properties"]["roleDefinitionId"]
            match = re.search(r"variables\('([^']+)'\)", expression)
            if not match:
                raise AssertionError(f"Unexpected role expression: {expression}")
            yield resource, variables[match.group(1)]
        nested = resource.get("properties", {}).get("template")
        if nested:
            yield from role_assignments(nested)


class InfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = validation.find_compiler()
        cls.template = json.loads(
            validation.run_compiler(cls.compiler, "build", "main.bicep", "--stdout")
        )
        cls.resources = list(all_resources(cls.template))

    def resources_of_type(self, resource_type):
        return [resource for resource in self.resources if resource["type"] == resource_type]

    def test_api_ingress_and_auth_configuration_are_restrictive(self):
        environments = self.resources_of_type("Microsoft.App/managedEnvironments")
        self.assertEqual(len(environments), 1)
        properties = environments[0]["properties"]
        self.assertTrue(properties["vnetConfiguration"]["internal"])
        self.assertEqual(properties["publicNetworkAccess"], "Disabled")
        apps = self.resources_of_type("Microsoft.App/containerApps")
        self.assertEqual(len(apps), 2)
        for app in apps:
            ingress = app["properties"]["configuration"]["ingress"]
            self.assertFalse(ingress["external"])
            self.assertFalse(ingress["allowInsecure"])
        auth = self.resources_of_type("Microsoft.App/containerApps/authConfigs")
        self.assertEqual(len(auth), 1)
        settings = auth[0]["properties"]
        self.assertTrue(settings["platform"]["enabled"])
        self.assertEqual(settings["globalValidation"]["unauthenticatedClientAction"], "Return401")
        self.assertEqual(settings["globalValidation"]["excludedPaths"], ["/healthz"])
        self.assertTrue(settings["identityProviders"]["azureActiveDirectory"]["enabled"])
        self.assertTrue(settings["httpSettings"]["requireHttps"])

    def test_foundry_and_database_disable_key_or_password_auth_and_public_access(self):
        account = self.resources_of_type("Microsoft.CognitiveServices/accounts")[0]["properties"]
        self.assertTrue(account["disableLocalAuth"])
        self.assertEqual(account["publicNetworkAccess"], "Disabled")
        self.assertEqual(account["networkAcls"]["defaultAction"], "Deny")
        postgres = self.resources_of_type("Microsoft.DBforPostgreSQL/flexibleServers")[0]["properties"]
        self.assertEqual(postgres["authConfig"]["activeDirectoryAuth"], "Enabled")
        self.assertEqual(postgres["authConfig"]["passwordAuth"], "Disabled")
        self.assertEqual(postgres["network"]["publicNetworkAccess"], "Disabled")
        self.assertNotIn("administratorLoginPassword", postgres)
        self.assertFalse(self.resources_of_type("Microsoft.DBforPostgreSQL/flexibleServers/firewallRules"))
        tls = self.resources_of_type("Microsoft.DBforPostgreSQL/flexibleServers/configurations")
        self.assertEqual(len(tls), 1)
        self.assertIn("require_secure_transport", tls[0]["name"])
        self.assertEqual(tls[0]["properties"]["value"], "ON")

    def test_postgres_major_version_disclosure_matches_compose_and_compiled_template(self):
        postgres = self.resources_of_type("Microsoft.DBforPostgreSQL/flexibleServers")[0]
        staged_version = postgres["properties"]["version"]
        compose = (validation.ROOT / "compose.yaml").read_text(encoding="utf-8")
        images = re.findall(r"(?m)^[ \t]*image:[ \t]*['\"]?postgres:(\d+)(?=[^0-9]|$)", compose)
        self.assertEqual(len(images), 1, "Compose must select one explicit PostgreSQL major version.")
        local_version = images[0]
        guide = (INFRA / "README.md").read_text(encoding="utf-8")
        section = guide.partition("## Open PostgreSQL version gap")[2].partition("\n## ")[0]
        if staged_version != local_version:
            self.assertTrue(section, "Document the PostgreSQL major-version mismatch.")
            self.assertIn(f"PostgreSQL **{staged_version}**", section)
            self.assertIn(f"PostgreSQL **{local_version}**", section)
            self.assertIn("do not establish", section)
            self.assertIn("drift", section)
        else:
            self.assertFalse(section, "Remove the stale PostgreSQL version-gap disclosure.")

    def test_monitoring_disables_public_access_and_insights_local_auth(self):
        workspace = self.resources_of_type("Microsoft.OperationalInsights/workspaces")[0]["properties"]
        insights = self.resources_of_type("Microsoft.Insights/components")[0]["properties"]
        for resource in (workspace, insights):
            self.assertEqual(resource["publicNetworkAccessForIngestion"], "Disabled")
            self.assertEqual(resource["publicNetworkAccessForQuery"], "Disabled")
        self.assertTrue(insights["DisableLocalAuth"])

    def test_roles_are_scoped_and_registry_cannot_use_anonymous_or_admin_auth(self):
        roles = list(role_assignments(self.template))
        self.assertEqual(len(roles), 4)
        for role, role_id in roles:
            scope = role["scope"]
            self.assertEqual(role["properties"]["principalType"], "ServicePrincipal")
            if role_id == "eed3b665-ab3a-47b6-8f48-c9382fb1dad6":
                self.assertTrue(
                    "accounts/{0}/projects/{1}" in scope or "accounts/projects" in scope
                )
                self.assertEqual(role.get("condition"), "[parameters('grantProjectAgentConsumer')]")
            elif role_id == "53ca6127-db72-4b80-b1b0-d745d6d5456d":
                self.assertIn("CognitiveServices/accounts", scope)
                self.assertNotIn("/projects/", scope)
            elif role_id == "7f951dda-4ed3-4680-a7ca-43fe172d538d":
                self.assertIn("ContainerRegistry/registries", scope)
            else:
                self.fail(f"Unexpected broad role: {role_id}")
        registry = self.resources_of_type("Microsoft.ContainerRegistry/registries")[0]["properties"]
        self.assertFalse(registry["adminUserEnabled"])
        self.assertFalse(registry["anonymousPullEnabled"])

    def test_optional_workloads_remain_disabled_and_keys_are_not_outputs(self):
        options = ("deployModel", "grantProjectAgentConsumer", "createRegistry", "createContainerApps")
        for name in options:
            self.assertIs(self.template["parameters"][name]["defaultValue"], False)
        conditions = [item.get("condition") for item in self.resources]
        for name in options:
            self.assertIn(f"[parameters('{name}')]", conditions)
        outputs = json.dumps(self.template["outputs"]).lower()
        self.assertNotIn("listkeys", outputs)
        self.assertNotIn("connectionstring", outputs)

    def test_network_validation_rejects_overlap_public_ranges_and_small_subnets(self):
        valid = {
            "networkAddressPrefix": "10.42.0.0/16",
            "appsSubnetPrefix": "10.42.0.0/23",
            "postgresSubnetPrefix": "10.42.2.0/24",
        }
        validation.validate_networks(valid)
        for changes in (
            {"postgresSubnetPrefix": "10.42.0.0/24"},
            {"appsSubnetPrefix": "10.42.0.0/28"},
            {"networkAddressPrefix": "8.0.0.0/8"},
            {"postgresSubnetPrefix": "2001:db8::/64"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(validation.ValidationError):
                    validation.validate_networks({**valid, **changes})

    def test_azd_configuration_rejects_paths_outside_the_generated_project(self):
        config = validation.read_json(validation.ROOT / "azure.yaml")
        validation.validate_azd_configuration(validation.ROOT, config, self.template)
        for key, value in (("project", "../outside"), ("docker", {"path": "../outside"})):
            altered = copy.deepcopy(config)
            altered["services"]["api"][key] = value
            with self.subTest(key=key):
                with self.assertRaises(validation.ValidationError):
                    validation.validate_azd_configuration(validation.ROOT, altered, self.template)

    def test_example_parameters_compile_without_enabling_cloud_workloads(self):
        validation.validate_examples(self.compiler, self.template)


if __name__ == "__main__":
    unittest.main()
