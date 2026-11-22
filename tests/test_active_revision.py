import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_active_revision import verify


DIGEST = "a" * 64


class ActiveRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.backend = self.root / "backend.json"
        self.frontend = self.root / "frontend.json"
        self.hosted = self.root / "hosted.json"
        self.output = self.root / "active.json"
        for path, name in (
            (self.backend, "backend--revision"),
            (self.frontend, "frontend--revision"),
        ):
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": name,
                            "active": True,
                            "trafficWeight": 100,
                            "healthState": "Healthy",
                            "runningState": "Running",
                            "template": {
                                "containers": [
                                    {"image": f"registry.example/app@sha256:{DIGEST}"}
                                ]
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
        self.hosted.write_text(
            json.dumps(
                {
                    "source_revision": "source-123",
                    "deployment_revision": "deployment-456",
                    "status": "active",
                    "is_active_version": True,
                    "version": "7",
                    "image": f"registry.example/agent@sha256:{DIGEST}",
                    "immutable_image_digest": True,
                    "principal_id": "opaque-principal",
                }
            ),
            encoding="utf-8",
        )

    def verify_artifact(self):
        return verify(
            self.backend,
            self.frontend,
            self.hosted,
            self.output,
            source_revision="source-123",
            deployment_revision="deployment-456",
            environment="synthetic-azure",
            expected_backend_revision="backend--revision",
            expected_frontend_revision="frontend--revision",
            expected_hosted_version="7",
        )

    def test_exact_active_revisions_and_digest_pins_pass(self):
        artifact = self.verify_artifact()
        self.assertEqual(artifact["outcome"], "passed")
        self.assertEqual(
            {item["traffic_weight"] for item in artifact["container_apps"]},
            {100},
        )
        self.assertTrue(
            all(
                item["image_digest"] == f"sha256:{DIGEST}"
                for item in artifact["container_apps"]
            )
        )

    def test_multiple_active_or_mutable_images_fail(self):
        revisions = json.loads(self.backend.read_text(encoding="utf-8"))
        revisions.append(dict(revisions[0]))
        self.backend.write_text(json.dumps(revisions), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.verify_artifact()

        self.backend.write_text(json.dumps(revisions[:1]), encoding="utf-8")
        revisions[0]["template"]["containers"][0]["image"] = (
            "registry.example/app:latest"
        )
        self.backend.write_text(json.dumps(revisions[:1]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not pinned"):
            self.verify_artifact()

    def test_hosted_version_and_revision_are_exact(self):
        hosted = json.loads(self.hosted.read_text(encoding="utf-8"))
        hosted["deployment_revision"] = "different"
        self.hosted.write_text(json.dumps(hosted), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "deployment revision"):
            self.verify_artifact()

    def test_missing_health_or_running_state_never_passes(self):
        revisions = json.loads(self.backend.read_text(encoding="utf-8"))
        revisions[0].pop("healthState")
        self.backend.write_text(json.dumps(revisions), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not healthy"):
            self.verify_artifact()

        revisions[0]["healthState"] = "Healthy"
        revisions[0].pop("runningState")
        self.backend.write_text(json.dumps(revisions), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not running"):
            self.verify_artifact()


if __name__ == "__main__":
    unittest.main()
