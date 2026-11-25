import importlib.util
import json
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
IMAGE = "registry.example.test/order-resolution@sha256:" + "a" * 64
OTHER_IMAGE = "registry.example.test/order-resolution@sha256:" + "b" * 64


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


class ImageAgents(FakeAgents):
    def __init__(self):
        super().__init__()
        self.route = {
            "agent_endpoint": {
                "version_selector": {
                    "version_selection_rules": [
                        {
                            "type": "FixedRatio",
                            "agent_version": "9",
                            "traffic_percentage": 100,
                        }
                    ]
                }
            }
        }
        self.observed_image = IMAGE

    def get(self, *, agent_name):
        return self.route

    def create_version(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("ack lost")
        return SimpleNamespace(version="10")

    def get_version(self, *, agent_name, agent_version):
        details = super().get_version(
            agent_name=agent_name,
            agent_version=agent_version,
        )
        details.version = agent_version
        details.definition = {"container_configuration": {"image": self.observed_image}}
        return details


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
        (root / "hosted-agent" / "Dockerfile").write_text(
            "FROM python:3.13-slim\n", encoding="utf-8"
        )
        (root / "hosted-agent" / ".dockerignore").write_text(
            "**/.env\n", encoding="utf-8"
        )

    def image_publish_arguments(self, root, agents):
        return {
            "agents": agents,
            "project_endpoint": "https://project.example.test",
            "project_id": PROJECT_ID,
            "agent_name": "order-resolution",
            "archive": root / "agent.zip",
            "operation_id": "image-publish",
            "runtime_environment": runtime_environment(),
            "journal_path": root / "image-publish.json",
            "image_reference": IMAGE,
            "expected_route_version": "9",
        }

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

    def test_container_context_uses_only_packaged_source_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            self.generated_tree(project)
            (project / "backend" / "app" / ".env").write_text(
                "private", encoding="utf-8"
            )
            (project / "hosted-agent" / "not-packaged.txt").write_text(
                "private", encoding="utf-8"
            )
            archive = root / "agent.zip"
            publisher.build_source_archive(project, archive)
            context = root / "context"
            publisher.build_container_context(project, archive, context)
            with zipfile.ZipFile(archive) as source:
                packaged = set(source.namelist())
                for name in packaged:
                    self.assertEqual((context / name).read_bytes(), source.read(name))
            self.assertEqual(
                {
                    p.relative_to(context).as_posix()
                    for p in context.rglob("*")
                    if p.is_file()
                },
                packaged | {"Dockerfile", ".dockerignore"},
            )
            self.assertFalse((context / "app" / ".env").exists())
            with self.assertRaises(ValueError):
                publisher.build_container_context(project, archive, context)
            with self.assertRaises(ValueError):
                publisher.build_container_context(project, archive, project / "context")
            with zipfile.ZipFile(archive, "a") as source:
                source.writestr("../escaped.txt", "no")
            with self.assertRaises(ValueError):
                publisher.build_container_context(project, archive, root / "invalid")
            self.assertFalse((root / "escaped.txt").exists())
            self.assertFalse((root / "invalid").exists())

    def test_image_publication_binds_digest_route_and_observed_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            publisher.build_source_archive(root, root / "agent.zip")
            agents = ImageAgents()
            arguments = self.image_publish_arguments(root, agents)
            definition = hosted_definition()
            with patch.object(publisher, "build_definition", return_value=definition):
                created = publisher.publish_once(**arguments)
                resolved = publisher.resolve_publish_identity(
                    agents=agents,
                    agent_name="order-resolution",
                    journal_path=root / "image-publish.json",
                    timeout_seconds=0,
                    require_active=True,
                )
                repeated = publisher.publish_once(**arguments)
                for changes in (
                    {"image_reference": OTHER_IMAGE},
                    {"expected_route_version": "8"},
                ):
                    with self.subTest(changes=changes):
                        with self.assertRaisesRegex(ValueError, "publication identity"):
                            publisher.publish_once(**(arguments | changes))
            self.assertEqual(len(agents.calls), 1)
            self.assertEqual(agents.calls[0]["retry_total"], 0)
            self.assertNotIn("code", agents.calls[0])
            self.assertNotIn("source_archive_sha256", agents.calls[0]["metadata"])
            self.assertEqual(agents.calls[0]["metadata"]["image_reference"], IMAGE)
            self.assertEqual(created.agent_version, "10")
            self.assertEqual(resolved.observed_image_reference, IMAGE)
            self.assertEqual(repeated.agent_version, "10")

    def test_image_references_and_route_fail_closed_before_create(self):
        invalid_images = (
            "registry.example.test/order-resolution:latest",
            "registry.example.test/order-resolution@sha256:" + "A" * 64,
            "registry.example.test/order-resolution@sha256:" + "a" * 63,
            "registry.example.test:99999/order-resolution@sha256:" + "a" * 64,
            "order-resolution@sha256:" + "a" * 64,
            "https://registry.example.test/order-resolution@sha256:" + "a" * 64,
        )
        invalid_routes = (
            None,
            {},
            {"agent_endpoint": {"version_selector": {"version_selection_rules": []}}},
            {
                "agent_endpoint": {
                    "version_selector": {
                        "version_selection_rules": [
                            {
                                "type": "FixedRatio",
                                "agent_version": "@latest",
                                "traffic_percentage": 100,
                            }
                        ]
                    }
                }
            },
            {
                "agent_endpoint": {
                    "version_selector": {
                        "version_selection_rules": [
                            {
                                "type": "FixedRatio",
                                "agent_version": "9",
                                "traffic_percentage": 100,
                            },
                            {
                                "type": "FixedRatio",
                                "agent_version": "8",
                                "traffic_percentage": 0,
                            },
                        ]
                    }
                }
            },
            {
                "agent_endpoint": {
                    "version_selector": {
                        "version_selection_rules": [
                            {
                                "type": "FixedRatio",
                                "agent_version": "9",
                                "traffic_percentage": 50,
                            }
                        ]
                    }
                }
            },
            {
                "agent_endpoint": {
                    "version_selector": {
                        "version_selection_rules": [
                            {
                                "type": "FixedRatio",
                                "agent_version": "8",
                                "traffic_percentage": 100,
                            }
                        ]
                    }
                }
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            publisher.build_source_archive(root, root / "agent.zip")
            agents = ImageAgents()
            arguments = self.image_publish_arguments(root, agents)
            with patch.object(
                publisher, "build_definition", return_value=hosted_definition()
            ):
                for image in invalid_images:
                    with self.subTest(image=image):
                        with self.assertRaises(ValueError):
                            publisher.publish_once(
                                **(arguments | {"image_reference": image})
                            )
                for version in (None, "", "@latest", "draft-123", "0"):
                    with self.subTest(expected_route_version=version):
                        with self.assertRaises(ValueError):
                            publisher.publish_once(
                                **(arguments | {"expected_route_version": version})
                            )
                for route in invalid_routes:
                    with self.subTest(route=route):
                        agents.route = route
                        with self.assertRaises(ValueError):
                            publisher.publish_once(**arguments)
                self.assertEqual(agents.calls, [])
                self.assertEqual(
                    publisher._load_record(root / "image-publish.json").status,
                    "not_submitted",
                )
                agents.route = ImageAgents().route
                publisher.publish_once(**arguments)
            self.assertEqual(len(agents.calls), 1)

    def test_route_change_during_image_create_is_reported_without_replaying(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            publisher.build_source_archive(root, root / "agent.zip")
            agents = ImageAgents()
            arguments = self.image_publish_arguments(root, agents)
            create = agents.create_version

            def create_and_change_route(**kwargs):
                result = create(**kwargs)
                agents.route["agent_endpoint"]["version_selector"][
                    "version_selection_rules"
                ][0]["agent_version"] = "@latest"
                return result

            agents.create_version = create_and_change_route
            with patch.object(
                publisher, "build_definition", return_value=hosted_definition()
            ):
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, "route"):
                        publisher.publish_once(**arguments)
            record = publisher._load_record(root / "image-publish.json")
            self.assertEqual(
                (record.status, record.agent_version), ("acknowledged", "10")
            )
            self.assertEqual(len(agents.calls), 1)
            with self.assertRaisesRegex(ValueError, "route"):
                publisher.resolve_publish_identity(
                    agents=agents,
                    agent_name="order-resolution",
                    journal_path=root / "image-publish.json",
                    timeout_seconds=0,
                )

    def test_ambiguous_image_create_and_reconciliation_recheck_route(self):
        for outcome in ("timeout", "missing_version"):
            with (
                self.subTest(outcome=outcome),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                self.generated_tree(root)
                publisher.build_source_archive(root, root / "agent.zip")
                agents = ImageAgents()
                arguments = self.image_publish_arguments(root, agents)

                def ambiguous_create(**kwargs):
                    agents.calls.append(kwargs)
                    agents.route["agent_endpoint"]["version_selector"][
                        "version_selection_rules"
                    ][0]["agent_version"] = "@latest"
                    if outcome == "timeout":
                        raise TimeoutError("ack lost")
                    return SimpleNamespace(version=None)

                agents.create_version = ambiguous_create
                with patch.object(
                    publisher, "build_definition", return_value=hosted_definition()
                ):
                    with self.assertRaisesRegex(
                        publisher.AmbiguousPublish, "fixed route could not be verified"
                    ):
                        publisher.publish_once(**arguments)
                    with self.assertRaises(publisher.AmbiguousPublish):
                        publisher.publish_once(**arguments)
                self.assertEqual(len(agents.calls), 1)
                self.assertEqual(
                    publisher._load_record(root / "image-publish.json").status,
                    "unknown",
                )

                for listing in ("empty", "error"):
                    with self.subTest(listing=listing):
                        agents.route = ImageAgents().route

                        def changed_route_during_list(*, agent_name):
                            agents.route["agent_endpoint"]["version_selector"][
                                "version_selection_rules"
                            ][0]["agent_version"] = "@latest"
                            if listing == "error":
                                raise TimeoutError("list failed")
                            return []

                        with patch.object(
                            agents,
                            "list_versions",
                            side_effect=changed_route_during_list,
                        ):
                            with self.assertRaisesRegex(ValueError, "route") as error:
                                publisher.reconcile_publish(
                                    agents=agents,
                                    agent_name="order-resolution",
                                    journal_path=root / "image-publish.json",
                                )
                        if listing == "error":
                            self.assertIsInstance(
                                error.exception.__context__, TimeoutError
                            )
                        self.assertEqual(
                            publisher._load_record(root / "image-publish.json").status,
                            "unknown",
                        )

                record = publisher._load_record(root / "image-publish.json")
                agents.route = ImageAgents().route
                agents.versions = [
                    {
                        "version": "10",
                        "metadata": {
                            "publish_operation_id": record.operation_id,
                            "publication_digest": record.publication_digest,
                            "image_reference": IMAGE,
                        },
                    }
                ]
                get_version = agents.get_version

                def changed_route_during_get(**kwargs):
                    details = get_version(**kwargs)
                    agents.route["agent_endpoint"]["version_selector"][
                        "version_selection_rules"
                    ][0]["agent_version"] = "@latest"
                    return details

                with patch.object(
                    agents, "get_version", side_effect=changed_route_during_get
                ):
                    with self.assertRaisesRegex(ValueError, "route"):
                        publisher.reconcile_publish(
                            agents=agents,
                            agent_name="order-resolution",
                            journal_path=root / "image-publish.json",
                        )
                self.assertEqual(
                    publisher._load_record(root / "image-publish.json").status,
                    "unknown",
                )

    def test_ambiguous_image_create_reports_unavailable_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            publisher.build_source_archive(root, root / "agent.zip")
            agents = ImageAgents()
            agents.fail = True
            get = agents.get

            def unavailable_after_create(**kwargs):
                if agents.calls:
                    raise TimeoutError("route unavailable")
                return get(**kwargs)

            with (
                patch.object(
                    publisher, "build_definition", return_value=hosted_definition()
                ),
                patch.object(agents, "get", side_effect=unavailable_after_create),
            ):
                with self.assertRaisesRegex(
                    publisher.AmbiguousPublish, "fixed route could not be verified"
                ) as error:
                    publisher.publish_once(**self.image_publish_arguments(root, agents))
            self.assertIsInstance(error.exception.__cause__, TimeoutError)
            self.assertEqual(
                publisher._load_record(root / "image-publish.json").status, "unknown"
            )
            self.assertEqual(len(agents.calls), 1)

    def test_image_mismatch_and_ambiguous_create_are_not_replayed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            publisher.build_source_archive(root, root / "agent.zip")
            agents = ImageAgents()
            agents.fail = True
            arguments = self.image_publish_arguments(root, agents)
            with patch.object(
                publisher, "build_definition", return_value=hosted_definition()
            ):
                with self.assertRaisesRegex(
                    publisher.AmbiguousPublish, "fixed route was observed"
                ):
                    publisher.publish_once(**arguments)
                with self.assertRaises(publisher.AmbiguousPublish):
                    publisher.publish_once(**arguments)
            self.assertEqual(len(agents.calls), 1)
            record = publisher._load_record(root / "image-publish.json")
            agents.versions = [
                {
                    "version": "10",
                    "metadata": {
                        "publish_operation_id": record.operation_id,
                        "publication_digest": record.publication_digest,
                        "image_reference": IMAGE,
                    },
                }
            ]
            agents.observed_image = OTHER_IMAGE
            with self.assertRaisesRegex(ValueError, "image"):
                publisher.reconcile_publish(
                    agents=agents,
                    agent_name="order-resolution",
                    journal_path=root / "image-publish.json",
                )
            self.assertEqual(
                publisher._load_record(root / "image-publish.json").status, "unknown"
            )
            agents.observed_image = IMAGE
            get_version = agents.get_version

            def wrong_version(**kwargs):
                details = get_version(**kwargs)
                details.version = "11"
                return details

            with patch.object(agents, "get_version", side_effect=wrong_version):
                with self.assertRaisesRegex(ValueError, "expected version"):
                    publisher.reconcile_publish(
                        agents=agents,
                        agent_name="order-resolution",
                        journal_path=root / "image-publish.json",
                    )
            self.assertEqual(
                publisher._load_record(root / "image-publish.json").status, "unknown"
            )
            publisher.reconcile_publish(
                agents=agents,
                agent_name="order-resolution",
                journal_path=root / "image-publish.json",
            )
            with patch.object(agents, "get_version", side_effect=wrong_version):
                with self.assertRaisesRegex(ValueError, "expected version"):
                    publisher.resolve_publish_identity(
                        agents=agents,
                        agent_name="order-resolution",
                        journal_path=root / "image-publish.json",
                        timeout_seconds=0,
                    )
            agents.observed_image = OTHER_IMAGE
            with self.assertRaisesRegex(ValueError, "image"):
                publisher.resolve_publish_identity(
                    agents=agents,
                    agent_name="order-resolution",
                    journal_path=root / "image-publish.json",
                    timeout_seconds=0,
                )
            self.assertEqual(len(agents.calls), 1)

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

    def test_existing_source_publish_journal_remains_reusable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.generated_tree(root)
            archive = root / "agent.zip"
            publisher.build_source_archive(root, archive)
            journal = root / "publish.json"
            agents = FakeAgents()
            arguments = {
                "agents": agents,
                "project_endpoint": "https://project.example.test",
                "project_id": PROJECT_ID,
                "agent_name": "order-resolution",
                "archive": archive,
                "operation_id": "existing-source-publish",
                "runtime_environment": runtime_environment(),
                "journal_path": journal,
            }
            with patch.object(
                publisher, "build_definition", return_value=hosted_definition()
            ):
                created = publisher.publish_once(**arguments)
                legacy = json.loads(journal.read_text(encoding="utf-8"))
                for name in (
                    "image_reference",
                    "observed_image_reference",
                    "expected_route_version",
                ):
                    del legacy[name]
                journal.write_text(json.dumps(legacy), encoding="utf-8")
                repeated = publisher.publish_once(**arguments)
            self.assertEqual(created.agent_version, repeated.agent_version)
            self.assertEqual(len(agents.calls), 1)

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
