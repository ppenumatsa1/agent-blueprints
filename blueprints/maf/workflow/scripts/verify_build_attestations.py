"""Verify three OCI build attestations; this is not a deployment authorization."""

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PREDICATE = "https://slsa.dev/provenance/v1"
STATEMENT = "https://in-toto.io/Statement/v1"
BUILD_TYPE = "https://actions.github.io/buildtypes/workflow/v1"
ISSUER = "https://token.actions.githubusercontent.com"
ROLES = ("api", "web", "foundry")
SHA = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
REF = re.compile(r"refs/(?:heads|tags)/[A-Za-z0-9._/-]+\Z")
IDENTITY = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
    r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml@"
    r"(?P<ref>refs/(?:heads|tags)/[A-Za-z0-9._/-]+|[0-9a-f]{40})\Z"
)
IMAGE = re.compile(
    r"(?P<name>(?P<registry>[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*(?::[0-9]{1,5})?)/"
    r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*)*)"
    r"@sha256:(?P<digest>[0-9a-f]{64})\Z"
)
MAX_BYTES = 5 * 1024 * 1024


class VerificationError(ValueError):
    """The build attestation or its independently supplied policy is invalid."""


@dataclass(frozen=True)
class Source:
    repository: str
    repository_id: str
    owner_id: str
    ref: str
    revision: str


@dataclass(frozen=True)
class Subject:
    role: str
    image: str
    signer_identity: str
    signer_revision: str


def _object(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise VerificationError(f"{label} has missing or unexpected fields")
    return value


def _text(value, label, maximum=512):
    if not isinstance(value, str) or not value or len(value) > maximum or not value.isascii():
        raise VerificationError(f"{label} must be a bounded ASCII string")
    return value


def _valid_ref(value):
    return (
        bool(REF.fullmatch(value))
        and not any(part in value for part in ("..", "//", "@{"))
        and not value.endswith(("/", "."))
    )


def _image(value):
    match = IMAGE.fullmatch(value)
    if not match:
        return None
    host, separator, port = match.group("registry").partition(":")
    if ("." not in host and host != "localhost" and not separator) or (
        separator and not 1 <= int(port) <= 65535
    ):
        return None
    return match


def _json(data, label):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise VerificationError(f"{label} has duplicate keys")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise VerificationError(f"{label} contains a non-finite number")

    if len(data) > MAX_BYTES:
        raise VerificationError(f"{label} is too large")
    try:
        return json.loads(data, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    except VerificationError:
        raise
    except (ValueError, RecursionError) as error:
        raise VerificationError(f"{label} is not valid JSON") from error


def _is_project_path(path):
    root = ROOT.resolve()
    if path.is_relative_to(root):
        return True
    return any(
        (ancestor / ".git").exists() and path.is_relative_to(ancestor) for ancestor in root.parents
    )


def read_policy(path):
    path = Path(path)
    if not path.is_absolute():
        raise VerificationError("Policy path must be absolute and independently administered")
    try:
        resolved = path.resolve(strict=True)
        if _is_project_path(resolved):
            raise VerificationError("Policy must be outside the project being assessed")
        with resolved.open("rb") as file:
            data = file.read(MAX_BYTES + 1)
    except (OSError, RuntimeError) as error:
        raise VerificationError("Cannot read the independent policy") from error
    return parse_policy(_json(data, "Policy"))


def parse_policy(document):
    policy = _object(document, ("schema_version", "source", "subjects"), "Policy")
    if policy["schema_version"] != "1":
        raise VerificationError("Unsupported policy version")
    data = _object(
        policy["source"],
        ("repository", "repository_id", "owner_id", "ref", "revision"),
        "Source policy",
    )
    source = Source(**{key: _text(value, f"source.{key}") for key, value in data.items()})
    if (
        not REPOSITORY.fullmatch(source.repository)
        or ".." in source.repository
        or not re.fullmatch(r"[1-9][0-9]*", source.repository_id)
        or not re.fullmatch(r"[1-9][0-9]*", source.owner_id)
        or not _valid_ref(source.ref)
        or not SHA.fullmatch(source.revision)
    ):
        raise VerificationError("Source policy contains an invalid identity or revision")
    entries = _object(policy["subjects"], ROLES, "Subject policy")
    subjects = []
    for role in ROLES:
        item = _object(entries[role], ("image", "signer_identity", "signer_revision"), role)
        subject = Subject(
            role=role,
            image=_text(item["image"], f"{role}.image"),
            signer_identity=_text(item["signer_identity"], f"{role}.signer_identity"),
            signer_revision=_text(item["signer_revision"], f"{role}.signer_revision"),
        )
        identity = IDENTITY.fullmatch(subject.signer_identity)
        signer_ref = identity.group("ref") if identity else ""
        if (
            not _image(subject.image)
            or not identity
            or not (_valid_ref(signer_ref) or SHA.fullmatch(signer_ref))
            or not SHA.fullmatch(subject.signer_revision)
            or (SHA.fullmatch(signer_ref) and signer_ref != subject.signer_revision)
        ):
            raise VerificationError(f"{role} policy contains an invalid image or signer")
        subjects.append(subject)
    if len({subject.image for subject in subjects}) != len(ROLES):
        raise VerificationError("API, web and Foundry must identify distinct image subjects")
    return source, tuple(subjects)


def _run(arguments, *, timeout):
    try:
        return subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            timeout=timeout,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise VerificationError(
            f"GitHub CLI verification failed (exit {error.returncode})"
        ) from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VerificationError("GitHub CLI unavailable or verification timed out") from error


def check_gh_version():
    output = _run(["gh", "--version"], timeout=10)
    match = re.match(rb"gh version ([0-9]+)\.([0-9]+)\.([0-9]+)(?:\s|$)", output)
    if not match or not (b"2" == match.group(1) and tuple(map(int, match.groups())) >= (2, 97, 0)):
        raise VerificationError("GitHub CLI 2.97.0 or later within major version 2 is required")


def _has_verified_timestamps(value):
    if not isinstance(value, list) or not value:
        return False
    for entry in value:
        if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
            return False
        if not entry["type"] or not isinstance(entry.get("timestamp"), str):
            return False
        try:
            timestamp = datetime.fromisoformat(entry["timestamp"])
            if timestamp.utcoffset() is None:
                return False
        except ValueError:
            return False
    return True


def _matches_build_predicate(statement, certificate, source, subject):
    try:
        predicate = statement["predicate"]
        build = predicate["buildDefinition"]
        workflow = build["externalParameters"]["workflow"]
        github = build["internalParameters"]["github"]
        dependencies = build["resolvedDependencies"]
        details = predicate["runDetails"]
        invocation = certificate["runInvocationURI"]
        source_uri = f"https://github.com/{source.repository}"
        dependency_uri = f"git+{source_uri}@{source.ref}"
        if not isinstance(dependencies, list):
            return False
        matching = [
            item
            for item in dependencies
            if isinstance(item, dict) and item.get("uri") == dependency_uri
        ]
        return (
            build["buildType"] == BUILD_TYPE
            and workflow["repository"] == source_uri
            and workflow["ref"] == source.ref
            and github["repository_id"] == source.repository_id
            and github["repository_owner_id"] == source.owner_id
            and github["runner_environment"] == "github-hosted"
            and len(matching) == 1
            and matching[0]["digest"]["gitCommit"] == source.revision
            and details["builder"]["id"] == subject.signer_identity
            and isinstance(invocation, str)
            and re.fullmatch(
                rf"{re.escape(source_uri)}/actions/runs/[1-9][0-9]*/attempts/[1-9][0-9]*",
                invocation,
            )
            is not None
            and details["metadata"]["invocationId"] == invocation
        )
    except (KeyError, TypeError):
        return False


def check_verified_result(data, source, subject):
    results = _json(data, f"{subject.role} verification result")
    if not isinstance(results, list) or len(results) != 1:
        raise VerificationError(f"{subject.role} requires exactly one verified attestation")
    try:
        verified = results[0]["verificationResult"]
        certificate = verified["signature"]["certificate"]
        statement = verified["statement"]
        timestamps = verified["verifiedTimestamps"]
        image = _image(subject.image)
        expected_certificate = {
            "issuer": ISSUER,
            "subjectAlternativeName": subject.signer_identity,
            "buildSignerURI": subject.signer_identity,
            "buildSignerDigest": subject.signer_revision,
            "runnerEnvironment": "github-hosted",
            "sourceRepositoryURI": f"https://github.com/{source.repository}",
            "sourceRepositoryOwnerURI": f"https://github.com/{source.repository.split('/')[0]}",
            "sourceRepositoryIdentifier": source.repository_id,
            "sourceRepositoryOwnerIdentifier": source.owner_id,
            "sourceRepositoryRef": source.ref,
            "sourceRepositoryDigest": source.revision,
        }
        if (
            not isinstance(certificate, dict)
            or any(certificate.get(key) != value for key, value in expected_certificate.items())
            or not _has_verified_timestamps(timestamps)
            or not isinstance(statement, dict)
            or statement.get("_type") != STATEMENT
            or statement.get("predicateType") != PREDICATE
            or not _matches_build_predicate(statement, certificate, source, subject)
            or not image
            or statement.get("subject")
            != [{"name": image.group("name"), "digest": {"sha256": image.group("digest")}}]
        ):
            raise VerificationError(f"{subject.role} certificate or subject does not match policy")
    except (KeyError, TypeError, IndexError) as error:
        raise VerificationError(f"{subject.role} verification result is incomplete") from error


def verify_subject(source, subject):
    output = _run(
        [
            "gh",
            "attestation",
            "verify",
            f"oci://{subject.image}",
            "--hostname",
            "github.com",
            "--repo",
            source.repository,
            "--cert-identity",
            subject.signer_identity,
            "--cert-oidc-issuer",
            ISSUER,
            "--signer-digest",
            subject.signer_revision,
            "--source-digest",
            source.revision,
            "--source-ref",
            source.ref,
            "--deny-self-hosted-runners",
            "--predicate-type",
            PREDICATE,
            "--format",
            "json",
        ],
        timeout=120,
    )
    check_verified_result(output, source, subject)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    args = parser.parse_args()
    try:
        source, subjects = read_policy(args.policy)
        check_gh_version()
        for subject in subjects:
            verify_subject(source, subject)
    except VerificationError as error:
        print(f"Build attestation verification failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "build_attestations": "verified",
                "source_revision": source.revision,
                "roles": list(ROLES),
                "deployment_provenance": "unverified",
                "release_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
