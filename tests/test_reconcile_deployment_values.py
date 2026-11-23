import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "reconcile_deployment_values",
    ROOT / "scripts" / "azure" / "reconcile-deployment-values.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class ReconcileDeploymentValuesTests(unittest.TestCase):
    @staticmethod
    def endpoint(agent: str, resource: str) -> str:
        return (
            "https://foundry.example.test/api/projects/project/"
            f"agents/{agent}/endpoint/protocols/openai/{resource}"
            "?api-version=2025-11-15-preview"
        )

    def test_reconcile_requires_exact_live_identity_and_emits_final_contract(self):
        subscription = "11111111-1111-4111-8111-111111111111"
        project = (
            f"/subscriptions/{subscription}/resourceGroups/rg/providers/"
            "Microsoft.CognitiveServices/accounts/foundry/projects/project"
        )
        values = {
            "AZURE_SUBSCRIPTION_ID": subscription,
            "AZURE_AI_PROJECT_ID": project,
            "AZURE_API_FQDN": "api.example.test",
            "AZURE_WEB_FQDN": "web.example.test",
            "AZURE_POSTGRESQL_HOST": "db.example.test",
            "AZURE_POSTGRESQL_DATABASE": "app",
            "AZURE_API_IDENTITY_NAME": "api identity",
            "AZURE_POSTGRES_ADMIN_PRINCIPAL_NAME": "operator@example.test",
            "AZURE_API_ENTRA_APP_ID_URI": "api://22222222-2222-4222-8222-222222222222",
        }
        journal = {
            "status": "acknowledged",
            "provisioning_status": "active",
            "agent_version": "2",
            "agent_version_id": "order-resolution:2",
            "agent_guid": "33333333-3333-4333-8333-333333333333",
            "identity_principal_id": "44444444-4444-4444-8444-444444444444",
            "identity_client_id": "44444444-4444-4444-8444-444444444444",
        }
        api_app = {
            "properties": {
                "latestReadyRevisionName": "api--revision",
                "template": {
                    "containers": [{"image": "registry/api@sha256:" + "a" * 64}]
                },
            }
        }
        web_app = {
            "properties": {
                "latestReadyRevisionName": "web--revision",
                "template": {
                    "containers": [{"image": "registry/web@sha256:" + "b" * 64}]
                },
            }
        }
        scope = f"{project}/agents/order-resolution"
        result = module.reconcile(
            values,
            journal,
            source_revision="c" * 40,
            deployment_revision="c" * 40,
            agent_name="order-resolution",
            responses_endpoint=self.endpoint("order-resolution", "responses"),
            conversation_endpoint=self.endpoint("order-resolution", "conversations"),
            api_app=api_app,
            web_app=web_app,
            agent_role_assignments=[{"id": "role-assignment", "scope": scope}],
            hosted_app_role_assignments=[{"id": "app-role-assignment"}],
            acceptance_mode=True,
        )
        self.assertEqual(result["AGENT_VERSION"], "2")
        self.assertEqual(result["DEPLOYMENT_REVISION"], "c" * 40)
        self.assertEqual(result["AZURE_HOSTED_AGENT_RBAC_SCOPE"], scope)
        self.assertEqual(
            result["AZURE_HOSTED_API_APP_ROLE_ASSIGNMENT_ID"], "app-role-assignment"
        )
        self.assertEqual(result["ACCEPTANCE_MODE"], "true")
        self.assertIn("sslmode=verify-full", result["AZURE_API_DATABASE_URL"])

    def test_reconcile_rejects_non_exact_agent_assignment(self):
        with self.assertRaises(module.ReconciliationError):
            module.reconcile(
                {
                    "AZURE_SUBSCRIPTION_ID": "11111111-1111-4111-8111-111111111111",
                    "AZURE_AI_PROJECT_ID": "/subscriptions/x/projects/y",
                    "AZURE_API_FQDN": "api.example.test",
                    "AZURE_WEB_FQDN": "web.example.test",
                    "AZURE_POSTGRESQL_HOST": "db.example.test",
                    "AZURE_POSTGRESQL_DATABASE": "app",
                    "AZURE_API_IDENTITY_NAME": "api",
                    "AZURE_POSTGRES_ADMIN_PRINCIPAL_NAME": "operator",
                    "AZURE_API_ENTRA_APP_ID_URI": "api://app",
                },
                {
                    "status": "acknowledged",
                    "provisioning_status": "active",
                    "agent_version": "1",
                    "agent_version_id": "a:1",
                    "agent_guid": "guid",
                    "identity_principal_id": "principal",
                    "identity_client_id": "client",
                },
                source_revision="a" * 40,
                deployment_revision="a" * 40,
                agent_name="agent",
                responses_endpoint=self.endpoint("agent", "responses"),
                conversation_endpoint=self.endpoint("agent", "conversations"),
                api_app={
                    "properties": {
                        "latestReadyRevisionName": "api--1",
                        "template": {
                            "containers": [{"image": "r/a@sha256:" + "a" * 64}]
                        },
                    }
                },
                web_app={
                    "properties": {
                        "latestReadyRevisionName": "web--1",
                        "template": {
                            "containers": [{"image": "r/w@sha256:" + "b" * 64}]
                        },
                    }
                },
                agent_role_assignments=[{"id": "bad", "scope": "/wrong"}],
                hosted_app_role_assignments=[{"id": "assignment"}],
                acceptance_mode=False,
            )

    def test_reconcile_rejects_generic_project_protocol_endpoints(self):
        with self.assertRaisesRegex(module.ReconciliationError, "selected agent"):
            module._endpoint(
                "https://foundry.example.test/api/projects/project/openai/responses"
                "?api-version=2025-11-15-preview",
                "order-resolution",
                "responses",
            )


if __name__ == "__main__":
    unittest.main()
