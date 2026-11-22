import argparse
import asyncio
import os
from pathlib import Path
from uuid import UUID

from app.domain.models import Principal
from app.domain.policy import CaseAccessPolicy
from app.order_resolution.action import RecordOrderResolutionAction
from app.order_resolution.host import OrderResolutionWorkflowHost
from app.order_resolution.persistence import (
    OrderResolutionStore,
    PostgresSyntheticDestination,
)
from app.order_resolution.rules import OrderResolutionRules
from app.order_resolution.service import OrderResolutionService
from app.order_resolution.workflow import build_order_resolution_workflow


TENANT = "10000000-0000-4000-8000-000000000001"
REVIEWER = "40000000-0000-4000-8000-000000000004"


def reviewer() -> Principal:
    return Principal(
        TENANT,
        REVIEWER,
        frozenset({"workflow.read", "workflow.approve"}),
        frozenset({"Workflow.Approver"}),
    )


def components(dsn: str, checkpoint_root: Path):
    store = OrderResolutionStore(dsn)
    destination = PostgresSyntheticDestination(store)
    action = RecordOrderResolutionAction(store, destination)
    host = OrderResolutionWorkflowHost(
        store,
        action,
        checkpoint_root,
        build_order_resolution_workflow,
    )
    service = OrderResolutionService(
        store,
        host,
        OrderResolutionRules(),
        CaseAccessPolicy(),
    )
    return store, destination, host, service


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("before-decision", "after-decision", "before-effect", "after-effect"),
    )
    parser.add_argument("dsn")
    parser.add_argument("checkpoint_root", type=Path)
    parser.add_argument("case_id", type=UUID)
    parser.add_argument("proposal_version", type=int)
    parser.add_argument("action")
    parser.add_argument("destination_id")
    parser.add_argument("handle")
    args = parser.parse_args()

    _, destination, host, service = components(args.dsn, args.checkpoint_root)
    if args.mode == "before-decision":
        os._exit(81)
    if args.mode == "after-decision":
        service.record_bound_decision(
            reviewer(),
            args.case_id,
            "approved",
            proposal_version=args.proposal_version,
            action=args.action,
            destination_id=args.destination_id,
            handle=args.handle,
            channel="api",
        )
        os._exit(82)

    send = destination.send

    def crash_send(request, *, timeout_seconds):
        if args.mode == "before-effect":
            os._exit(83)
        send(request, timeout_seconds=timeout_seconds)
        os._exit(84)

    destination.send = crash_send
    asyncio.run(host.resume(args.case_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
