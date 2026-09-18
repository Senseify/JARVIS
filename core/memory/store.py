"""Persistent SQLite store for memory entries."""

import asyncio
from datetime import datetime, timezone
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from core.models.memory import MemoryEntry, MemoryType
from core.persistence.database import Database

logger = logging.getLogger(__name__)


class MemoryStore:
    """Manages SQLite persistence for structured memory entries."""

    def __init__(self, database: Database):
        self.database = database

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        metadata_val = row["metadata"]
        tags_val = row["tags"]

        metadata = json.loads(metadata_val) if metadata_val else {}
        tags = json.loads(tags_val) if tags_val else []

        return MemoryEntry(
            id=row["id"],
            memory_type=MemoryType(row["memory_type"]),
            content=row["content"],
            metadata=metadata,
            source=row["source"],
            task_id=row["task_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            importance=float(row["importance"]),
            tags=tags,
            expires_at=row["expires_at"],
        )

    async def store(self, entry: MemoryEntry) -> MemoryEntry:
        """Store or update a memory entry."""
        return await asyncio.to_thread(self._store_sync, entry)

    def _store_sync(self, entry: MemoryEntry) -> MemoryEntry:
        conn = self.database._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, memory_type, content, metadata, source,
                    task_id, created_at, updated_at, importance, tags, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    memory_type = excluded.memory_type,
                    content = excluded.content,
                    metadata = excluded.metadata,
                    source = excluded.source,
                    task_id = excluded.task_id,
                    updated_at = excluded.updated_at,
                    importance = excluded.importance,
                    tags = excluded.tags,
                    expires_at = excluded.expires_at
                """,
                (
                    entry.id,
                    entry.memory_type.value,
                    entry.content,
                    json.dumps(entry.metadata),
                    entry.source,
                    entry.task_id,
                    entry.created_at,
                    entry.updated_at,
                    entry.importance,
                    json.dumps(entry.tags),
                    entry.expires_at,
                ),
            )
        return entry

    async def get(self, memory_id: str) -> Optional[MemoryEntry]:
        """Fetch a single memory entry by ID."""
        return await asyncio.to_thread(self._get_sync, memory_id)

    def _get_sync(self, memory_id: str) -> Optional[MemoryEntry]:
        conn = self.database._get_connection()
        cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_entry(row)
        return None

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        memory_type: Optional[str] = None,
        task_id: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[MemoryEntry]:
        """List memory entries with optional filtering."""
        return await asyncio.to_thread(
            self._list_sync, limit, offset, memory_type, task_id, include_expired
        )

    def _list_sync(
        self,
        limit: int,
        offset: int,
        memory_type: Optional[str],
        task_id: Optional[str],
        include_expired: bool,
    ) -> List[MemoryEntry]:
        conn = self.database._get_connection()
        conditions = []
        params: List[Any] = []

        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        if not include_expired:
            now_iso = datetime.now(timezone.utc).isoformat()
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(now_iso)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM memories {where_clause} ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, tuple(params))
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory entry by ID."""
        return await asyncio.to_thread(self._delete_sync, memory_id)

    def _delete_sync(self, memory_id: str) -> bool:
        conn = self.database._get_connection()
        with conn:
            cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0

    async def clear_by_task(self, task_id: str) -> int:
        """Clear all memory entries associated with a specific task."""
        return await asyncio.to_thread(self._clear_by_task_sync, task_id)

    def _clear_by_task_sync(self, task_id: str) -> int:
        conn = self.database._get_connection()
        with conn:
            cursor = conn.execute("DELETE FROM memories WHERE task_id = ?", (task_id,))
            return cursor.rowcount

    async def clear_all(self) -> int:
        """Clear all stored memories."""
        return await asyncio.to_thread(self._clear_all_sync)

    def _clear_all_sync(self) -> int:
        conn = self.database._get_connection()
        with conn:
            cursor = conn.execute("DELETE FROM memories")
            return cursor.rowcount

    async def count(
        self,
        memory_type: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> int:
        """Count total memories matching criteria."""
        return await asyncio.to_thread(self._count_sync, memory_type, task_id)

    def _count_sync(self, memory_type: Optional[str], task_id: Optional[str]) -> int:
        conn = self.database._get_connection()
        conditions = []
        params: List[Any] = []

        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT COUNT(*) FROM memories {where_clause}"
        cursor = conn.execute(query, tuple(params))
        return cursor.fetchone()[0]

    async def find_duplicate(
        self,
        normalized_content: str,
        memory_type: Optional[MemoryType] = None,
    ) -> Optional[MemoryEntry]:
        """Find an existing memory matching normalized content and category."""
        return await asyncio.to_thread(
            self._find_duplicate_sync, normalized_content, memory_type
        )

    def _find_duplicate_sync(
        self,
        normalized_content: str,
        memory_type: Optional[MemoryType],
    ) -> Optional[MemoryEntry]:
        conn = self.database._get_connection()
        query = "SELECT * FROM memories WHERE LOWER(TRIM(content)) = ?"
        params: List[Any] = [normalized_content]

        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type.value)

        query += " ORDER BY updated_at DESC LIMIT 1"
        cursor = conn.execute(query, tuple(params))
        row = cursor.fetchone()
        if row:
            return self._row_to_entry(row)
        return None

    async def prune_expired(self) -> int:
        """Delete memories whose expiration timestamp has passed."""
        return await asyncio.to_thread(self._prune_expired_sync)

    def _prune_expired_sync(self) -> int:
        conn = self.database._get_connection()
        now_iso = datetime.now(timezone.utc).isoformat()
        with conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now_iso,),
            )
            return cursor.rowcount
