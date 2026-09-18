"""Task Manager coordinating task lifecycle and state transitions."""

import logging
from typing import Dict, List, Optional, Set
from core.constants import AgentLoopState, EventType, TaskStatus
from core.events.bus import EventBus
from core.models.events import AgentEvent
from core.models.tasks import Task
from core.persistence.database import Database

logger = logging.getLogger(__name__)

# Valid transitions between AgentLoopState during task execution
VALID_STATE_TRANSITIONS: Dict[AgentLoopState, Set[AgentLoopState]] = {
    AgentLoopState.IDLE: {AgentLoopState.OBSERVE},
    AgentLoopState.OBSERVE: {AgentLoopState.UNDERSTAND},
    AgentLoopState.UNDERSTAND: {AgentLoopState.PLAN},
    AgentLoopState.PLAN: {AgentLoopState.ACT},
    AgentLoopState.ACT: {AgentLoopState.VERIFY},
    AgentLoopState.VERIFY: {AgentLoopState.REMEMBER, AgentLoopState.RECOVER},
    AgentLoopState.RECOVER: {AgentLoopState.PLAN, AgentLoopState.ACT, AgentLoopState.REMEMBER},
    AgentLoopState.REMEMBER: {AgentLoopState.IDLE},
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal lifecycle state transition is attempted."""
    pass


class TaskManager:
    """Manages the creation, transition, completion, and retrieval of tasks."""

    def __init__(self, database: Optional[Database] = None, event_bus: Optional[EventBus] = None):
        self.database = database
        self.event_bus = event_bus
        self._tasks: Dict[str, Task] = {}

    async def create_task(self, input_text: str, metadata: Optional[dict] = None) -> Task:
        """Create and persist a new task in IDLE / PENDING state."""
        task = Task(
            input=input_text,
            state=AgentLoopState.IDLE,
            status=TaskStatus.PENDING,
            metadata=metadata or {},
        )
        self._tasks[task.id] = task

        if self.database is not None:
            await self.database.save_task(task)

        if self.event_bus is not None:
            await self.event_bus.publish(
                AgentEvent(
                    task_id=task.id,
                    event_type=EventType.TASK_CREATED,
                    source="core.task_manager",
                    state=task.state,
                    status=task.status,
                    payload={"input": task.input, "metadata": task.metadata},
                )
            )

        logger.info(f"Created task {task.id}: {task.input}")
        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve a task by ID."""
        if task_id in self._tasks:
            return self._tasks[task_id]
        if self.database is not None:
            task = await self.database.get_task(task_id)
            if task:
                self._tasks[task.id] = task
            return task
        return None

    async def list_tasks(self, limit: int = 50, offset: int = 0) -> List[Task]:
        """List tasks ordered by recency."""
        if self.database is not None:
            tasks = await self.database.list_tasks(limit=limit, offset=offset)
            for t in tasks:
                self._tasks[t.id] = t
            return tasks
        all_tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return all_tasks[offset : offset + limit]

    async def update_task_state(self, task_id: str, new_state: AgentLoopState) -> Task:
        """Advance a task to a new AgentLoopState, validating transitions."""
        task = await self.get_task(task_id)
        if not task:
            raise KeyError(f"Task with ID {task_id} not found.")

        current_state = task.state
        allowed_targets = VALID_STATE_TRANSITIONS.get(current_state, set())

        if new_state not in allowed_targets:
            raise InvalidStateTransitionError(
                f"Invalid transition for task {task_id}: cannot transition from '{current_state.value}' to '{new_state.value}'. "
                f"Allowed transitions: {[s.value for s in allowed_targets]}"
            )

        task.state = new_state
        if task.status == TaskStatus.PENDING and new_state != AgentLoopState.IDLE:
            task.status = TaskStatus.RUNNING
        task.update_timestamp()

        if self.database is not None:
            await self.database.save_task(task)

        if self.event_bus is not None:
            await self.event_bus.publish(
                AgentEvent(
                    task_id=task.id,
                    event_type=EventType.TASK_STATE_CHANGED,
                    source="core.task_manager",
                    state=task.state,
                    status=task.status,
                    payload={"previous_state": current_state.value, "new_state": new_state.value},
                )
            )

        return task

    async def complete_task(self, task_id: str, result: dict) -> Task:
        """Mark a task as completed with result payload."""
        task = await self.get_task(task_id)
        if not task:
            raise KeyError(f"Task with ID {task_id} not found.")

        task.status = TaskStatus.COMPLETED
        task.state = AgentLoopState.IDLE
        task.result = result
        task.update_timestamp()

        if self.database is not None:
            await self.database.save_task(task)

        if self.event_bus is not None:
            await self.event_bus.publish(
                AgentEvent(
                    task_id=task.id,
                    event_type=EventType.TASK_COMPLETED,
                    source="core.task_manager",
                    state=task.state,
                    status=task.status,
                    payload={"result": result},
                )
            )

        logger.info(f"Completed task {task.id}")
        return task

    async def fail_task(self, task_id: str, error_message: str) -> Task:
        """Mark a task as failed with an error message."""
        task = await self.get_task(task_id)
        if not task:
            raise KeyError(f"Task with ID {task_id} not found.")

        task.status = TaskStatus.FAILED
        task.error = error_message
        task.update_timestamp()

        if self.database is not None:
            await self.database.save_task(task)

        if self.event_bus is not None:
            await self.event_bus.publish(
                AgentEvent(
                    task_id=task.id,
                    event_type=EventType.TASK_FAILED,
                    source="core.task_manager",
                    state=task.state,
                    status=task.status,
                    error=error_message,
                    payload={"error": error_message},
                )
            )

        logger.error(f"Task {task.id} failed: {error_message}")
        return task
