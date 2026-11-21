import os
import stat
from pathlib import Path
from typing import Callable
from uuid import UUID

from agent_framework import CheckpointStorage, FileCheckpointStorage, Workflow

from app.domain.errors import ActionError, CheckpointError
from app.domain.models import StateRepository, TransactionalAction
from app.workflows.workflow import WORKFLOW_NAME, create_workflow


WorkflowFactory = Callable[[StateRepository, TransactionalAction, CheckpointStorage | None], Workflow]


class LocalWorkflowHost:
    """Run one native workflow per case with private, single-host checkpoints."""

    def __init__(
        self,
        store: StateRepository,
        action: TransactionalAction,
        checkpoint_root: Path,
        workflow_factory: WorkflowFactory = create_workflow,
    ):
        self.store = store
        self.action = action
        self.root = Path(checkpoint_root).absolute()
        self.workflow_factory = workflow_factory
        self._private_directory(self.root)

    @staticmethod
    def _private_directory(path: Path) -> None:
        if path.is_symlink():
            raise CheckpointError("Checkpoint directories must not be symbolic links.")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not path.is_dir():
            raise CheckpointError("The checkpoint path is not a directory.")
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise CheckpointError("The checkpoint directory must be private to the service account.")

    def _storage(self, case_id: UUID) -> FileCheckpointStorage:
        directory = self.root / str(case_id)
        self._private_directory(directory)
        return FileCheckpointStorage(directory)

    async def _checkpoints(self, storage: FileCheckpointStorage):
        checkpoints = []
        for path in storage.storage_path.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise CheckpointError("Unexpected or incomplete checkpoint file.")
            try:
                UUID(path.stem)
                checkpoint = await storage.load(path.stem)
            except Exception as exc:
                raise CheckpointError("A checkpoint is unreadable or corrupt.") from exc
            if checkpoint.workflow_name != WORKFLOW_NAME or checkpoint.checkpoint_id != path.stem:
                raise CheckpointError("A checkpoint belongs to a different workflow.")
            checkpoints.append(checkpoint)
        return checkpoints

    async def _requests(self, stream, case_id: UUID) -> list[str]:
        requests = []
        async for event in stream:
            if event.type == "request_info":
                if event.data != {"case_id": str(case_id)}:
                    raise CheckpointError("The pending request does not match the record.")
                requests.append(event.request_id)
        return requests

    def _workflow(self, storage: FileCheckpointStorage) -> Workflow:
        return self.workflow_factory(self.store, self.action, storage)

    async def start(self, case_id: UUID) -> None:
        with self.store.run_lock(case_id):
            case = self.store.get(case_id)
            if case.status != "created":
                return
            storage = self._storage(case_id)
            checkpoints = await self._checkpoints(storage)
            workflow = self._workflow(storage)
            if checkpoints:
                latest = max(checkpoints, key=lambda item: item.timestamp)
                requests = await self._requests(
                    workflow.run(checkpoint_id=latest.checkpoint_id, stream=True), case_id
                )
            else:
                requests = await self._requests(
                    workflow.run({"case_id": str(case_id)}, stream=True), case_id
                )
            if len(requests) != 1:
                raise CheckpointError("The workflow did not produce exactly one approval request.")
            checkpoints = await self._checkpoints(storage)
            if not checkpoints:
                raise CheckpointError("The pending workflow checkpoint was not saved.")
            pending = max(checkpoints, key=lambda item: item.timestamp)
            restored = await self._requests(
                self._workflow(storage).run(checkpoint_id=pending.checkpoint_id, stream=True), case_id
            )
            if restored != requests:
                raise CheckpointError("The pending request could not be restored.")
            self.store.save_pending(case_id, pending.checkpoint_id, requests[0])

    async def resume(self, case_id: UUID) -> None:
        with self.store.run_lock(case_id):
            case = self.store.get(case_id)
            storage = self._storage(case_id)
            checkpoints = await self._checkpoints(storage)
            by_id = {checkpoint.checkpoint_id: checkpoint for checkpoint in checkpoints}
            if case.execution_complete:
                if not case.terminal_checkpoint_id or case.terminal_checkpoint_id not in by_id:
                    raise CheckpointError("The completed workflow checkpoint is missing.")
                return
            if not case.checkpoint_id or case.checkpoint_id not in by_id or not case.request_id:
                raise CheckpointError("The pending workflow checkpoint is missing.")
            workflow = self._workflow(storage)
            requests = await self._requests(
                workflow.run(checkpoint_id=case.checkpoint_id, stream=True), case_id
            )
            if requests != [case.request_id]:
                raise CheckpointError("The checkpoint does not contain the recorded pending request.")
            if case.decision is None:
                return
            expected = {"case_id": str(case_id), "decision": case.decision}
            outputs = []
            try:
                async for event in workflow.run(
                    responses={case.request_id: case.decision == "approved"}, stream=True
                ):
                    if event.type == "output":
                        outputs.append(event.data)
            except ActionError:
                self.store.mark_action_failed(case_id)
                raise
            if outputs != [expected]:
                raise CheckpointError("The workflow did not produce the expected outcome.")
            checkpoints = await self._checkpoints(storage)
            terminal = max(checkpoints, key=lambda item: item.timestamp)
            if terminal.checkpoint_id == case.checkpoint_id:
                raise CheckpointError("The completed workflow checkpoint was not saved.")
            self.store.finish(case_id, terminal.checkpoint_id)
