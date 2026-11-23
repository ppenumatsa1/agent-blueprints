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


def runtime_environment(**changes):
    value = {
        "FOUNDRY_PROJECT_ENDPOINT": "https://project.example.test",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "configured-model",
        "APPLICATIONINSIGHTS_CONNECTION_STRING": (
            "InstrumentationKey=00000000-0000-0000-0000-000000000000;"
            "IngestionEndpoint=https://monitor.example.test/"
        ),
        "SOURCE_REVISION": "a" * 40,
        "DEPLOYMENT_REVISION": "a" * 40,
        "ORDER_RESOLUTION_API_ENDPOINT": (
            "https://api.example.test/internal/order-resolution/hosted"
        ),
        "ORDER_RESOLUTION_API_SCOPE": "api://order-resolution-api/.default",
        "ORDER_RESOLUTION_API_TIMEOUT_SECONDS": "30",
    }
    value.update(changes)
    return value


def hosted_definition():
    return SimpleNamespace(
        environment_variables=publisher.hosted_runtime_environment(
            runtime_environment()
        )
    )


class FakeAgents:
    def __init__(self):
        self.calls = []
        self.versions = []
        self.fail = False
        self.get_calls = []

    def create_version_from_code(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("ack lost")
        return SimpleNamespace(version="7")

    def list_versions(self, agent_name):
        return self.versions

    def get_version(self, *, agent_name, agent_version):
        self.get_calls.append((agent_name, agent_version))
        return SimpleNamespace(
            id="agent-version-resource",
            agent_guid="agent-guid",
            status="active",
            instance_identity=SimpleNamespace(
                principal_id="identity-principal",
                client_id="identity-client",
            ),
        )


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
            definition = hosted_definition()
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
                            runtime_environment=runtime_environment(),
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
            definition = hosted_definition()
            with patch.object(publisher, "build_definition", return_value=definition):
                created = publisher.publish_once(
                    agents=agents,
                    project_endpoint="https://project.example.test",
                    project_id=PROJECT_ID,
                    agent_name="order-resolution",
                    archive=archive,
                    operation_id="publish-2",
                    runtime_environment=runtime_environment(),
                    journal_path=root / "publish.json",
                )
                resolved = publisher.resolve_publish_identity(
                    agents=agents,
                    agent_name="order-resolution",
                    journal_path=root / "publish.json",
                    timeout_seconds=0,
                )
            self.assertEqual(agents.calls[0]["retry_total"], 0)
            self.assertEqual(
                agents.calls[0]["definition"].environment_variables[
                    "AZURE_AI_MODEL_DEPLOYMENT_NAME"
                ],
                "configured-model",
            )
            self.assertEqual(created.agent_version, "7")
            self.assertEqual(
                (
                    resolved.agent_version_id,
                    resolved.agent_guid,
                    resolved.identity_principal_id,
                    resolved.identity_client_id,
                ),
                (
                    "agent-version-resource",
                    "agent-guid",
                    "identity-principal",
                    "identity-client",
                ),
            )
            self.assertEqual(agents.get_calls, [("order-resolution", "7")])

    def test_identity_discovery_precedes_active_readiness_without_recreate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            publisher.build_source_archive(root, archive)
            agents = FakeAgents()
            journal = root / "publish.json"
            definition = hosted_definition()
            creating = SimpleNamespace(
                id="agent-version-resource",
                agent_guid="agent-guid",
                status="creating",
                instance_identity=SimpleNamespace(
                    principal_id="identity-principal",
                    client_id="identity-client",
                ),
            )
            active = SimpleNamespace(
                id="agent-version-resource",
                agent_guid="agent-guid",
                status="active",
                instance_identity=SimpleNamespace(
                    principal_id="identity-principal",
                    client_id="identity-client",
                ),
            )
            with (
                patch.object(publisher, "build_definition", return_value=definition),
                patch.object(
                    agents,
                    "get_version",
                    return_value=creating,
                ) as get_version,
            ):
                publisher.publish_once(
                    agents=agents,
                    project_endpoint="https://project.example.test",
                    project_id=PROJECT_ID,
                    agent_name="order-resolution",
                    archive=archive,
                    operation_id="publish-identity-timeout",
                    runtime_environment=runtime_environment(),
                    journal_path=journal,
                )
                discovered = publisher.resolve_publish_identity(
                    agents=agents,
                    agent_name="order-resolution",
                    journal_path=journal,
                    timeout_seconds=0,
                )
                with self.assertRaises(TimeoutError):
                    publisher.resolve_publish_identity(
                        agents=agents,
                        agent_name="order-resolution",
                        journal_path=journal,
                        timeout_seconds=0,
                        require_active=True,
                    )
                get_version.return_value = active
                ready = publisher.resolve_publish_identity(
                    agents=agents,
                    agent_name="order-resolution",
                    journal_path=journal,
                    timeout_seconds=0,
                    require_active=True,
                )
            record = publisher._load_record(journal)
            self.assertEqual(
                (
                    discovered.status,
                    discovered.provisioning_status,
                    ready.provisioning_status,
                    record.status,
                    record.agent_version,
                ),
                ("acknowledged", "creating", "active", "acknowledged", "7"),
            )
            self.assertEqual(record.identity_principal_id, "identity-principal")
            self.assertEqual(len(agents.calls), 1)
            self.assertEqual(get_version.call_count, 3)

    def test_publish_identity_rejects_target_model_and_runtime_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            publisher.build_source_archive(root, archive)
            journal = root / "publish.json"
            agents = FakeAgents()
            definition = hosted_definition()
            common = {
                "agents": agents,
                "project_endpoint": "https://project.example.test",
                "project_id": PROJECT_ID,
                "agent_name": "order-resolution",
                "archive": archive,
                "operation_id": "publish-bound",
                "runtime_environment": runtime_environment(),
                "journal_path": journal,
            }
            with patch.object(publisher, "build_definition", return_value=definition):
                publisher.publish_once(**common)
                conflicts = (
                    {
                        "project_endpoint": "https://other.example.test",
                        "runtime_environment": runtime_environment(
                            FOUNDRY_PROJECT_ENDPOINT="https://other.example.test"
                        ),
                    },
                    {"project_id": "/subscriptions/sub/projects/other"},
                    {"agent_name": "other-agent"},
                    {
                        "runtime_environment": runtime_environment(
                            AZURE_AI_MODEL_DEPLOYMENT_NAME="other-model"
                        )
                    },
                    {
                        "runtime_environment": runtime_environment(
                            ORDER_RESOLUTION_API_ENDPOINT=(
                                "https://other-api.example.test/internal/"
                                "order-resolution/hosted"
                            )
                        )
                    },
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
            runtime_environment=runtime_environment(),
        )
        self.assertEqual(identity["project_endpoint"], "https://project.example.test")
        self.assertEqual(identity["hosted_definition"]["runtime"], "python_3_13")
        self.assertNotIn(
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            identity["hosted_definition"]["environment"],
        )
        self.assertEqual(
            len(
                identity["hosted_definition"]["environment"][
                    "APPLICATIONINSIGHTS_CONNECTION_STRING_SHA256"
                ]
            ),
            64,
        )
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
                    runtime_environment=runtime_environment(),
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
                    runtime_environment=runtime_environment(),
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
                "runtime_environment": runtime_environment(),
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

    def test_runtime_environment_is_explicit_passwordless_and_target_bound(self):
        environment = publisher.hosted_runtime_environment(
            runtime_environment(
                DATABASE_URL="postgresql://must-not-publish",
                DATABASE_AUTH_MODE="managed-identity",
                DATABASE_TLS_MODE="verify-full",
                PGSSLROOTCERT="/must/not/publish.pem",
                AGENTSERVER_FLUSH_MODE="background",
                APPLICATIONINSIGHTS_AUTH_MODE="connection-string",
                ENABLE_SENSITIVE_DATA="true",
                ENABLE_MESSAGE_EVENTS="true",
                OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="true",
            )
        )
        self.assertEqual(
            set(environment),
            set(publisher.REQUIRED_RUNTIME_ENVIRONMENT)
            | set(publisher.PRIVACY_RUNTIME_ENVIRONMENT)
            | set(publisher.OBSERVABILITY_RUNTIME_ENVIRONMENT)
            | {"PYTHONNOUSERSITE"},
        )
        self.assertEqual(
            {name: environment[name] for name in publisher.PRIVACY_RUNTIME_ENVIRONMENT},
            publisher.PRIVACY_RUNTIME_ENVIRONMENT,
        )
        self.assertEqual(
            {
                name: environment[name]
                for name in publisher.OBSERVABILITY_RUNTIME_ENVIRONMENT
            },
            {
                "AGENTSERVER_FLUSH_MODE": "async",
                "APPLICATIONINSIGHTS_AUTH_MODE": "entra",
            },
        )
        self.assertFalse(
            {
                "DATABASE_URL",
                "DATABASE_AUTH_MODE",
                "DATABASE_TLS_MODE",
                "PGSSLROOTCERT",
            }
            & set(environment)
        )
        self.assertEqual(
            environment["ORDER_RESOLUTION_API_SCOPE"],
            "api://order-resolution-api/.default",
        )
        for invalid in (
            runtime_environment(
                ORDER_RESOLUTION_API_ENDPOINT="http://api.example.test"
            ),
            runtime_environment(ORDER_RESOLUTION_API_SCOPE="https://api.example.test"),
            runtime_environment(ORDER_RESOLUTION_API_TIMEOUT_SECONDS="0"),
            runtime_environment(ORDER_RESOLUTION_API_TIMEOUT_SECONDS="not-a-number"),
            runtime_environment(SOURCE_REVISION="not safe"),
            runtime_environment(DEPLOYMENT_REVISION="x" * 129),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    publisher.hosted_runtime_environment(invalid)
        with self.assertRaisesRegex(ValueError, "must match"):
            publisher.publication_identity(
                project_endpoint="https://other.example.test",
                project_id=PROJECT_ID,
                agent_name="order-resolution",
                archive_sha256="a" * 64,
                runtime_environment=runtime_environment(),
            )


if __name__ == "__main__":
    unittest.main()
