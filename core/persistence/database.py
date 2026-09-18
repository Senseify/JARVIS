"""SQLite persistence layer for JARVIS OS Core."""

import asyncio
from datetime import datetime
import json
import sqlite3
from typing import Optional

from core.models.devices import Device
from core.models.events import AgentEvent
from core.models.tasks import Task


class Database:
    """Async wrapper around SQLite for persisting tasks, events, and devices."""

    def __init__(self, db_path: str = "jarvis.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            # check_same_thread=False allows thread-pool access via asyncio.to_thread
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode for file-based databases to enhance concurrency
            if not self.db_path.startswith(":memory:"):
                self._conn.execute("PRAGMA journal_mode=WAL;")
        return self._conn

    def _init_db_sync(self) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    input TEXT NOT NULL,
                    state TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    metadata TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    task_id TEXT,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    state TEXT,
                    status TEXT,
                    payload TEXT,
                    error TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    capabilities TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    metadata TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_task_id ON events (task_id);")

    async def connect(self) -> None:
        """Initialize database schema asynchronously."""
        async with self._lock:
            await asyncio.to_thread(self._init_db_sync)

    def _close_sync(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    async def close(self) -> None:
        """Close the database connection."""
        async with self._lock:
            await asyncio.to_thread(self._close_sync)

    # -------------------------------------------------------------
    # Task Operations
    # -------------------------------------------------------------
    def _save_task_sync(self, task: Task) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO tasks (id, input, state, status, created_at, updated_at, result, error, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    input = excluded.input,
                    state = excluded.state,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    result = excluded.result,
                    error = excluded.error,
                    metadata = excluded.metadata
                """,
                (
                    task.id,
                    task.input,
                    task.state.value,
                    task.status.value,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    json.dumps(task.result) if task.result is not None else None,
                    task.error,
                    json.dumps(task.metadata),
                ),
            )

    async def save_task(self, task: Task) -> None:
        """Persist or update a task."""
        async with self._lock:
            await asyncio.to_thread(self._save_task_sync, task)

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            input=row["input"],
            state=row["state"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _get_task_sync(self, task_id: str) -> Optional[Task]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return self._row_to_task(row) if row else None

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve a task by ID."""
        async with self._lock:
            return await asyncio.to_thread(self._get_task_sync, task_id)

    def _list_tasks_sync(self, limit: int = 50, offset: int = 0) -> list[Task]:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [self._row_to_task(row) for row in cursor.fetchall()]

    async def list_tasks(self, limit: int = 50, offset: int = 0) -> list[Task]:
        """List tasks ordered by creation date descending."""
        async with self._lock:
            return await asyncio.to_thread(self._list_tasks_sync, limit, offset)

    # -------------------------------------------------------------
    # Event Operations
    # -------------------------------------------------------------
    def _save_event_sync(self, event: AgentEvent) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO events (id, timestamp, task_id, event_type, source, state, status, payload, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.timestamp.isoformat(),
                    event.task_id,
                    event.event_type.value,
                    event.source,
                    event.state.value if event.state else None,
                    event.status.value if event.status else None,
                    json.dumps(event.payload),
                    event.error,
                ),
            )

    async def save_event(self, event: AgentEvent) -> None:
        """Persist a runtime event."""
        async with self._lock:
            await asyncio.to_thread(self._save_event_sync, event)

    def _row_to_event(self, row: sqlite3.Row) -> AgentEvent:
        return AgentEvent(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            task_id=row["task_id"],
            event_type=row["event_type"],
            source=row["source"],
            state=row["state"],
            status=row["status"],
            payload=json.loads(row["payload"]) if row["payload"] else {},
            error=row["error"],
        )

    def _get_events_for_task_sync(self, task_id: str) -> list[AgentEvent]:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM events WHERE task_id = ? ORDER BY timestamp ASC",
            (task_id,),
        )
        return [self._row_to_event(row) for row in cursor.fetchall()]

    async def get_events_for_task(self, task_id: str) -> list[AgentEvent]:
        """Retrieve all events recorded for a specific task."""
        async with self._lock:
            return await asyncio.to_thread(self._get_events_for_task_sync, task_id)

    # -------------------------------------------------------------
    # Device Operations
    # -------------------------------------------------------------
    def _save_device_sync(self, device: Device) -> None:
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO devices (id, name, device_type, status, capabilities, last_seen, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    device_type = excluded.device_type,
                    status = excluded.status,
                    capabilities = excluded.capabilities,
                    last_seen = excluded.last_seen,
                    metadata = excluded.metadata
                """,
                (
                    device.id,
                    device.name,
                    device.device_type.value,
                    device.status.value,
                    json.dumps(device.capabilities),
                    device.last_seen.isoformat(),
                    json.dumps(device.metadata),
                ),
            )

    async def save_device(self, device: Device) -> None:
        """Persist or update a registered device."""
        async with self._lock:
            await asyncio.to_thread(self._save_device_sync, device)

    def _row_to_device(self, row: sqlite3.Row) -> Device:
        return Device(
            id=row["id"],
            name=row["name"],
            device_type=row["device_type"],
            status=row["status"],
            capabilities=json.loads(row["capabilities"]) if row["capabilities"] else [],
            last_seen=datetime.fromisoformat(row["last_seen"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _get_device_sync(self, device_id: str) -> Optional[Device]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        return self._row_to_device(row) if row else None

    async def get_device(self, device_id: str) -> Optional[Device]:
        """Retrieve a device by ID."""
        async with self._lock:
            return await asyncio.to_thread(self._get_device_sync, device_id)

    def _list_devices_sync(self) -> list[Device]:
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM devices ORDER BY name ASC")
        return [self._row_to_device(row) for row in cursor.fetchall()]

    async def list_devices(self) -> list[Device]:
        """List all registered devices."""
        async with self._lock:
            return await asyncio.to_thread(self._list_devices_sync)

    def _delete_device_sync(self, device_id: str) -> bool:
        conn = self._get_connection()
        with conn:
            cursor = conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            return cursor.rowcount > 0

    async def delete_device(self, device_id: str) -> bool:
        """Delete a device by ID."""
        async with self._lock:
            return await asyncio.to_thread(self._delete_device_sync, device_id)
