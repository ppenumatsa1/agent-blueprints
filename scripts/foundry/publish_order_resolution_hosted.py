"""Package and publish the generated Order Resolution host without provisioning Azure."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any
from uuid import uuid4


PROTOCOL_VERSION = "2.0.0"
PYTHON_RUNTIME = "python_3_13"
ENTRY_POINT = ("python", "main.py")
DEPENDENCY_RESOLUTION = "remote_build"
CPU = "0.5"
MEMORY = "1Gi"
PYTHON_NO_USER_SITE = "1"


@dataclass(frozen=True)
class PublishRecord:
    operation_id: str
    publication_digest: str
    archive_sha256: str
    status: str
    agent_version: str | None = None
    owner_token: str | None = None


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
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary)
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
    return hashlib.sha256(output.read_bytes()).hexdigest()


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


def build_definition(model_deployment_name: str) -> Any:
    if not model_deployment_name.strip():
        raise ValueError("A configured model deployment name is required.")
    from azure.ai.projects.models import (
        CodeConfiguration,
        HostedAgentDefinition,
        ProtocolVersionRecord,
    )

    return HostedAgentDefinition(
        cpu=CPU,
        memory=MEMORY,
        code_configuration=CodeConfiguration(
            runtime=PYTHON_RUNTIME,
            entry_point=list(ENTRY_POINT),
            dependency_resolution=DEPENDENCY_RESOLUTION,
        ),
        protocol_versions=[
            ProtocolVersionRecord(protocol="responses", version=PROTOCOL_VERSION)
        ],
        environment_variables={
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": model_deployment_name,
            "PYTHONNOUSERSITE": PYTHON_NO_USER_SITE,
        },
    )


def publication_identity(
    *,
    project_endpoint: str,
    project_id: str,
    agent_name: str,
    archive_sha256: str,
    model_deployment_name: str,
) -> dict[str, Any]:
    endpoint = project_endpoint.rstrip("/")
    for value, label in (
        (endpoint, "Foundry project endpoint"),
        (project_id, "Foundry project ID"),
        (agent_name, "Agent name"),
        (archive_sha256, "Archive digest"),
        (model_deployment_name, "Model deployment name"),
    ):
        if not isinstance(value, str) or not value.strip() or len(value) > 2048:
            raise ValueError(f"{label} is required and bounded.")
    if not endpoint.startswith("https://"):
        raise ValueError("The Foundry project endpoint must use HTTPS.")
    return {
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
            "environment": {
                "AZURE_AI_MODEL_DEPLOYMENT_NAME": model_deployment_name,
                "PYTHONNOUSERSITE": PYTHON_NO_USER_SITE,
            },
        },
    }


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
        )
        _save_record(journal_path, updated)
        return updated


def publish_once(
    *,
    agents: Any,
    project_endpoint: str,
    project_id: str,
    agent_name: str,
    archive: Path,
    operation_id: str,
    model_deployment_name: str,
    journal_path: Path,
) -> PublishRecord:
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    identity_digest = publication_digest(
        publication_identity(
            project_endpoint=project_endpoint,
            project_id=project_id,
            agent_name=agent_name,
            archive_sha256=digest,
            model_deployment_name=model_deployment_name,
        )
    )
    definition = build_definition(model_deployment_name)
    owner_token = uuid4().hex
    pending = PublishRecord(
        operation_id,
        identity_digest,
        digest,
        "pending",
        owner_token=owner_token,
    )
    claim = _claim_publish(journal_path, pending)
    if not claim.acquired:
        return claim.record
    with archive.open("rb") as code:
        try:
            created = agents.create_version_from_code(
                agent_name=agent_name,
                definition=definition,
                code=code,
                code_zip_sha256=digest,
                description="Order Resolution native MAF Responses host.",
                metadata={
                    "publish_operation_id": operation_id,
                    "publication_digest": identity_digest,
                    "source_archive_sha256": digest,
                },
                retry_total=0,
            )
        except Exception as exc:
            _finish_owned_publish(
                journal_path,
                owner_token=owner_token,
                status="unknown",
            )
            raise AmbiguousPublish(
                "Hosted version creation may have applied; reconcile before any retry."
            ) from exc
    version = getattr(created, "version", None)
    if not isinstance(version, str) or not version:
        _finish_owned_publish(
            journal_path,
            owner_token=owner_token,
            status="unknown",
        )
        raise AmbiguousPublish("The create response did not contain an agent version.")
    return _finish_owned_publish(
        journal_path,
        owner_token=owner_token,
        status="acknowledged",
        agent_version=version,
    )


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
    matches = []
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
            and metadata.get("source_archive_sha256") == record.archive_sha256
            and version
        ):
            matches.append(str(version))
    if len(set(matches)) != 1:
        return record
    with _journal_lock(journal_path):
        current = _load_record(journal_path)
        if current is None:
            raise ValueError("The publish journal is missing.")
        if (
            current.operation_id != record.operation_id
            or current.publication_digest != record.publication_digest
            or current.archive_sha256 != record.archive_sha256
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
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--agent-name")
    parser.add_argument("--operation-id")
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args()
    digest = build_source_archive(args.project_root, args.archive)
    print(f"ARCHIVE_SHA256={digest}")
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
    model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "").strip()
    if not endpoint or not project_id or not model:
        raise ValueError(
            "FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_PROJECT_ID, and "
            "AZURE_AI_MODEL_DEPLOYMENT_NAME are required."
        )
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
            model_deployment_name=model,
            journal_path=args.journal,
        )
    print(json.dumps(asdict(record), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise
