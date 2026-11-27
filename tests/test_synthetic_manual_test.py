import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "blueprints" / "maf" / "workflow" / "scripts"
SPEC = importlib.util.spec_from_file_location(
    "offline_launcher", SCRIPTS / "run_synthetic_manual_test.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def safe_container():
    return {
        "Image": "sha256:" + "a" * 64,
        "State": {"Status": "created"},
        "Mounts": [],
        "Config": {
            "User": "65534:65534",
            "Entrypoint": ["/usr/local/bin/python", "-I", "-B", "/offline/runner.py"],
            "Cmd": ["approved"],
            "Env": ["PATH=/usr/local/bin", "LANG=C.UTF-8"],
        },
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges=true"],
            "Memory": 512 * 1024 * 1024,
            "MemorySwap": 512 * 1024 * 1024,
            "NanoCpus": 1_000_000_000,
            "PidsLimit": 64,
            "IpcMode": "private",
            "LogConfig": {"Type": "none"},
        },
    }


class SyntheticManualTestBoundaryTests(unittest.TestCase):
    def test_denies_added_execution_capabilities(self):
        baseline = safe_container()
        runner.verify_container(baseline, baseline["Image"], "approved")
        changes = {
            "HostConfig": {
                "NetworkMode": "host",
                "ReadonlyRootfs": False,
                "Privileged": True,
                "CapDrop": [],
                "CapAdd": ["SYS_ADMIN"],
                "SecurityOpt": [],
                "Memory": 0,
                "MemorySwap": -1,
                "NanoCpus": 0,
                "PidsLimit": 0,
                "Binds": ["/:/host"],
                "Tmpfs": {"/tmp": "rw"},
                "Devices": [{"PathOnHost": "/dev/sda"}],
                "DeviceRequests": [{"Count": -1}],
                "VolumesFrom": ["other"],
                "PortBindings": {"80/tcp": [{"HostPort": "8080"}]},
                "PidMode": "host",
                "IpcMode": "host",
                "UTSMode": "host",
                "ExtraHosts": ["host:host-gateway"],
                "Links": ["production:db"],
                "LogConfig": {"Type": "json-file"},
            },
            "Config": {
                "User": "0",
                "Entrypoint": ["/bin/sh"],
                "Cmd": ["arbitrary.py"],
                "Env": ["AZURE_CLIENT_SECRET=synthetic-canary"],
                "OpenStdin": True,
                "Tty": True,
                "Volumes": {"/data": {}},
                "ExposedPorts": {"80/tcp": {}},
            },
        }
        for section, entries in changes.items():
            for key, value in entries.items():
                with self.subTest(section=section, key=key):
                    changed = copy.deepcopy(baseline)
                    changed[section][key] = value
                    with self.assertRaises(RuntimeError):
                        runner.verify_container(changed, baseline["Image"], "approved")
        for key, value in (
            ("Image", "sha256:" + "b" * 64),
            ("Mounts", [{"Source": "/var/run/docker.sock"}]),
            ("State", {"Status": "running"}),
        ):
            changed = copy.deepcopy(baseline)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                runner.verify_container(changed, baseline["Image"], "approved")

    def test_denial_never_starts_and_always_removes_container(self):
        container = safe_container()
        container["HostConfig"]["NetworkMode"] = "bridge"
        with (
            patch.object(runner, "create_container", return_value="fixed-id"),
            patch.object(runner, "docker", return_value=json.dumps([container])) as docker,
        ):
            with self.assertRaises(RuntimeError):
                runner.run_test(container["Image"], "approved")
        self.assertEqual(
            [call.args for call in docker.call_args_list],
            [("inspect", "fixed-id"), ("rm", "--force", "fixed-id")],
        )

    def test_timeout_removes_container_without_success_result(self):
        container = safe_container()
        with (
            patch.object(runner, "create_container", return_value="fixed-id"),
            patch.object(
                runner,
                "docker",
                side_effect=[json.dumps([container]), subprocess.TimeoutExpired("docker", 60), ""],
            ) as docker,
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run_test(container["Image"], "approved")
        self.assertEqual(docker.call_args_list[-1].args, ("rm", "--force", "fixed-id"))

    def test_build_context_excludes_unrelated_files_and_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            for name in runner.BUILD_FILES:
                target = project / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("bundled synthetic input", encoding="utf-8")
            (project / "backend" / ".env").write_text("synthetic-canary", encoding="utf-8")
            (project / "backend" / "app" / "main.py").write_text(
                "raise RuntimeError('application must not load')", encoding="utf-8"
            )

            def build(*arguments, **kwargs):
                self.assertEqual(arguments[0], "build")
                context = Path(arguments[-1])
                self.assertEqual(
                    {p.relative_to(context).as_posix() for p in context.rglob("*") if p.is_file()},
                    set(runner.BUILD_FILES),
                )
                Path(arguments[arguments.index("--iidfile") + 1]).write_text("sha256:" + "a" * 64)
                return ""

            with patch.object(runner, "ROOT", project), patch.object(runner, "docker", build):
                self.assertEqual(runner.build_image(), "sha256:" + "a" * 64)

    def test_build_rejects_symlink_before_docker(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            outside = project / "outside.txt"
            outside.write_text("synthetic", encoding="ascii")
            linked = project / "link"
            try:
                linked.symlink_to(outside)
            except OSError:
                # Windows may disallow symlink creation; exercise the same guard deterministically.
                with (
                    patch.object(runner, "ROOT", project),
                    patch.object(runner, "BUILD_FILES", ("outside.txt",)),
                    patch.object(Path, "is_symlink", return_value=True),
                    patch.object(runner, "docker") as docker,
                ):
                    with self.assertRaises(ValueError):
                        runner.build_image()
                    docker.assert_not_called()
            else:
                with (
                    patch.object(runner, "ROOT", project),
                    patch.object(runner, "BUILD_FILES", ("link",)),
                    patch.object(runner, "docker") as docker,
                ):
                    with self.assertRaises(ValueError):
                        runner.build_image()
                    docker.assert_not_called()

    def test_no_caller_credentials_or_endpoint_overrides_forwarded(self):
        with (
            patch.dict(
                os.environ,
                {
                    "AZURE_CLIENT_SECRET": "synthetic",
                    "DATABASE_URL": "synthetic",
                    "DOCKER_HOST": "tcp://example.invalid:2375",
                    "HTTP_PROXY": "synthetic",
                    "PYTHONPATH": "synthetic",
                },
            ),
            patch.object(runner.subprocess, "run") as process,
        ):
            process.return_value.stdout = "fixed"
            with patch.object(runner, "local_endpoint", return_value="unix:///var/run/docker.sock"):
                runner.docker("version")
        environment = process.call_args.kwargs["env"]
        self.assertFalse(
            set(environment)
            & {
                "AZURE_CLIENT_SECRET",
                "DATABASE_URL",
                "DOCKER_HOST",
                "HTTP_PROXY",
                "PYTHONPATH",
            }
        )
        self.assertNotIn("shell", process.call_args.kwargs)

    def test_denies_remote_docker_endpoints(self):
        for endpoint in (
            "ssh://example.invalid",
            "tcp://example.invalid:2375",
            "npipe:////other-host/pipe/docker_engine",
        ):
            runner.local_endpoint.cache_clear()
            with (
                self.subTest(endpoint=endpoint),
                patch.object(runner, "_client", return_value=json.dumps(endpoint)),
                self.assertRaises(RuntimeError),
            ):
                runner.local_endpoint()
        runner.local_endpoint.cache_clear()

    def test_rejects_arbitrary_decisions_and_credentialed_package_indexes(self):
        with patch.object(runner, "docker") as docker:
            for value in ("callback.py", "--privileged", "approved; whoami"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    runner.create_container("image", value)
            for value in (
                "http://example.invalid/simple",
                "https://user:secret@example.invalid/simple",
                "https://example.invalid/simple?token=synthetic",
            ):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    runner.build_image(value)
            docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
