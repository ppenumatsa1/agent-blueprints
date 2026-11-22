"""Run the real service/host in a subprocess with test-only crash barriers."""

import argparse
import asyncio
import os
import time
from pathlib import Path
from uuid import UUID

from app.workflows.host import LocalWorkflowHost
from app.domain.models import Principal
from app.domain.policy import CaseAccessPolicy, JsonObjectRules
from app.usecases.service import WorkflowService
from app.infrastructure.store import PostgresStore
from tests.fixture_application import FixtureAction


class BarrierStore(PostgresStore):
    def __init__(self, dsn: str, barrier: str | None, marker: Path | None):
        super().__init__(dsn)
        self.barrier = barrier
        self.marker = marker

    def _wait(self, name: str) -> None:
        if self.barrier == name:
            if self.marker is None:
                raise ValueError("A barrier requires a marker path.")
            self.marker.write_text(name, encoding="utf-8")
            while True:
                time.sleep(1)

    def record_decision(self, case_id, actor, decision):
        case = super().record_decision(case_id, actor, decision)
        self._wait("after-decision")
        return case

    def apply_once(self, case_id, approved, action):
        super().apply_once(case_id, approved, action)
        if approved:
            self._wait("after-action")


async def run(args) -> None:
    store = BarrierStore(os.environ["MAF_TEST_DATABASE_URL"], args.barrier, args.marker)
    host = LocalWorkflowHost(store, FixtureAction(), args.checkpoint_root)
    service = WorkflowService(store, host, JsonObjectRules(), CaseAccessPolicy())
    if args.operation == "decide":
        actor = Principal(
            tenant_id="test-tenant",
            subject="reviewer-1",
            scopes=frozenset({"workflow.read", "workflow.approve"}),
            roles=frozenset({"Workflow.Approver"}),
        )
        await service.decide(actor, args.case_id, "approved")
    else:
        await host.resume(args.case_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("decide", "resume"))
    parser.add_argument("case_id", type=UUID)
    parser.add_argument("checkpoint_root", type=Path)
    parser.add_argument("--barrier", choices=("after-decision", "after-action"))
    parser.add_argument("--marker", type=Path)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
