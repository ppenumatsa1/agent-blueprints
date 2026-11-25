"""Package and publish the generated Order Resolution host without provisioning Azure."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NoReturn
from urllib.parse import urlsplit
from uuid import uuid4


PROTOCOL_VERSION = "2.0.0"
PYTHON_RUNTIME = "python_3_13"
ENTRY_POINT = ("python", "main.py")
DEPENDENCY_RESOLUTION = "remote_build"
CPU = "0.5"
MEMORY = "1Gi"
PYTHON_NO_USER_SITE = "1"
REQUIRED_RUNTIME_ENVIRONMENT = (
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "SOURCE_REVISION",
    "DEPLOYMENT_REVISION",
    "ORDER_RESOLUTION_API_ENDPOINT",
    "ORDER_RESOLUTION_API_SCOPE",
    "ORDER_RESOLUTION_API_TIMEOUT_SECONDS",
)
PRIVACY_RUNTIME_ENVIRONMENT = {
    "ENABLE_SENSITIVE_DATA": "false",
    "ENABLE_MESSAGE_EVENTS": "false",
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
}
OBSERVABILITY_RUNTIME_ENVIRONMENT = {
    "AGENTSERVER_FLUSH_MODE": "async",
    "APPLICATIONINSIGHTS_AUTH_MODE": "entra",
}
IMAGE_REFERENCE = re.compile(
    r"(?P<registry>[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*(?::[0-9]{1,5})?)/"
    r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*)*"
    r"@sha256:[0-9a-f]{64}\Z"
)


@dataclass(frozen=True)
class PublishRecord:
    operation_id: str
    publication_digest: str
    archive_sha256: str
    status: str
    agent_version: str | None = None
    owner_token: str | None = None
    agent_version_id: str | None = None
    agent_guid: str | None = None
    provisioning_status: str | None = None
    identity_principal_id: str | None = None
    identity_client_id: str | None = None
    image_reference: str | None = None
    observed_image_reference: str | None = None
    expected_route_version: str | None = None


@dataclass(frozen=True)
class PublishClaim:
    record: PublishRecord
    acquired: bool


class AmbiguousPublish(RuntimeError):
    """The version create may have applied and must not be replayed."""


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".env",
            ".env.*",
            ".venv",
            ".uv-cache",
            ".ruff_cache",
        ),
    )


def build_source_archive(project_root: Path, output: Path) -> str:
    project_root = project_root.resolve()
    hosted = project_root / "hosted-agent"
    backend_app = project_root / "backend" / "app"
    for required in (
        hosted / "main.py",
        hosted / "requirements.txt",
        hosted / "src" / "order_resolution_hosted",
        backend_app,
    ):
        if not required.exists():
            raise ValueError(f"Generated hosted source is missing: {required}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".publish-staging-{uuid4().hex}"
    staging.mkdir()
    try:
        shutil.copy2(hosted / "main.py", staging / "main.py")
        shutil.copy2(hosted / "requirements.txt", staging / "requirements.txt")
        _copy_tree(
            hosted / "src" / "order_resolution_hosted",
            staging / "order_resolution_hosted",
        )
        _copy_tree(backend_app, staging / "app")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(path.relative_to(staging).as_posix())
                    info.date_time = (1980, 1, 1, 0, 0, 0)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    archive.writestr(info, path.read_bytes())
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def build_container_context(
    project_root: Path, archive: Path, destination: Path
) -> None:
    project_root = project_root.resolve()
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(project_root):
        raise ValueError(
            "The container context must be a new directory outside the project."
        )
    if not destination.parent.is_dir():
        raise ValueError("The container context parent directory must already exist.")
    assets = [
        project_root / "hosted-agent" / name for name in ("Dockerfile", ".dockerignore")
    ]
    if any(not asset.is_file() for asset in assets):
        raise ValueError("The generated hosted container build assets are missing.")
    destination.mkdir()
    try:
        with zipfile.ZipFile(archive) as source:
            names = set()
            for entry in source.infolist():
                name = entry.filename
                parts = name.split("/")
                path = PurePosixPath(name)
                if (
                    not name
                    or name in names
                    or entry.is_dir()
                    or path.is_absolute()
                    or path.as_posix() != name
                    or "\\" in name
                    or ":" in name
                    or any(part in ("", ".", "..") for part in parts)
                    or (
                        name not in ("main.py", "requirements.txt")
                        and (
                            len(parts) < 2
                            or parts[0] not in ("app", "order_resolution_hosted")
                        )
                    )
                ):
                    raise ValueError(
                        "The hosted source archive contains an invalid path."
                    )
                names.add(name)
                target = destination.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(entry))
            if (
                not {"main.py", "requirements.txt"}.issubset(names)
                or not any(name.startswith("app/") for name in names)
                or not any(
                    name.startswith("order_resolution_hosted/") for name in names
                )
            ):
                raise ValueError("The hosted source archive is incomplete.")
        for asset in assets:
            shutil.copy2(asset, destination / asset.name)
    except Exception:
        shutil.rmtree(destination)
        raise


def _validate_image_reference(image_reference: str) -> None:
    if not isinstance(image_reference, str) or len(image_reference) > 512:
        raise ValueError("The hosted image must be a bounded digest-pinned reference.")
    match = IMAGE_REFERENCE.fullmatch(image_reference)
    if not match:
        raise ValueError(
            "The hosted image must be a fully qualified sha256 digest reference."
        )
    host, separator, port = match.group("registry").partition(":")
    if ("." not in host and host != "localhost" and not separator) or (
        separator and not 1 <= int(port) <= 65535
    ):
        raise ValueError("The hosted image registry is invalid.")


def _validate_route_version(version: str | None) -> None:
    if not isinstance(version, str) or not re.fullmatch(r"[1-9][0-9]*", version):
        raise ValueError(
            "The expected route must identify a concrete released version."
        )


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _require_fixed_route(
    agents: Any, agent_name: str, expected_version: str | None
) -> None:
    _validate_route_version(expected_version)
    agent = agents.get(agent_name=agent_name)
    endpoint = _field(agent, "agent_endpoint")
    selector = _field(endpoint, "version_selector")
    rules = _field(selector, "version_selection_rules")
    if not isinstance(rules, (list, tuple)) or len(rules) != 1:
        raise ValueError(
            "The hosted endpoint must have one explicit fixed-version route."
        )
    rule = rules[0]
    percentage = _field(rule, "traffic_percentage")
    if (
        _text(_field(rule, "type")) != "FixedRatio"
        or _field(rule, "agent_version") != expected_version
        or type(percentage) is not int
        or percentage != 100
    ):
        raise ValueError(
            "The hosted endpoint must route 100% to the expected fixed version."
        )


def _require_configured_image(
    details: Any, expected_version: str, expected_image: str
) -> str:
    if _field(details, "version") != expected_version:
        raise ValueError("The hosted version GET did not return the expected version.")
    definition = _field(details, "definition")
    container = _field(definition, "container_configuration")
    actual_image = _field(container, "image")
    if actual_image != expected_image:
        raise ValueError(
            "The hosted version's configured image does not match the requested image."
        )
    return actual_image


def build_azd_service_contract(project: str = "hosted-agent") -> dict[str, Any]:
    return {
        "project": project,
        "host": "azure.ai.agent",
        "kind": "hosted",
        "protocols": [{"protocol": "responses", "version": PROTOCOL_VERSION}],
        "codeConfiguration": {
            "runtime": PYTHON_RUNTIME,
            "entryPoint": list(ENTRY_POINT),
            "dependencyResolution": DEPENDENCY_RESOLUTION,
        },
        "env": {"PYTHONNOUSERSITE": PYTHON_NO_USER_SITE},
    }


def hosted_runtime_environment(source: Mapping[str, str]) -> dict[str, str]:
    environment = {}
    for name in REQUIRED_RUNTIME_ENVIRONMENT:
        value = source.get(name, "")
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            raise ValueError(f"{name} is required and bounded.")
        environment[name] = value.strip()
    for name in ("SOURCE_REVISION", "DEPLOYMENT_REVISION"):
        revision = environment[name]
        if (
            len(revision) > 128
            or not revision.isascii()
            or any(
                not (character.isalnum() or character in "._:-")
                for character in revision
            )
        ):
            raise ValueError(f"{name} must be a privacy-safe identifier.")
    project = urlsplit(environment["FOUNDRY_PROJECT_ENDPOINT"])
    if (
        project.scheme != "https"
        or not project.hostname
        or project.username is not None
        or project.password is not None
    ):
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT must be an HTTPS project endpoint.")
    api = urlsplit(environment["ORDER_RESOLUTION_API_ENDPOINT"])
    if (
        api.scheme != "https"
        or not api.hostname
        or api.username is not None
        or api.password is not None
        or api.query
        or api.fragment
    ):
        raise ValueError(
            "ORDER_RESOLUTION_API_ENDPOINT must be an explicit HTTPS base URL."
        )
    scope = environment["ORDER_RESOLUTION_API_SCOPE"]
    if (
        not scope.startswith("api://")
        or not scope.endswith("/.default")
        or any(character.isspace() for character in scope)
    ):
        raise ValueError("ORDER_RESOLUTION_API_SCOPE must use api://.../.default.")
    try:
        timeout = float(environment["ORDER_RESOLUTION_API_TIMEOUT_SECONDS"])
    except ValueError as exc:
        raise ValueError(
            "ORDER_RESOLUTION_API_TIMEOUT_SECONDS must be numeric."
        ) from exc
    if timeout <= 0 or timeout > 300:
        raise ValueError("ORDER_RESOLUTION_API_TIMEOUT_SECONDS must be in (0, 300].")
    environment["PYTHONNOUSERSITE"] = PYTHON_NO_USER_SITE
    environment.update(PRIVACY_RUNTIME_ENVIRONMENT)
    environment.update(OBSERVABILITY_RUNTIME_ENVIRONMENT)
    return environment


def _publication_environment(environment: Mapping[str, str]) -> dict[str, str]:
    published = dict(environment)
    connection_string = published.pop("APPLICATIONINSIGHTS_CONNECTION_STRING")
    published["APPLICATIONINSIGHTS_CONNECTION_STRING_SHA256"] = hashlib.sha256(
        connection_string.encode("utf-8")
    ).hexdigest()
    return published


def build_definition(
    runtime_environment: Mapping[str, str], *, image_reference: str | None = None
) -> Any:
    environment = hosted_runtime_environment(runtime_environment)
    from azure.ai.projects.models import (
        CodeConfiguration,
        ContainerConfiguration,
        HostedAgentDefinition,
        ProtocolVersionRecord,
    )

    configuration: dict[str, Any]
    if image_reference is None:
        configuration = {
            "code_configuration": CodeConfiguration(
                runtime=PYTHON_RUNTIME,
                entry_point=list(ENTRY_POINT),
                dependency_resolution=DEPENDENCY_RESOLUTION,
            )
        }
    else:
        _validate_image_reference(image_reference)
        configuration = {
            "container_configuration": ContainerConfiguration(image=image_reference)
        }
    return HostedAgentDefinition(
        cpu=CPU,
        memory=MEMORY,
        protocol_versions=[
            ProtocolVersionRecord(protocol="responses", version=PROTOCOL_VERSION)
        ],
        environment_variables=environment,
        **configuration,
    )


def publication_identity(
    *,
    project_endpoint: str,
    project_id: str,
    agent_name: str,
    archive_sha256: str,
    runtime_environment: Mapping[str, str],
    image_reference: str | None = None,
    expected_route_version: str | None = None,
) -> dict[str, Any]:
    endpoint = project_endpoint.rstrip("/")
    for value, label in (
        (endpoint, "Foundry project endpoint"),
        (project_id, "Foundry project ID"),
        (agent_name, "Agent name"),
        (archive_sha256, "Archive digest"),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > 2048:
            raise ValueError(f"{label} is required and bounded.")
    if not endpoint.startswith("https://"):
        raise ValueError("The Foundry project endpoint must use HTTPS.")
    environment = hosted_runtime_environment(runtime_environment)
    if environment["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/") != endpoint:
        raise ValueError(
            "The hosted runtime project endpoint must match the publication target."
        )
    if (image_reference is None) != (expected_route_version is None):
        raise ValueError("Image publication requires an expected fixed route version.")
    identity = {
        "schema_version": "1",
        "project_endpoint": endpoint,
        "project_id": project_id,
        "agent_name": agent_name,
        "archive_sha256": archive_sha256,
        "hosted_definition": {
            "cpu": CPU,
            "memory": MEMORY,
            "runtime": PYTHON_RUNTIME,
            "entry_point": list(ENTRY_POINT),
            "dependency_resolution": DEPENDENCY_RESOLUTION,
            "protocols": [{"protocol": "responses", "version": PROTOCOL_VERSION}],
            "environment": _publication_environment(environment),
        },
    }
    if image_reference is not None:
        _validate_image_reference(image_reference)
        _validate_route_version(expected_route_version)
        hosted = identity["hosted_definition"]
        del hosted["runtime"], hosted["entry_point"], hosted["dependency_resolution"]
        hosted["container_image"] = image_reference
        identity["expected_route_version"] = expected_route_version
    return identity


def publication_digest(identity: dict[str, Any]) -> str:
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_record(path: Path) -> PublishRecord | None:
    if not path.is_file():
        return None
    return PublishRecord(**json.loads(path.read_text(encoding="utf-8")))


@contextlib.contextmanager
def _journal_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _save_record(path: Path, record: PublishRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(record), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _claim_publish(journal_path: Path, requested: PublishRecord) -> PublishClaim:
    with _journal_lock(journal_path):
        existing = _load_record(journal_path)
        if existing is None:
            _save_record(journal_path, requested)
            return PublishClaim(requested, acquired=True)
        if (
            existing.operation_id != requested.operation_id
            or existing.publication_digest != requested.publication_digest
            or existing.archive_sha256 != requested.archive_sha256
            or existing.image_reference != requested.image_reference
            or existing.expected_route_version != requested.expected_route_version
        ):
            raise ValueError(
                "The publish journal is bound to different publication identity."
            )
        if existing.status == "acknowledged":
            return PublishClaim(existing, acquired=False)
        if existing.status == "unknown":
            raise AmbiguousPublish(
                "The prior publish is unknown and cannot be replayed."
            )
        if existing.status == "not_submitted":
            _save_record(journal_path, requested)
            return PublishClaim(requested, acquired=True)
        if existing.status == "pending":
            _save_record(journal_path, replace(existing, status="unknown"))
            raise AmbiguousPublish(
                "The pending publish has no active owner proof and cannot be replayed."
            )
        raise ValueError("The publish journal contains an invalid status.")


def _finish_owned_publish(
    journal_path: Path,
    *,
    owner_token: str,
    status: str,
    agent_version: str | None = None,
    details: Any | None = None,
) -> PublishRecord:
    with _journal_lock(journal_path):
        existing = _load_record(journal_path)
        if existing is None:
            raise ValueError("The publish journal is missing.")
        if existing.status == "acknowledged":
            if status == "acknowledged" and existing.agent_version == agent_version:
                return existing
            raise ValueError("An acknowledged publish cannot change outcome.")
        if existing.owner_token != owner_token:
            raise AmbiguousPublish(
                "The publish owner claim is no longer authoritative."
            )
        updated = replace(
            existing,
            status=status,
            agent_version=agent_version,
            owner_token=None if status != "pending" else owner_token,
            **(_version_details(details) if details is not None else {}),
        )
        _save_record(journal_path, updated)
        return updated


def _raise_ambiguous_publish(
    message: str,
    *,
    agents: Any,
    agent_name: str,
    image_reference: str | None,
    expected_route_version: str | None,
    cause: Exception | None = None,
) -> NoReturn:
    if image_reference is not None:
        try:
            _require_fixed_route(agents, agent_name, expected_route_version)
        except Exception as route_error:
            raise AmbiguousPublish(
                f"{message} The expected fixed route could not be verified after create."
            ) from route_error
        message += " The expected fixed route was observed after create."
    raise AmbiguousPublish(message) from cause


def publish_once(
    *,
    agents: Any,
    project_endpoint: str,
    project_id: str,
    agent_name: str,
    archive: Path,
    operation_id: str,
    runtime_environment: Mapping[str, str],
    journal_path: Path,
    image_reference: str | None = None,
    expected_route_version: str | None = None,
) -> PublishRecord:
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    identity_digest = publication_digest(
        publication_identity(
            project_endpoint=project_endpoint,
            project_id=project_id,
            agent_name=agent_name,
            archive_sha256=digest,
            runtime_environment=runtime_environment,
            image_reference=image_reference,
            expected_route_version=expected_route_version,
        )
    )
    definition = (
        build_definition(runtime_environment)
        if image_reference is None
        else build_definition(runtime_environment, image_reference=image_reference)
    )
    owner_token = uuid4().hex
    pending = PublishRecord(
        operation_id,
        identity_digest,
        digest,
        "pending",
        owner_token=owner_token,
        image_reference=image_reference,
        expected_route_version=expected_route_version,
    )
    claim = _claim_publish(journal_path, pending)
    if not claim.acquired:
        if image_reference is not None:
            _require_fixed_route(agents, agent_name, expected_route_version)
        return claim.record
    if image_reference is not None:
        try:
            _require_fixed_route(agents, agent_name, expected_route_version)
        except Exception:
            _finish_owned_publish(
                journal_path,
                owner_token=owner_token,
                status="not_submitted",
            )
            raise
    source = (
        archive.open("rb") if image_reference is None else contextlib.nullcontext(None)
    )
    with source as code:
        try:
            metadata = {
                "publish_operation_id": operation_id,
                "publication_digest": identity_digest,
            }
            if image_reference is None:
                metadata["source_archive_sha256"] = digest
            else:
                metadata["image_reference"] = image_reference
            options = {
                "agent_name": agent_name,
                "definition": definition,
                "description": "Order Resolution native MAF Responses host.",
                "metadata": metadata,
                "retry_total": 0,
            }
            if image_reference is None:
                created = agents.create_version_from_code(
                    code=code, code_zip_sha256=digest, **options
                )
            else:
                created = agents.create_version(**options)
        except Exception as exc:
            _finish_owned_publish(
                journal_path,
                owner_token=owner_token,
                status="unknown",
            )
            _raise_ambiguous_publish(
                "Hosted version creation may have applied; reconcile before any retry.",
                agents=agents,
                agent_name=agent_name,
                image_reference=image_reference,
                expected_route_version=expected_route_version,
                cause=exc,
            )
    version = getattr(created, "version", None)
    if not isinstance(version, str) or not version:
        _finish_owned_publish(
            journal_path,
            owner_token=owner_token,
            status="unknown",
        )
        _raise_ambiguous_publish(
            "The create response did not contain an agent version; reconcile before any retry.",
            agents=agents,
            agent_name=agent_name,
            image_reference=image_reference,
            expected_route_version=expected_route_version,
        )
    record = _finish_owned_publish(
        journal_path,
        owner_token=owner_token,
        status="acknowledged",
        agent_version=version,
        details=created,
    )
    if image_reference is not None:
        _require_fixed_route(agents, agent_name, expected_route_version)
    return record


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    enum_value = getattr(value, "value", None)
    return enum_value if isinstance(enum_value, str) and enum_value else None


def _version_details(details: Any) -> dict[str, str | None]:
    identity = (
        details.get("instance_identity")
        if isinstance(details, dict)
        else getattr(details, "instance_identity", None)
    )
    read = (
        (lambda name: details.get(name))
        if isinstance(details, dict)
        else (lambda name: getattr(details, name, None))
    )
    identity_read = (
        (lambda name: identity.get(name))
        if isinstance(identity, dict)
        else (lambda name: getattr(identity, name, None))
    )
    return {
        "agent_version_id": _text(read("id")),
        "agent_guid": _text(read("agent_guid")),
        "provisioning_status": _text(read("status")),
        "identity_principal_id": _text(identity_read("principal_id")),
        "identity_client_id": _text(identity_read("client_id")),
    }


def resolve_publish_identity(
    *,
    agents: Any,
    agent_name: str,
    journal_path: Path,
    timeout_seconds: float = 600,
    poll_seconds: float = 5,
    require_active: bool = False,
) -> PublishRecord:
    if timeout_seconds < 0 or poll_seconds <= 0:
        raise ValueError("Identity polling durations are invalid.")
    deadline = time.monotonic() + timeout_seconds
    while True:
        with _journal_lock(journal_path):
            record = _load_record(journal_path)
        if (
            record is None
            or record.status != "acknowledged"
            or not record.agent_version
        ):
            raise ValueError("An acknowledged agent version is required.")
        if record.image_reference is not None:
            _validate_route_version(record.expected_route_version)
            _require_fixed_route(agents, agent_name, record.expected_route_version)
        details = agents.get_version(
            agent_name=agent_name,
            agent_version=record.agent_version,
        )
        resolved = _version_details(details)
        if record.image_reference is not None:
            resolved["observed_image_reference"] = _require_configured_image(
                details, record.agent_version, record.image_reference
            )
        identity_ready = (
            resolved["identity_principal_id"]
            and resolved["identity_client_id"]
            and resolved["agent_version_id"]
            and resolved["agent_guid"]
        )
        if identity_ready:
            with _journal_lock(journal_path):
                current = _load_record(journal_path)
                if (
                    current is None
                    or current.operation_id != record.operation_id
                    or current.publication_digest != record.publication_digest
                    or current.archive_sha256 != record.archive_sha256
                    or current.agent_version != record.agent_version
                    or current.image_reference != record.image_reference
                    or current.expected_route_version != record.expected_route_version
                ):
                    raise ValueError(
                        "The publish journal changed during identity resolution."
                    )
                updated = replace(current, **resolved)
                _save_record(journal_path, updated)
            if not require_active or resolved["provisioning_status"] == "active":
                if record.image_reference is not None:
                    _require_fixed_route(
                        agents, agent_name, record.expected_route_version
                    )
                return updated
        if require_active and resolved["provisioning_status"] == "failed":
            raise RuntimeError("The hosted agent version failed provisioning.")
        if time.monotonic() >= deadline:
            target = "active" if require_active else "its agent identity"
            raise TimeoutError(
                f"The hosted version is acknowledged but {target} is not ready."
            )
        time.sleep(poll_seconds)


def reconcile_publish(
    *,
    agents: Any,
    agent_name: str,
    journal_path: Path,
) -> PublishRecord:
    with _journal_lock(journal_path):
        record = _load_record(journal_path)
    if record is None:
        raise ValueError("The publish journal is missing.")
    if record.status == "not_submitted":
        return record
    matches = []
    try:
        for item in agents.list_versions(agent_name=agent_name):
            if isinstance(item, dict):
                metadata = item.get("metadata", {})
                version = item.get("version")
            else:
                metadata = getattr(item, "metadata", {}) or {}
                version = getattr(item, "version", None)
            if (
                metadata.get("publish_operation_id") == record.operation_id
                and metadata.get("publication_digest") == record.publication_digest
                and (
                    metadata.get("source_archive_sha256") == record.archive_sha256
                    if record.image_reference is None
                    else metadata.get("image_reference") == record.image_reference
                )
                and version
            ):
                matches.append(str(version))
    finally:
        if record.image_reference is not None:
            _validate_route_version(record.expected_route_version)
            _require_fixed_route(agents, agent_name, record.expected_route_version)
    if len(set(matches)) != 1:
        return record
    if record.image_reference is not None:
        try:
            details = agents.get_version(
                agent_name=agent_name, agent_version=matches[0]
            )
            _require_configured_image(details, matches[0], record.image_reference)
        finally:
            _require_fixed_route(agents, agent_name, record.expected_route_version)
    with _journal_lock(journal_path):
        current = _load_record(journal_path)
        if current is None:
            raise ValueError("The publish journal is missing.")
        if (
            current.operation_id != record.operation_id
            or current.publication_digest != record.publication_digest
            or current.archive_sha256 != record.archive_sha256
            or current.image_reference != record.image_reference
            or current.expected_route_version != record.expected_route_version
        ):
            raise ValueError("The publish journal changed during reconciliation.")
        if current.status == "acknowledged":
            return current
        reconciled = replace(
            current,
            status="acknowledged",
            agent_version=matches[0],
            owner_token=None,
        )
        _save_record(journal_path, reconciled)
        return reconciled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--container-context", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--image-reference")
    parser.add_argument("--expected-route-version")
    parser.add_argument("--agent-name")
    parser.add_argument("--operation-id")
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--identity-timeout-seconds", type=float, default=600)
    parser.add_argument("--require-active", action="store_true")
    args = parser.parse_args()
    if args.identity_timeout_seconds < 0:
        parser.error("--identity-timeout-seconds must be nonnegative")
    if args.container_context is not None and args.publish:
        parser.error("--container-context cannot be combined with --publish")
    if (args.image_reference is None) != (args.expected_route_version is None):
        parser.error(
            "--image-reference and --expected-route-version must be supplied together"
        )
    if args.image_reference is not None and not args.publish:
        parser.error("--image-reference requires --publish")
    digest = build_source_archive(args.project_root, args.archive)
    print(f"ARCHIVE_SHA256={digest}")
    if args.container_context is not None:
        build_container_context(args.project_root, args.archive, args.container_context)
        print(f"CONTAINER_CONTEXT={args.container_context}")
    if not args.publish:
        return 0
    for name, value in (
        ("--agent-name", args.agent_name),
        ("--operation-id", args.operation_id),
        ("--journal", args.journal),
    ):
        if not value:
            parser.error(f"{name} is required with --publish")
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    project_id = os.environ.get("FOUNDRY_PROJECT_ID", "").strip()
    if not endpoint or not project_id:
        raise ValueError(
            "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_PROJECT_ID are required."
        )
    runtime_environment = hosted_runtime_environment(os.environ)
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    with AIProjectClient(
        endpoint=endpoint, credential=DefaultAzureCredential()
    ) as project:
        record = publish_once(
            agents=project.agents,
            project_endpoint=endpoint,
            project_id=project_id,
            agent_name=args.agent_name,
            archive=args.archive,
            operation_id=args.operation_id,
            runtime_environment=runtime_environment,
            journal_path=args.journal,
            image_reference=args.image_reference,
            expected_route_version=args.expected_route_version,
        )
        record = resolve_publish_identity(
            agents=project.agents,
            agent_name=args.agent_name,
            journal_path=args.journal,
            timeout_seconds=args.identity_timeout_seconds,
            require_active=args.require_active,
        )
    print(json.dumps(asdict(record), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise
