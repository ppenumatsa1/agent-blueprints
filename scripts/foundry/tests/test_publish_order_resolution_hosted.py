import importlib.util
import sys
import tempfile
import threading
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
PROJECT_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/"
    "Microsoft.CognitiveServices/accounts/account/projects/project"
)


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
        (root / "hosted-agent" / "main.py").write_text(
            "print('host')\n", encoding="utf-8"
        )
        (root / "hosted-agent" / "requirements.txt").write_text(
            "x==1\n", encoding="utf-8"
        )
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
                            project_endpoint="https://project.example.test",
                            project_id=PROJECT_ID,
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
                        "publication_digest": publisher._load_record(
                            journal
                        ).publication_digest,
                        "source_archive_sha256": digest,
                    },
                }
            ]
            reconciled = publisher.reconcile_publish(
                agents=agents,
                agent_name="order-resolution",
                journal_path=journal,
            )
            self.assertEqual(
                (reconciled.status, reconciled.agent_version), ("acknowledged", "9")
            )

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
                    project_endpoint="https://project.example.test",
                    project_id=PROJECT_ID,
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

    def test_publish_identity_rejects_target_model_and_runtime_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            publisher.build_source_archive(root, archive)
            journal = root / "publish.json"
            agents = FakeAgents()
            definition = SimpleNamespace(
                environment_variables={
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME": "configured-model"
                }
            )
            common = {
                "agents": agents,
                "project_endpoint": "https://project.example.test",
                "project_id": PROJECT_ID,
                "agent_name": "order-resolution",
                "archive": archive,
                "operation_id": "publish-bound",
                "model_deployment_name": "configured-model",
                "journal_path": journal,
            }
            with patch.object(publisher, "build_definition", return_value=definition):
                publisher.publish_once(**common)
                conflicts = (
                    {"project_endpoint": "https://other.example.test"},
                    {"project_id": "/subscriptions/sub/projects/other"},
                    {"agent_name": "other-agent"},
                    {"model_deployment_name": "other-model"},
                )
                for change in conflicts:
                    with self.subTest(change=change):
                        with self.assertRaisesRegex(ValueError, "publication identity"):
                            publisher.publish_once(**(common | change))
                with (
                    patch.object(publisher, "PYTHON_RUNTIME", "python_3_14"),
                    self.assertRaisesRegex(ValueError, "publication identity"),
                ):
                    publisher.publish_once(**common)

    def test_publication_digest_covers_complete_target_and_definition(self):
        identity = publisher.publication_identity(
            project_endpoint="https://project.example.test/",
            project_id=PROJECT_ID,
            agent_name="order-resolution",
            archive_sha256="a" * 64,
            model_deployment_name="configured-model",
        )
        self.assertEqual(identity["project_endpoint"], "https://project.example.test")
        self.assertEqual(identity["hosted_definition"]["runtime"], "python_3_13")
        self.assertEqual(
            identity["hosted_definition"]["protocols"],
            [{"protocol": "responses", "version": "2.0.0"}],
        )
        self.assertEqual(len(publisher.publication_digest(identity)), 64)

    def test_existing_pending_publish_becomes_unknown_without_sdk_create(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            archive_digest = publisher.build_source_archive(root, archive)
            identity_digest = publisher.publication_digest(
                publisher.publication_identity(
                    project_endpoint="https://project.example.test",
                    project_id=PROJECT_ID,
                    agent_name="order-resolution",
                    archive_sha256=archive_digest,
                    model_deployment_name="configured-model",
                )
            )
            journal = root / "publish.json"
            publisher._save_record(
                journal,
                publisher.PublishRecord(
                    operation_id="publish-pending",
                    publication_digest=identity_digest,
                    archive_sha256=archive_digest,
                    status="pending",
                    owner_token="previous-process",
                ),
            )
            agents = FakeAgents()
            definition = SimpleNamespace(environment_variables={})
            with (
                patch.object(publisher, "build_definition", return_value=definition),
                self.assertRaises(publisher.AmbiguousPublish),
            ):
                publisher.publish_once(
                    agents=agents,
                    project_endpoint="https://project.example.test",
                    project_id=PROJECT_ID,
                    agent_name="order-resolution",
                    archive=archive,
                    operation_id="publish-pending",
                    model_deployment_name="configured-model",
                    journal_path=journal,
                )
            self.assertEqual(agents.calls, [])
            self.assertEqual(publisher._load_record(journal).status, "unknown")

    def test_concurrent_publish_has_one_sdk_create_and_owner_can_ack(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            publisher.build_source_archive(root, archive)
            journal = root / "publish.json"
            agents = FakeAgents()
            entered = threading.Event()
            release = threading.Event()

            def create_version_from_code(**kwargs):
                agents.calls.append(kwargs)
                entered.set()
                release.wait(timeout=5)
                return SimpleNamespace(version="11")

            agents.create_version_from_code = create_version_from_code
            definition = SimpleNamespace(environment_variables={})
            common = {
                "agents": agents,
                "project_endpoint": "https://project.example.test",
                "project_id": PROJECT_ID,
                "agent_name": "order-resolution",
                "archive": archive,
                "operation_id": "publish-concurrent",
                "model_deployment_name": "configured-model",
                "journal_path": journal,
            }
            results = []
            errors = []

            def first():
                try:
                    results.append(publisher.publish_once(**common))
                except Exception as exc:
                    errors.append(exc)

            with patch.object(publisher, "build_definition", return_value=definition):
                thread = threading.Thread(target=first)
                thread.start()
                self.assertTrue(entered.wait(timeout=5))
                with self.assertRaises(publisher.AmbiguousPublish):
                    publisher.publish_once(**common)
                release.set()
                thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(agents.calls), 1)
            self.assertEqual(results[0].status, "acknowledged")
            self.assertEqual(results[0].agent_version, "11")
            self.assertEqual(publisher._load_record(journal).status, "acknowledged")


if __name__ == "__main__":
    unittest.main()
