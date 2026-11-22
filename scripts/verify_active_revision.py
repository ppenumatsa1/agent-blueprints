"""Verify exact active Container Apps revisions and Foundry hosted-agent version."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


DIGEST_IMAGE = re.compile(r"^.+@sha256:[a-f0-9]{64}$")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _field(value, *names):
    for name in names:
        if name in value:
            return value[name]
    return None


def _container_image(revision):
    image = revision.get("image")
    if image:
        return image
    template = revision.get("template") or revision.get("properties", {}).get(
        "template", {}
    )
    containers = template.get("containers", [])
    return containers[0].get("image") if len(containers) == 1 else None


def _verify_container(service, revisions, expected_revision):
    if not isinstance(revisions, list):
        raise ValueError(f"{service} revision evidence must be a list.")
    active = [
        revision
        for revision in revisions
        if _field(revision, "active", "isActive") is True
    ]
    if len(active) != 1:
        raise ValueError(f"{service} must have exactly one active revision.")
    revision = active[0]
    name = _field(revision, "name", "revisionName")
    if name != expected_revision:
        raise ValueError(
            f"{service} active revision does not match the expected revision."
        )
    if _field(revision, "trafficWeight", "traffic_weight") != 100:
        raise ValueError(f"{service} active revision must receive 100 percent traffic.")
    health = _field(revision, "healthState", "health_state")
    running = _field(revision, "runningState", "running_state")
    if health != "Healthy":
        raise ValueError(f"{service} active revision is not healthy.")
    if running != "Running":
        raise ValueError(f"{service} active revision is not running.")
    image = _container_image(revision)
    if not isinstance(image, str) or not DIGEST_IMAGE.fullmatch(image):
        raise ValueError(f"{service} active image is not pinned by SHA-256 digest.")
    return {
        "service": service,
        "revision": name,
        "traffic_weight": 100,
        "health_state": health,
        "running_state": running,
        "image": image,
        "image_digest": image.rsplit("@", 1)[1],
    }


def _verify_hosted_agent(
    inspection, expected_version, source_revision, deployment_revision
):
    if inspection.get("source_revision") != source_revision:
        raise ValueError("Hosted-agent inspection source revision mismatch.")
    if inspection.get("deployment_revision") != deployment_revision:
        raise ValueError("Hosted-agent inspection deployment revision mismatch.")
    if (
        inspection.get("status") != "active"
        or inspection.get("is_active_version") is not True
    ):
        raise ValueError("Hosted-agent version is not active.")
    if str(inspection.get("version")) != str(expected_version):
        raise ValueError(
            "Hosted-agent active version does not match the expected version."
        )
    image = inspection.get("image")
    if not isinstance(image, str) or not DIGEST_IMAGE.fullmatch(image):
        raise ValueError("Hosted-agent image is not pinned by SHA-256 digest.")
    immutable = inspection.get("immutable_image_digest")
    if immutable not in (True, image.rsplit("@", 1)[1]):
        raise ValueError(
            "Hosted-agent inspection did not verify an immutable image digest."
        )
    return {
        "version": str(expected_version),
        "image": image,
        "image_digest": image.rsplit("@", 1)[1],
        "principal_id_present": bool(inspection.get("principal_id")),
    }


def verify(
    backend_revisions,
    frontend_revisions,
    hosted_agent,
    output,
    *,
    source_revision,
    deployment_revision,
    environment,
    expected_backend_revision,
    expected_frontend_revision,
    expected_hosted_version,
):
    artifact = {
        "schema_version": "1.0.0",
        "source_revision": source_revision,
        "deployment_revision": deployment_revision,
        "environment": environment,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "check_id": "ACTIVE-REVISION",
        "outcome": "passed",
        "container_apps": [
            _verify_container(
                "backend",
                _read(backend_revisions),
                expected_backend_revision,
            ),
            _verify_container(
                "frontend",
                _read(frontend_revisions),
                expected_frontend_revision,
            ),
        ],
        "hosted_agent": _verify_hosted_agent(
            _read(hosted_agent),
            expected_hosted_version,
            source_revision,
            deployment_revision,
        ),
    }
    Path(output).write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-revisions", type=Path, required=True)
    parser.add_argument("--frontend-revisions", type=Path, required=True)
    parser.add_argument("--hosted-agent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--deployment-revision", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--expected-backend-revision", required=True)
    parser.add_argument("--expected-frontend-revision", required=True)
    parser.add_argument("--expected-hosted-version", required=True)
    args = parser.parse_args()
    try:
        verify(
            args.backend_revisions,
            args.frontend_revisions,
            args.hosted_agent,
            args.output,
            source_revision=args.source_revision,
            deployment_revision=args.deployment_revision,
            environment=args.environment,
            expected_backend_revision=args.expected_backend_revision,
            expected_frontend_revision=args.expected_frontend_revision,
            expected_hosted_version=args.expected_hosted_version,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(
            f"Active revision verification failed: {type(error).__name__}.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
