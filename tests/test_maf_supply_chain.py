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
            (backend / "requirements.txt").write_text(
                "agent-framework-core==1.26.0\nagent-framework==1.26.1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Disallowed umbrella distribution"):
                VERIFY.verify_manifests(backend)

    def test_unapproved_core_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            backend = Path(temporary)
            (backend / "requirements.txt").write_text(
                "agent-framework-core==1.26.1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "exactly agent-framework-core==1.26.0"):
                VERIFY.verify_manifests(backend)

    def test_unapproved_wheel_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            wheel = Path(temporary) / "agent_framework_core-1.26.0-py3-none-any.whl"
            wheel.write_bytes(b"not the approved wheel")
            with self.assertRaisesRegex(ValueError, "wheel digest mismatch"):
                VERIFY.verify_wheel(wheel, "0" * 64)


if __name__ == "__main__":
    unittest.main()
