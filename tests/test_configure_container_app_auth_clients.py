import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "configure_container_app_auth_clients",
    ROOT / "scripts" / "azure" / "configure-container-app-auth-clients.py",
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class ConfigureContainerAppAuthClientsTests(unittest.TestCase):
    def test_configure_preserves_auth_and_sets_exact_clients(self):
        current = {
            "properties": {
                "platform": {"enabled": True},
                "identityProviders": {
                    "azureActiveDirectory": {
                        "registration": {"clientId": "api-client"},
                        "validation": {"allowedAudiences": ["api://api-client"]},
                    }
                },
            }
        }
        clients = [
            "04b07795-8ddb-461a-bbee-02f9e1bf7b46",
            "fc6ad53b-9748-48d5-9d88-2059d4931bb7",
        ]
        updated = {
            "properties": {
                **current["properties"],
                "identityProviders": {
                    "azureActiveDirectory": {
                        **current["properties"]["identityProviders"][
                            "azureActiveDirectory"
                        ],
                        "validation": {
                            "allowedAudiences": ["api://api-client"],
                            "defaultAuthorizationPolicy": {
                                "allowedApplications": clients,
                            },
                        },
                    }
                },
            }
        }

        with patch.object(module, "_run", side_effect=[current, updated]) as run:
            result = module.configure("https://management.example.test/auth", clients)

        self.assertEqual(result["allowedApplications"], clients)
        body = run.call_args_list[1].kwargs["body"]
        self.assertTrue(body["properties"]["platform"]["enabled"])
        self.assertEqual(
            body["properties"]["identityProviders"]["azureActiveDirectory"][
                "validation"
            ]["allowedAudiences"],
            ["api://api-client"],
        )

    def test_configure_rejects_non_uuid_client(self):
        with self.assertRaises(module.AuthConfigurationError):
            module.configure(
                "https://management.example.test/auth", ["not-a-client-id"]
            )


if __name__ == "__main__":
    unittest.main()
