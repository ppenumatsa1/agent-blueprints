from uuid import UUID

from app.domain.errors import CheckpointError
from app.infrastructure.telemetry import instrumented
from app.order_resolution.persistence import OrderResolutionStore
from app.workflows.host import LocalWorkflowHost
from app.workflows.workflow import WORKFLOW_NAME


class OrderResolutionWorkflowHost(LocalWorkflowHost):
    """Allow either automatic completion or the base host's native approval pause."""

    async def _events(self, stream, case_id: UUID) -> tuple[list[str], list[object]]:
        requests: list[str] = []
        outputs: list[object] = []
        async for event in stream:
            if event.type == "request_info":
                if event.data != {"case_id": str(case_id)}:
                    raise CheckpointError("The pending request does not match the record.")
                requests.append(event.request_id)
            elif event.type == "output":
                outputs.append(event.data)
        return requests, outputs

    @instrumented("workflow.start")
    async def start(self, case_id: UUID) -> None:
        with self.store.run_lock(case_id):
            case = self.store.get(case_id)
            if case.status != "created":
                return
            storage = self._storage(case_id)
            checkpoints = await self._checkpoints(storage)
            workflow = self._workflow(storage)
            if checkpoints:
                latest = await storage.get_latest(workflow_name=WORKFLOW_NAME)
                if latest is None or latest.checkpoint_id not in {
                    item.checkpoint_id for item in checkpoints
                }:
                    raise CheckpointError("The latest checkpoint could not be selected.")
                stream = workflow.run(checkpoint_id=latest.checkpoint_id, stream=True)
            else:
                stream = workflow.run({"case_id": str(case_id)}, stream=True)
            requests, outputs = await self._events(stream, case_id)

            if requests:
                if len(requests) != 1 or outputs:
                    raise CheckpointError("The workflow produced an invalid approval pause.")
                checkpoints = await self._checkpoints(storage)
                pending_id = workflow.get_last_checkpoint_id()
                pending = next(
                    (item for item in checkpoints if item.checkpoint_id == pending_id),
                    None,
                )
                if pending is None or set(pending.pending_request_info_events) != set(requests):
                    raise CheckpointError("The pending workflow checkpoint was not saved.")
                restored = await self._requests(
                    self._workflow(storage).run(checkpoint_id=pending.checkpoint_id, stream=True),
                    case_id,
                )
                if restored != requests:
                    raise CheckpointError("The pending request could not be restored.")
                self.store.save_pending(case_id, pending.checkpoint_id, requests[0])
                self.store.bind_decision_handle(case_id, requests[0])
                return

            expected = [{"case_id": str(case_id), "decision": "automatic"}]
            if outputs != expected:
                raise CheckpointError("The workflow produced an invalid automatic outcome.")
            checkpoints = await self._checkpoints(storage)
            terminal_id = workflow.get_last_checkpoint_id()
            terminal = next(
                (item for item in checkpoints if item.checkpoint_id == terminal_id),
                None,
            )
            if terminal is None or not self._is_terminal(terminal, None):
                raise CheckpointError("The automatic workflow checkpoint was not saved.")
            if not isinstance(self.store, OrderResolutionStore):
                raise CheckpointError("The Order Resolution persistence adapter is required.")
            self.store.finish_automatic(case_id, terminal.checkpoint_id)

    @instrumented("workflow.resume")
    async def resume(self, case_id: UUID) -> None:
        case = self.store.get(case_id)
        if (
            not case.execution_complete
            and case.request_id
            and case.payload.get("proposal", {}).get("approval_required") is True
        ):
            self.store.bind_decision_handle(case_id, case.request_id)
        await super().resume(case_id)
