import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "azure" / "verify_hosted_agent_scope.py"
SPEC = importlib.util.spec_from_file_location("verify_hosted_agent_scope", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SUBSCRIPTION = "11111111-1111-1111-1111-111111111111"
RESOURCE_GROUP = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg"
ACCOUNT = (
    f"{RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/account"
)
PROJECT = f"{ACCOUNT}/projects/project"
AGENT_NAME = "order-resolution"
SCOPE = f"{PROJECT}/agents/{AGENT_NAME}"


class HostedScopeEvidenceTests(unittest.TestCase):
    def test_exact_agent_scope_is_derived(self):
        self.assertEqual(MODULE.derive_scope(PROJECT, AGENT_NAME), SCOPE)
        self.assertEqual(
            MODULE.verify_exact_scope(SCOPE.lower(), PROJECT, AGENT_NAME),
            SCOPE,
        )

    def test_project_account_resource_group_and_subscription_are_rejected(self):
        for scope in (PROJECT, ACCOUNT, RESOURCE_GROUP, f"/subscriptions/{SUBSCRIPTION}"):
            with self.subTest(scope=scope), self.assertRaises(
                MODULE.ScopeEvidenceError
            ):
                MODULE.verify_exact_scope(scope, PROJECT, AGENT_NAME)

    def test_another_agent_scope_is_rejected(self):
        with self.assertRaises(MODULE.ScopeEvidenceError):
            MODULE.verify_exact_scope(
                f"{PROJECT}/agents/another-agent",
                PROJECT,
                AGENT_NAME,
            )

    def test_agent_version_or_role_assignment_child_is_rejected(self):
        for scope in (
            f"{SCOPE}/versions/7",
            f"{SCOPE}/providers/Microsoft.Authorization/roleAssignments/value",
        ):
            with self.subTest(scope=scope), self.assertRaises(
                MODULE.ScopeEvidenceError
            ):
                MODULE.verify_exact_scope(scope, PROJECT, AGENT_NAME)

    def test_invalid_project_or_agent_name_is_rejected(self):
        for project, name in (
            (ACCOUNT, AGENT_NAME),
            (PROJECT, "wrong/agent"),
            (PROJECT, ""),
        ):
            with self.subTest(project=project, name=name), self.assertRaises(
                MODULE.ScopeEvidenceError
            ):
                MODULE.derive_scope(project, name)


if __name__ == "__main__":
    unittest.main()
