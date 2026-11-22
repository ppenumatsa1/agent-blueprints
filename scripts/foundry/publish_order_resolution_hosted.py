"""Package and publish the generated Order Resolution host without provisioning Azure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "2.0.0"
PYTHON_RUNTIME = "python_3_13"


@dataclass(frozen=True)
class PublishRecord:
    operation_id: str
    archive_sha256: str
    status: str
    agent_version: str | None = None


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
            "entryPoint": ["python", "main.py"],
            "dependencyResolution": "remote_build",
        },
        "env": {"PYTHONNOUSERSITE": "1"},
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
        cpu="0.5",
        memory="1Gi",
        code_configuration=CodeConfiguration(
            runtime=PYTHON_RUNTIME,
            entry_point=["python", "main.py"],
            dependency_resolution="remote_build",
        ),
        protocol_versions=[
            ProtocolVersionRecord(protocol="responses", version=PROTOCOL_VERSION)
        ],
        environment_variables={
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": model_deployment_name,
            "PYTHONNOUSERSITE": "1",
        },
    )


def _load_record(path: Path) -> PublishRecord | None:
    if not path.is_file():
        return None
    return PublishRecord(**json.loads(path.read_text(encoding="utf-8")))


def _save_record(path: Path, record: PublishRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(record), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def publish_once(
    *,
    agents: Any,
    agent_name: str,
    archive: Path,
    operation_id: str,
    model_deployment_name: str,
    journal_path: Path,
) -> PublishRecord:
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    definition = build_definition(model_deployment_name)
    existing = _load_record(journal_path)
    if existing is not None:
        if existing.operation_id != operation_id or existing.archive_sha256 != digest:
            raise ValueError("The publish journal is bound to a different operation.")
        if existing.status == "acknowledged":
            return existing
        if existing.status == "unknown":
            raise AmbiguousPublish("The prior publish is unknown and cannot be replayed.")
    with archive.open("rb") as code:
        pending = PublishRecord(operation_id, digest, "pending")
        _save_record(journal_path, pending)
        try:
            created = agents.create_version_from_code(
                agent_name=agent_name,
                definition=definition,
                code=code,
                code_zip_sha256=digest,
                description="Order Resolution native MAF Responses host.",
                metadata={
                    "publish_operation_id": operation_id,
                    "source_archive_sha256": digest,
                },
                retry_total=0,
            )
        except Exception as exc:
            _save_record(
                journal_path,
                PublishRecord(operation_id, digest, "unknown"),
            )
            raise AmbiguousPublish(
                "Hosted version creation may have applied; reconcile before any retry."
            ) from exc
    version = getattr(created, "version", None)
    if not isinstance(version, str) or not version:
        _save_record(journal_path, PublishRecord(operation_id, digest, "unknown"))
        raise AmbiguousPublish("The create response did not contain an agent version.")
    acknowledged = PublishRecord(operation_id, digest, "acknowledged", version)
    _save_record(journal_path, acknowledged)
    return acknowledged


def reconcile_publish(
    *,
    agents: Any,
    agent_name: str,
    journal_path: Path,
) -> PublishRecord:
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
            and metadata.get("source_archive_sha256") == record.archive_sha256
            and version
        ):
            matches.append(str(version))
    if len(set(matches)) != 1:
        return record
    reconciled = PublishRecord(
        record.operation_id,
        record.archive_sha256,
        "acknowledged",
        matches[0],
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
    model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "").strip()
    if not endpoint or not model:
        raise ValueError(
            "FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME are required."
        )
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    with AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential()) as project:
        record = publish_once(
            agents=project.agents,
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
