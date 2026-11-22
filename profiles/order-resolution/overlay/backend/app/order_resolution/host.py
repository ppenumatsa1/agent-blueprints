from uuid import UUID

from agent_framework import FileCheckpointStorage

from app.domain.errors import ActionError, CheckpointError
from app.domain.models import Principal
from app.infrastructure.telemetry import instrumented
from app.order_resolution.persistence import OrderResolutionStore
from app.order_resolution.workflow import OrderResolutionDecision
from app.workflows.host import LocalWorkflowHost
from app.workflows.workflow import WORKFLOW_NAME


class OrderResolutionWorkflowHost(LocalWorkflowHost):
    """Allow either automatic completion or the base host's native approval pause."""

    def _storage(self, case_id: UUID) -> FileCheckpointStorage:
        directory = self.root / str(case_id)
        self._private_directory(directory)
        return FileCheckpointStorage(
            directory,
            allowed_checkpoint_types=[
                "app.order_resolution.workflow:OrderResolutionDecision"
            ],
        )

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
    async def start(self, case_id: UUID, actor: Principal | None = None) -> None:
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
    async def resume(
        self,
        case_id: UUID,
        actor: Principal | None = None,
        decision_command: object | None = None,
    ) -> None:
        with self.store.run_lock(case_id):
            case = self.store.get(case_id)
            storage = self._storage(case_id)
            checkpoints = await self._checkpoints(storage)
            by_id = {checkpoint.checkpoint_id: checkpoint for checkpoint in checkpoints}
            if case.execution_complete:
                if not case.terminal_checkpoint_id or case.terminal_checkpoint_id not in by_id:
                    raise CheckpointError("The completed workflow checkpoint is missing.")
                if not self._is_terminal(by_id[case.terminal_checkpoint_id], case.checkpoint_id):
                    raise CheckpointError("The completed workflow checkpoint is incomplete.")
                return
            if not case.checkpoint_id or case.checkpoint_id not in by_id or not case.request_id:
                raise CheckpointError("The pending workflow checkpoint is missing.")
            workflow = self._workflow(storage)
            requests = await self._requests(
                workflow.run(checkpoint_id=case.checkpoint_id, stream=True), case_id
            )
            if requests != [case.request_id]:
                raise CheckpointError(
                    "The checkpoint does not contain the recorded pending request."
                )
            proposal = self.store.bind_decision_handle(case_id, case.request_id)
            if case.decision is None:
                return
            response = OrderResolutionDecision(
                case_id=case_id,
                proposal_version=proposal.proposal_version,
                action=proposal.action,
                destination_id=proposal.destination_id,
                handle=case.request_id,
                channel=proposal.decision_channel or "api",
                decision=case.decision,
            )
            expected = {"case_id": str(case_id), "decision": case.decision}
            outputs = []
            try:
                async for event in workflow.run(
                    responses={case.request_id: response}, stream=True
                ):
                    if event.type == "output":
                        outputs.append(event.data)
            except ActionError:
                self.store.mark_action_failed(case_id)
                raise
            if outputs != [expected]:
                raise CheckpointError("The workflow did not produce the expected outcome.")
            checkpoints = await self._checkpoints(storage)
            terminal_id = workflow.get_last_checkpoint_id()
            terminal = next(
                (item for item in checkpoints if item.checkpoint_id == terminal_id), None
            )
            if terminal is None or not self._is_terminal(terminal, case.checkpoint_id):
                raise CheckpointError("The completed workflow checkpoint was not saved.")
            self.store.finish(case_id, terminal.checkpoint_id)
