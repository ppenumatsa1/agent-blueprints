import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "blueprints" / "maf" / "workflow" / "backend"
SCRIPT = BACKEND / "scripts" / "verify_framework_supply_chain.py"
SPEC = importlib.util.spec_from_file_location("verify_framework_supply_chain", SCRIPT)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class MafSupplyChainTests(unittest.TestCase):
    def test_approved_core_pin_and_hash_are_consistent(self):
        version = VERIFY.verify_manifests(BACKEND)
        filename, digest = VERIFY.read_approval(BACKEND, version)
        self.assertEqual(version, "1.26.0")
        self.assertEqual(filename, "agent_framework_core-1.26.0-py3-none-any.whl")
        self.assertEqual(
            digest,
            "175b75f07e15d1bb7b6cea9cb35b965ac2528cd96e3eae8f791c85c48c7232b3",
        )

    def test_compromised_umbrella_distribution_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            self.write_manifests(backend, dependency="agent-framework==1.26.1")
            with self.assertRaisesRegex(ValueError, "Disallowed umbrella distribution"):
                VERIFY.verify_manifests(backend)

    def test_unapproved_core_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            self.write_manifests(backend, dependency="agent-framework-core==1.26.1")
            with self.assertRaisesRegex(ValueError, "exactly agent-framework-core==1.26.0"):
                VERIFY.verify_manifests(backend)

    def test_locked_graph_rejects_umbrella_and_requires_approved_core_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            self.write_manifests(backend, locked_package="agent-framework")
            with self.assertRaisesRegex(ValueError, "umbrella distribution in uv.lock"):
                VERIFY.verify_manifests(backend)

        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            self.write_manifests(backend, locked_hash="0" * 64)
            with self.assertRaisesRegex(ValueError, "approved core wheel digest is missing"):
                VERIFY.verify_manifests(backend)

    def test_unapproved_wheel_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            wheel = Path(temporary) / "agent_framework_core-1.26.0-py3-none-any.whl"
            wheel.write_bytes(b"not the approved wheel")
            with self.assertRaisesRegex(ValueError, "wheel digest mismatch"):
                VERIFY.verify_wheel(wheel, "0" * 64)

    def test_source_generated_and_container_installations_use_the_guarded_uv_lock(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        source_step = workflow.split(
            "      - name: Install uv and locked blueprint dependencies\n", 1
        )[1].split("      - name:", 1)[0]
        generated_step = workflow.split(
            "      - name: Install generated project test dependencies\n", 1
        )[1].split("      - name:", 1)[0]
        self.assertIn("python scripts/verify_framework_supply_chain.py", source_step)
        self.assertIn("uv sync --locked", source_step)
        self.assertIn(
            "$GENERATED_DIR/backend/scripts/verify_framework_supply_chain.py",
            generated_step,
        )
        self.assertIn('uv sync --locked --project "$GENERATED_DIR/backend"', generated_step)
        self.assertNotIn("pip install -r", source_step + generated_step)

        dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("pyproject.toml uv.lock", dockerfile)
        self.assertIn("scripts/verify_framework_supply_chain.py", dockerfile)
        self.assertIn("uv pip install --system --no-cache --require-hashes", dockerfile)
        self.assertIn("ca-certificates", dockerfile)
        self.assertIn("test -r /etc/ssl/certs/ca-certificates.crt", dockerfile)
        self.assertIn("SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt", dockerfile)
        self.assertIn("COPY --chown=blueprint:blueprint migrations/ migrations/", dockerfile)
        self.assertNotIn("requirements.txt", dockerfile)

    @staticmethod
    def write_manifests(
        backend: Path,
        dependency: str = "agent-framework-core==1.26.0",
        locked_package: str = "agent-framework-core",
        locked_version: str = "1.26.0",
        locked_hash: str = "175b75f07e15d1bb7b6cea9cb35b965ac2528cd96e3eae8f791c85c48c7232b3",
    ) -> None:
        backend.mkdir(parents=True, exist_ok=True)
        (backend / "pyproject.toml").write_text(
            f'[project]\ndependencies = ["{dependency}"]\n',
            encoding="utf-8",
        )
        (backend / "agent-framework-core.sha256").write_text(
            "175b75f07e15d1bb7b6cea9cb35b965ac2528cd96e3eae8f791c85c48c7232b3  "
            "agent_framework_core-1.26.0-py3-none-any.whl\n",
            encoding="ascii",
        )
        (backend / "uv.lock").write_text(
            f'version = 1\nrevision = 3\nrequires-python = "==3.12.*"\n'
            f'[[package]]\nname = "{locked_package}"\nversion = "{locked_version}"\n'
            'wheels = [{ url = "https://example.invalid/core.whl", '
            f'hash = "sha256:{locked_hash}" }}]\n',
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
