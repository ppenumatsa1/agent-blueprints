import base64
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "azure_preflight", ROOT / "scripts" / "azure" / "preflight.py"
)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = PREFLIGHT
SPEC.loader.exec_module(PREFLIGHT)


def token(claims):
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


class IdentityModeTests(unittest.TestCase):
    def setUp(self):
        self.config = PREFLIGHT.Configuration(
            subscription_id="00000000-0000-0000-0000-000000000001",
            tenant_id="00000000-0000-0000-0000-000000000002",
            expected_user="operator@example.test",
            regions=("eastus2",),
            model_name="gpt-4.1-mini",
            model_version="2025-04-14",
            model_sku="GlobalStandard",
            model_capacity=10,
            postgres_sku="Standard_B2s",
            postgres_tier="Burstable",
        )

    @patch.object(PREFLIGHT, "run_text")
    @patch.object(PREFLIGHT, "run_json")
    def test_azure_cli_mode_reports_but_does_not_block_azd_mismatch(
        self, run_json, run_text
    ):
        run_json.return_value = {
            "id": self.config.subscription_id,
            "tenantId": self.config.tenant_id,
            "user": {"name": self.config.expected_user},
        }
        run_text.side_effect = [
            "Logged in to Azure as other@example.test",
            token(
                {
                    "tid": "00000000-0000-0000-0000-000000000099",
                    "preferred_username": "other@example.test",
                }
            ),
        ]

        identity = PREFLIGHT.verify_identity(self.config, "azure-cli")

        self.assertEqual(identity["deploymentMode"], "azure-cli")
        self.assertEqual(identity["azdIdentity"]["status"], "mismatch")
        self.assertFalse(identity["azdIdentity"]["matched"])

    @patch.object(PREFLIGHT, "run_text")
    @patch.object(PREFLIGHT, "run_json")
    def test_azd_mode_blocks_mismatched_identity(self, run_json, run_text):
        run_json.return_value = {
            "id": self.config.subscription_id,
            "tenantId": self.config.tenant_id,
            "user": {"name": self.config.expected_user},
        }
        run_text.side_effect = [
            "Logged in to Azure as other@example.test",
            token(
                {
                    "tid": "00000000-0000-0000-0000-000000000099",
                    "preferred_username": "other@example.test",
                }
            ),
        ]

        with self.assertRaisesRegex(PREFLIGHT.PreflightError, "azd mode must stop"):
            PREFLIGHT.verify_identity(self.config, "azd")

    @patch.object(PREFLIGHT, "run_text")
    @patch.object(PREFLIGHT, "run_json")
    def test_wrong_azure_cli_context_fails_before_azd_is_checked(
        self, run_json, run_text
    ):
        run_json.return_value = {
            "id": "00000000-0000-0000-0000-000000000099",
            "tenantId": self.config.tenant_id,
            "user": {"name": self.config.expected_user},
        }

        with self.assertRaisesRegex(
            PREFLIGHT.PreflightError, "active subscription does not match"
        ):
            PREFLIGHT.verify_identity(self.config, "azure-cli")

        run_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
