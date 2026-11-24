"""Fixed synthetic fixture, not an application loader or production approval path."""
# ruff: noqa: E402

import os
import sys

os.environ.clear()
sys.path.insert(0, "/offline")

import asyncio
import errno
import json
from pathlib import Path
import socket
from uuid import UUID

from app.workflows.workflow import create_workflow


CASE_ID = UUID("40000000-0000-4000-8000-000000000004")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def isolation_probes() -> None:
    require(not os.environ, "Unexpected inherited environment")
    require(os.getuid() == 65534 and os.getgid() == 65534, "Unexpected runtime identity")
    status = Path("/proc/self/status").read_text()
    require("CapEff:\t0000000000000000" in status, "Effective capabilities are not empty")
    require("NoNewPrivs:\t1" in status, "Privilege escalation is not disabled")
    require("Seccomp:\t2" in status, "Default syscall filtering is not active")
    require({path.name for path in Path("/sys/class/net").iterdir()} == {"lo"}, "Network exists")
    for address in ("192.0.2.1", "169.254.169.254"):
        with socket.socket() as connection:
            connection.settimeout(1)
            try:
                connection.connect((address, 80))
            except OSError as error:
                require(error.errno == errno.ENETUNREACH, "Unexpected network failure mode")
            else:
                raise RuntimeError("External or metadata network access succeeded")
    for directory in ("/offline", "/tmp", "/home"):
        try:
            with open(f"{directory}/offline-write-probe", "x", encoding="ascii") as output:
                output.write("synthetic")
        except OSError as error:
            require(error.errno == errno.EROFS, "Filesystem is not read-only")
        else:
            raise RuntimeError("Filesystem write succeeded")
    for forbidden in (
        "/var/run/docker.sock",
        "/run/docker.sock",
        "/offline/app/main.py",
        "/offline/app/infrastructure",
        "/offline/examples",
    ):
        require(not Path(forbidden).exists(), "Unexpected runtime asset")
    try:
        list(Path("/root/.azure").iterdir())
    except (PermissionError, FileNotFoundError):
        pass
    else:
        raise RuntimeError("Root credential directory is accessible")


class SyntheticRecord:
    def __init__(self) -> None:
        self.records: list[tuple[UUID, bool]] = []

    def apply_once(self, case_id: UUID, approved: bool, action: object) -> None:
        require(case_id == CASE_ID and not self.records, "Invalid or repeated synthetic case")
        self.records.append((case_id, approved))


class ForbiddenBusinessAction:
    def apply(self, *args: object) -> None:
        raise RuntimeError("Business actions are forbidden in the offline fixture")


async def run(decision: str) -> dict:
    require(decision in ("approved", "rejected"), "Unknown synthetic decision")
    store = SyntheticRecord()
    workflow = create_workflow(store, ForbiddenBusinessAction())
    requests = []
    initial_outputs = []
    async for event in workflow.run({"case_id": str(CASE_ID)}, stream=True):
        if event.type == "request_info":
            requests.append(event)
        if event.type == "output":
            initial_outputs.append(event.data)
    require(len(requests) == 1 and not initial_outputs, "Native workflow did not suspend")
    outputs = []
    async for event in workflow.run(
        responses={requests[0].request_id: decision == "approved"}, stream=True
    ):
        require(event.type != "request_info", "Unexpected second approval request")
        if event.type == "output":
            outputs.append(event.data)
    require(
        outputs == [{"case_id": str(CASE_ID), "decision": decision}]
        and store.records == [(CASE_ID, decision == "approved")],
        "Native workflow output or synthetic record mismatch",
    )
    return {
        "kind": "offline-synthetic-native-approval",
        "decision": decision,
        "requests": len(requests),
        "records": len(store.records),
        "business_effects": 0,
        "isolation_probes": "passed",
        "durable": False,
    }


if __name__ == "__main__":
    require(len(sys.argv) == 2, "Exactly one fixed decision is required")
    isolation_probes()
    print(json.dumps(asyncio.run(run(sys.argv[1])), sort_keys=True))
