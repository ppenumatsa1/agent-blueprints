import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_attestation_verifier", SCRIPTS / "verify_build_attestations.py"
)
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


def policy():
    signer = (
        "https://github.com/example-builder/builds/.github/workflows/publish.yml@refs/heads/main"
    )
    return {
        "schema_version": "1",
        "source": {
            "repository": "example-owner/example-source",
            "repository_id": "1234",
            "owner_id": "42",
            "ref": "refs/heads/main",
            "revision": "1" * 40,
        },
        "subjects": {
            role: {
                "image": f"registry.example.invalid/team/{role}@sha256:{digest * 64}",
                "signer_identity": signer,
                "signer_revision": "2" * 40,
            }
            for role, digest in zip(verifier.ROLES, "abc")
        },
    }


def verified_result(source, subject):
    image = verifier.IMAGE.fullmatch(subject.image)
    source_uri = f"https://github.com/{source.repository}"
    invocation = f"{source_uri}/actions/runs/99/attempts/1"
    return [
        {
            "verificationResult": {
                "signature": {
                    "certificate": {
                        "issuer": verifier.ISSUER,
                        "subjectAlternativeName": subject.signer_identity,
                        "buildSignerURI": subject.signer_identity,
                        "buildSignerDigest": subject.signer_revision,
                        "runnerEnvironment": "github-hosted",
                        "sourceRepositoryURI": f"https://github.com/{source.repository}",
                        "sourceRepositoryOwnerURI": "https://github.com/example-owner",
                        "sourceRepositoryIdentifier": source.repository_id,
                        "sourceRepositoryOwnerIdentifier": source.owner_id,
                        "sourceRepositoryRef": source.ref,
                        "sourceRepositoryDigest": source.revision,
                        "runInvocationURI": invocation,
                    }
                },
                "statement": {
                    "_type": verifier.STATEMENT,
                    "predicateType": verifier.PREDICATE,
                    "subject": [
                        {
                            "name": image.group("name"),
                            "digest": {"sha256": image.group("digest")},
                        }
                    ],
                    "predicate": {
                        "buildDefinition": {
                            "buildType": verifier.BUILD_TYPE,
                            "externalParameters": {
                                "workflow": {"repository": source_uri, "ref": source.ref}
                            },
                            "internalParameters": {
                                "github": {
                                    "repository_id": source.repository_id,
                                    "repository_owner_id": source.owner_id,
                                    "runner_environment": "github-hosted",
                                }
                            },
                            "resolvedDependencies": [
                                {
                                    "uri": f"git+{source_uri}@{source.ref}",
                                    "digest": {"gitCommit": source.revision},
                                }
                            ],
                        },
                        "runDetails": {
                            "builder": {"id": subject.signer_identity},
                            "metadata": {"invocationId": invocation},
                        },
                    },
                },
                "verifiedTimestamps": [{"type": "Tlog", "timestamp": "2024-11-18T21:56:17Z"}],
            }
        }
    ]


def encoded(value):
    return json.dumps(value).encode("utf-8")


class BuildAttestationTests(unittest.TestCase):
    def setUp(self):
        self.source, self.subjects = verifier.parse_policy(policy())
        self.subject = self.subjects[0]
        self.result = verified_result(self.source, self.subject)

    def check(self, result):
        verifier.check_verified_result(encoded(result), self.source, self.subject)

    def test_exact_verified_result_and_three_distinct_subjects(self):
        self.check(self.result)
        document = policy()
        document["subjects"]["web"]["image"] = (
            "registry.example.invalid/team/api@sha256:" + "d" * 64
        )
        self.assertEqual(len(verifier.parse_policy(document)[1]), 3)

    def test_reusable_signer_can_be_pinned_to_its_exact_commit(self):
        document = policy()
        item = document["subjects"]["api"]
        item["signer_identity"] = item["signer_identity"].split("@")[0] + "@" + "2" * 40
        verifier.parse_policy(document)
        item["signer_revision"] = "3" * 40
        with self.assertRaises(verifier.VerificationError):
            verifier.parse_policy(document)

    def test_rejects_malformed_or_ambiguous_policy(self):
        mutations = (
            ("source id", lambda p: p["source"].update(repository_id=1234)),
            ("source ref", lambda p: p["source"].update(ref="refs/pull/62/merge")),
            ("source commit", lambda p: p["source"].update(revision="A" * 40)),
            ("signer commit", lambda p: p["subjects"]["api"].update(signer_revision="latest")),
            ("signer ref", lambda p: p["subjects"]["api"].update(signer_identity="https://x")),
            (
                "tag",
                lambda p: p["subjects"]["api"].update(image="registry.example.invalid/api:tag"),
            ),
            (
                "digest",
                lambda p: p["subjects"]["api"].update(
                    image="registry.example.invalid/api@sha256:" + "A" * 64
                ),
            ),
            (
                "implicit registry",
                lambda p: p["subjects"]["api"].update(image="team/api@sha256:" + "a" * 64),
            ),
            (
                "bad port",
                lambda p: p["subjects"]["api"].update(
                    image="registry.example.invalid:99999/api@sha256:" + "a" * 64
                ),
            ),
            (
                "duplicate",
                lambda p: p["subjects"]["web"].update(image=p["subjects"]["api"]["image"]),
            ),
            ("unknown role", lambda p: p["subjects"].update(extra={})),
            ("unknown field", lambda p: p.update(authorize_release=True)),
        )
        for label, mutate in mutations:
            document = policy()
            mutate(document)
            with self.subTest(label=label), self.assertRaises(verifier.VerificationError):
                verifier.parse_policy(document)

    def test_external_path_is_required_but_does_not_prove_independence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            project = repository / "blueprints" / "maf" / "workflow"
            project.mkdir(parents=True)
            (repository / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
            inside = repository / "policy.json"
            outside = root / "policy.json"
            for path in (inside, outside):
                path.write_bytes(encoded(policy()))
            with patch.object(verifier, "ROOT", project):
                with self.assertRaises(verifier.VerificationError):
                    verifier.read_policy(Path("relative.json"))
                with self.assertRaises(verifier.VerificationError):
                    verifier.read_policy(inside)
                self.assertEqual(verifier.read_policy(outside)[0], self.source)
                link = root / "linked-policy.json"
                try:
                    link.symlink_to(inside)
                except OSError:
                    pass
                else:
                    with self.assertRaises(verifier.VerificationError):
                        verifier.read_policy(link)

    def test_duplicate_invalid_and_oversized_json_are_rejected(self):
        for data in (
            b'{"a":{"b":1,"b":2}}',
            b'{"x":NaN}',
            b"\xff",
            b"9" * 5000,
            b" " * (verifier.MAX_BYTES + 1),
        ):
            with self.subTest(data=data[:30]), self.assertRaises(verifier.VerificationError):
                verifier._json(data, "Input")

    def test_rejects_certificate_mismatches(self):
        wrong = {
            "issuer": "https://example.invalid",
            "subjectAlternativeName": "https://example.invalid/workflow",
            "buildSignerURI": "https://example.invalid/workflow",
            "buildSignerDigest": "3" * 40,
            "runnerEnvironment": "self-hosted",
            "sourceRepositoryURI": "https://github.com/example-owner/another",
            "sourceRepositoryOwnerURI": "https://github.com/another",
            "sourceRepositoryIdentifier": "1235",
            "sourceRepositoryOwnerIdentifier": "43",
            "sourceRepositoryRef": "refs/heads/another",
            "sourceRepositoryDigest": "3" * 40,
            "runInvocationURI": "https://example.invalid/runs/99",
        }
        for field, value in wrong.items():
            result = copy.deepcopy(self.result)
            result[0]["verificationResult"]["signature"]["certificate"][field] = value
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                self.check(result)

    def test_subject_predicate_and_attestation_must_match_in_same_result(self):
        mutations = (
            lambda v: v["statement"].update(_type="https://example.invalid"),
            lambda v: v["statement"].update(predicateType="https://example.invalid"),
            lambda v: v["statement"]["subject"][0].update(name="another.example.invalid/api"),
            lambda v: v["statement"]["subject"][0]["digest"].update(sha256="b" * 64),
            lambda v: v["statement"]["subject"][0]["digest"].update(sha512="c" * 128),
            lambda v: v["statement"]["subject"].append(v["statement"]["subject"][0]),
            lambda v: v.update(verifiedTimestamps=[]),
        )
        for mutate in mutations:
            result = copy.deepcopy(self.result)
            mutate(result[0]["verificationResult"])
            with self.subTest(mutation=mutate), self.assertRaises(verifier.VerificationError):
                self.check(result)
        other = copy.deepcopy(self.result[0])
        other["verificationResult"]["signature"]["certificate"]["sourceRepositoryIdentifier"] = "0"
        for result in ([], self.result + [other], [None], {}):
            with self.subTest(result=result), self.assertRaises(verifier.VerificationError):
                self.check(result)

    def test_build_predicate_must_agree_with_the_verified_certificate(self):
        mutations = (
            lambda p: p["buildDefinition"].update(buildType="https://example.invalid"),
            lambda p: p["buildDefinition"]["externalParameters"]["workflow"].update(
                repository="https://github.com/example-owner/another"
            ),
            lambda p: p["buildDefinition"]["externalParameters"]["workflow"].update(
                ref="refs/heads/another"
            ),
            lambda p: p["buildDefinition"]["internalParameters"]["github"].update(
                repository_id="wrong"
            ),
            lambda p: p["buildDefinition"]["internalParameters"]["github"].update(
                runner_environment="self-hosted"
            ),
            lambda p: p["buildDefinition"]["resolvedDependencies"][0]["digest"].update(
                gitCommit="3" * 40
            ),
            lambda p: p["buildDefinition"]["resolvedDependencies"].append(
                p["buildDefinition"]["resolvedDependencies"][0]
            ),
            lambda p: p["runDetails"]["builder"].update(id="https://example.invalid/workflow"),
            lambda p: p["runDetails"]["metadata"].update(invocationId="https://example.invalid"),
        )
        for mutate in mutations:
            result = copy.deepcopy(self.result)
            mutate(result[0]["verificationResult"]["statement"]["predicate"])
            with self.subTest(mutation=mutate), self.assertRaises(verifier.VerificationError):
                self.check(result)

    def test_requires_well_formed_verified_timestamps(self):
        for timestamps in (
            [None],
            [{}],
            [{"type": "", "timestamp": "2024-11-18T21:56:17Z"}],
            [{"type": "Tlog", "timestamp": "not-a-time"}],
            [{"type": "Tlog", "timestamp": "2024-11-18T21:56:17"}],
        ):
            result = copy.deepcopy(self.result)
            result[0]["verificationResult"]["verifiedTimestamps"] = timestamps
            with self.subTest(timestamps=timestamps), self.assertRaises(verifier.VerificationError):
                self.check(result)

    def test_gh_verification_pins_all_identity_and_subject_controls(self):
        with patch.object(verifier, "_run", return_value=encoded(self.result)) as run:
            verifier.verify_subject(self.source, self.subject)
        self.assertEqual(
            run.call_args.args[0],
            [
                "gh",
                "attestation",
                "verify",
                f"oci://{self.subject.image}",
                "--hostname",
                "github.com",
                "--repo",
                self.source.repository,
                "--cert-identity",
                self.subject.signer_identity,
                "--cert-oidc-issuer",
                verifier.ISSUER,
                "--signer-digest",
                self.subject.signer_revision,
                "--source-digest",
                self.source.revision,
                "--source-ref",
                self.source.ref,
                "--deny-self-hosted-runners",
                "--predicate-type",
                verifier.PREDICATE,
                "--format",
                "json",
            ],
        )
        self.assertEqual(run.call_args.kwargs["timeout"], 120)

    def test_requires_supported_github_cli_and_hides_subprocess_output(self):
        for version in (b"gh version 2.96.9\n", b"gh version 3.0.0\n", b"unknown"):
            with (
                self.subTest(version=version),
                patch.object(verifier, "_run", return_value=version),
                self.assertRaises(verifier.VerificationError),
            ):
                verifier.check_gh_version()
        with patch.object(verifier, "_run", return_value=b"gh version 2.103.3\n"):
            verifier.check_gh_version()
        failures = (
            subprocess.CalledProcessError(1, ["private"], stderr=b"private token"),
            subprocess.TimeoutExpired(["private"], 1),
            OSError("private token"),
        )
        for failure in failures:
            with (
                self.subTest(failure=type(failure)),
                patch.object(verifier.subprocess, "run", side_effect=failure),
                self.assertRaises(verifier.VerificationError) as raised,
            ):
                verifier._run(["gh"], timeout=1)
            self.assertNotIn("private", str(raised.exception))

    def test_cli_requires_all_three_and_never_authorizes_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_bytes(encoded(policy()))
            stdout = io.StringIO()
            stderr = io.StringIO()
            calls = []

            def run(arguments, *, timeout):
                calls.append(arguments)
                if arguments == ["gh", "--version"]:
                    return b"gh version 2.103.3\n"
                subject = next(s for s in self.subjects if f"oci://{s.image}" in arguments)
                return encoded(verified_result(self.source, subject))

            with (
                patch.object(sys, "argv", ["verify_build_attestations.py", "--policy", str(path)]),
                patch.object(verifier, "_run", side_effect=run),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                status = verifier.main()
            output = json.loads(stdout.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(len(calls), 4)
            self.assertEqual(output["roles"], list(verifier.ROLES))
            self.assertEqual(output["build_attestations"], "verified")
            self.assertEqual(output["deployment_provenance"], "unverified")
            self.assertIs(output["release_authorized"], False)
            self.assertEqual(stderr.getvalue(), "")

    def test_cli_does_not_report_success_after_partial_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_bytes(encoded(policy()))
            stdout = io.StringIO()
            stderr = io.StringIO()
            calls = []

            def run(arguments, *, timeout):
                calls.append(arguments)
                if arguments == ["gh", "--version"]:
                    return b"gh version 2.103.3\n"
                subject = next(s for s in self.subjects if f"oci://{s.image}" in arguments)
                result = verified_result(self.source, subject)
                if subject.role == "web":
                    result[0]["verificationResult"]["signature"]["certificate"][
                        "sourceRepositoryIdentifier"
                    ] = "wrong"
                return encoded(result)

            with (
                patch.object(sys, "argv", ["verify_build_attestations.py", "--policy", str(path)]),
                patch.object(verifier, "_run", side_effect=run),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                status = verifier.main()
            self.assertEqual(status, 1)
            self.assertEqual(len(calls), 3)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("verification failed", stderr.getvalue())
            self.assertNotIn("registry.example.invalid", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
