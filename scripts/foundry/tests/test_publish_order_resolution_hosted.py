import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "foundry" / "publish_order_resolution_hosted.py"
SPEC = importlib.util.spec_from_file_location("publish_order_resolution_hosted", SCRIPT)
publisher = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = publisher
SPEC.loader.exec_module(publisher)


class FakeAgents:
    def __init__(self):
        self.calls = []
        self.versions = []
        self.fail = False

    def create_version_from_code(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("ack lost")
        return SimpleNamespace(version="7")

    def list_versions(self, agent_name):
        return self.versions


class PublisherTests(unittest.TestCase):
    def generated_tree(self, root):
        (root / "hosted-agent" / "src" / "order_resolution_hosted").mkdir(parents=True)
        (root / "backend" / "app").mkdir(parents=True)
        (root / "hosted-agent" / "main.py").write_text("print('host')\n", encoding="utf-8")
        (root / "hosted-agent" / "requirements.txt").write_text("x==1\n", encoding="utf-8")
        (
            root / "hosted-agent" / "src" / "order_resolution_hosted" / "__init__.py"
        ).write_text("", encoding="utf-8")
        (root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")

    def test_archive_and_manifest_are_source_responses_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            second = root / "agent-second.zip"
            digest = publisher.build_source_archive(root, archive)
            self.assertEqual(
                digest,
                publisher.build_source_archive(root, second),
            )
            self.assertEqual(archive.read_bytes(), second.read_bytes())
            self.assertEqual(len(digest), 64)
            with zipfile.ZipFile(archive) as value:
                self.assertEqual(
                    sorted(value.namelist()),
                    [
                        "app/__init__.py",
                        "main.py",
                        "order_resolution_hosted/__init__.py",
                        "requirements.txt",
                    ],
                )
            contract = publisher.build_azd_service_contract()
            self.assertEqual(
                contract["protocols"],
                [{"protocol": "responses", "version": "2.0.0"}],
            )
            self.assertEqual(contract["codeConfiguration"]["runtime"], "python_3_13")

    def test_ambiguous_publish_is_not_replayed_and_can_be_reconciled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            digest = publisher.build_source_archive(root, archive)
            journal = root / "publish.json"
            agents = FakeAgents()
            agents.fail = True
            definition = SimpleNamespace(
                environment_variables={
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "configured-model"
                }
            )
            with patch.object(publisher, "build_definition", return_value=definition):
                for _ in range(2):
                    with self.assertRaises(publisher.AmbiguousPublish):
                        publisher.publish_once(
                            agents=agents,
                            agent_name="order-resolution",
                            archive=archive,
                            operation_id="publish-1",
                            model_deployment_name="configured-model",
                            journal_path=journal,
                        )
            self.assertEqual(len(agents.calls), 1)
            agents.versions = [
                {
                    "version": "9",
                    "metadata": {
                        "publish_operation_id": "publish-1",
                        "source_archive_sha256": digest,
                    },
                }
            ]
            reconciled = publisher.reconcile_publish(
                agents=agents,
                agent_name="order-resolution",
                journal_path=journal,
            )
            self.assertEqual((reconciled.status, reconciled.agent_version), ("acknowledged", "9"))

    def test_publish_disables_sdk_post_retries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            publisher.build_source_archive(root, archive)
            agents = FakeAgents()
            definition = SimpleNamespace(
                environment_variables={
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "configured-model"
                }
            )
            with patch.object(publisher, "build_definition", return_value=definition):
                publisher.publish_once(
                    agents=agents,
                    agent_name="order-resolution",
                    archive=archive,
                    operation_id="publish-2",
                    model_deployment_name="configured-model",
                    journal_path=root / "publish.json",
                )
            self.assertEqual(agents.calls[0]["retry_total"], 0)
            self.assertEqual(
                agents.calls[0]["definition"].environment_variables[
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME"
                ],
                "configured-model",
            )


if __name__ == "__main__":
    unittest.main()
