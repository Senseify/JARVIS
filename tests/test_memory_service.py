"""Tests for MemoryStore SQLite persistence and MemoryService operations, deduplication, and deterministic scoring."""

import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from core.memory.service import MemoryService
from core.memory.store import MemoryStore
from core.models.memory import MemoryEntry, MemoryType, MemoryUpdateRequest
from core.persistence.database import Database


@pytest.fixture
async def memory_components(tmp_path):
    db_file = str(tmp_path / "memory_test.db")
    db = Database(db_path=db_file)
    await db.connect()
    store = MemoryStore(database=db)
    service = MemoryService(store=store)

    yield db, store, service, db_file

    await db.close()


@pytest.mark.asyncio
async def test_memory_store_crud_and_restart_persistence(memory_components):
    """Verify MemoryStore CRUD operations and persistence across database reconnects."""
    db, store, _, db_file = memory_components

    entry = MemoryEntry(
        content="VS Code default theme is Dark Modern.",
        memory_type=MemoryType.PREFERENCE,
        source="user",
        task_id="task-101",
        importance=0.85,
        tags=["ide", "theme"],
    )

    # 1. Store
    stored = await store.store(entry)
    assert stored.id == entry.id

    # 2. Get by ID
    fetched = await store.get(entry.id)
    assert fetched is not None
    assert fetched.content == "VS Code default theme is Dark Modern."
    assert fetched.importance == 0.85
    assert fetched.tags == ["ide", "theme"]
    assert fetched.task_id == "task-101"

    # 3. Count
    assert await store.count() == 1
    assert await store.count(memory_type="preference") == 1
    assert await store.count(memory_type="fact") == 0

    # 4. Restart persistence test
    await db.close()

    # Reconnect with new Database and MemoryStore instance pointing to same file
    new_db = Database(db_path=db_file)
    await new_db.connect()
    new_store = MemoryStore(database=new_db)

    re_fetched = await new_store.get(entry.id)
    assert re_fetched is not None
    assert re_fetched.content == "VS Code default theme is Dark Modern."
    assert await new_store.count() == 1

    # 5. Delete
    deleted = await new_store.delete(entry.id)
    assert deleted is True
    assert await new_store.get(entry.id) is None
    assert await new_store.count() == 0

    await new_db.close()


@pytest.mark.asyncio
async def test_memory_deduplication(memory_components):
    """Verify deduplication updates existing entries rather than creating duplicate rows."""
    _, _, service, _ = memory_components

    # Store first entry
    entry1, is_new1 = await service.store_memory(
        content="Default monitor resolution is 1920x1080",
        memory_type=MemoryType.FACT,
        importance=0.5,
        tags=["display", "resolution"],
    )
    assert is_new1 is True

    # Store duplicate entry (case and whitespace normalized)
    entry2, is_new2 = await service.store_memory(
        content="  default monitor resolution is 1920x1080  ",
        memory_type=MemoryType.FACT,
        importance=0.8,  # higher importance
        tags=["display", "hardware"],  # new tag
    )
    assert is_new2 is False
    assert entry2.id == entry1.id
    # Importance bumped to max(0.5, 0.8)
    assert entry2.importance == 0.8
    # Tags merged
    assert sorted(entry2.tags) == ["display", "hardware", "resolution"]

    # Explicit bypass of deduplication
    entry3, is_new3 = await service.store_memory(
        content="Default monitor resolution is 1920x1080",
        memory_type=MemoryType.FACT,
        allow_duplicate=True,
    )
    assert is_new3 is True
    assert entry3.id != entry1.id


@pytest.mark.asyncio
async def test_memory_deterministic_search_ranking(memory_components):
    """Verify deterministic ranking based on keywords, tags, category, and importance."""
    _, _, service, _ = memory_components

    # Populate memories with distinct attributes
    await service.store_memory(
        content="Python 3.12 is the primary programming language for JARVIS OS.",
        memory_type=MemoryType.FACT,
        importance=0.9,
        tags=["python", "core", "runtime"],
    )
    await service.store_memory(
        content="User prefers Python script automation over shell commands.",
        memory_type=MemoryType.PREFERENCE,
        importance=0.6,
        tags=["python", "scripting"],
    )
    await service.store_memory(
        content="Windows Agent uses ctypes to invoke User32 APIs.",
        memory_type=MemoryType.FACT,
        importance=0.7,
        tags=["windows", "win32"],
    )

    # 1. Search for 'Python' -> both Python entries should rank above Windows
    results_py = await service.search_memory(query="Python", limit=10)
    assert len(results_py) == 2
    contents = [r.entry.content for r in results_py]
    assert all("Python" in c for c in contents)

    # Primary entry with importance 0.9 and more tag matches should rank highest
    top_result = results_py[0]
    assert "primary programming language" in top_result.entry.content
    assert top_result.relevance_score > results_py[1].relevance_score

    # 2. Filter by memory_type = PREFERENCE
    results_pref = await service.search_memory(
        query="Python",
        memory_type=MemoryType.PREFERENCE,
    )
    assert len(results_pref) == 1
    assert results_pref[0].entry.memory_type == MemoryType.PREFERENCE

    # 3. Filter by tag
    results_tag = await service.search_memory(tags=["win32"])
    assert len(results_tag) == 1
    assert "User32" in results_tag[0].entry.content

    # 4. Empty query returns all entries ranked deterministically
    all_results = await service.search_memory(limit=10)
    assert len(all_results) == 3

    # 5. Query with no matches
    empty_results = await service.search_memory(query="Kubernetes Cluster")
    assert len(empty_results) == 0


@pytest.mark.asyncio
async def test_memory_update_and_delete_operations(memory_components):
    """Verify memory update fields and delete behavior."""
    _, _, service, _ = memory_components

    entry, _ = await service.store_memory(
        content="Temporary cache timeout is 60 seconds",
        importance=0.4,
        tags=["cache"],
    )

    # Update fields
    updated = await service.update_memory(
        entry.id,
        MemoryUpdateRequest(
            content="Temporary cache timeout is 120 seconds",
            importance=0.75,
            tags=["cache", "timeout"],
        ),
    )
    assert updated is not None
    assert updated.content == "Temporary cache timeout is 120 seconds"
    assert updated.importance == 0.75
    assert updated.tags == ["cache", "timeout"]

    # Non-existent ID update returns None
    assert await service.update_memory("non-existent-id", MemoryUpdateRequest(content="Test")) is None

    # Delete
    assert await service.delete_memory(entry.id) is True
    assert await service.get_memory(entry.id) is None
    assert await service.delete_memory(entry.id) is False


@pytest.mark.asyncio
async def test_memory_clear_by_task_and_retention(memory_components):
    """Verify task memory clearing and expiration pruning."""
    _, _, service, _ = memory_components

    # Add task-specific memories
    await service.store_memory(content="Task 1 step 1", task_id="task-999")
    await service.store_memory(content="Task 1 step 2", task_id="task-999")
    await service.store_memory(content="Task 2 step 1", task_id="task-888")

    # Clear task-999
    cleared = await service.clear_task_memory("task-999")
    assert cleared == 2

    # Check remaining
    assert len(await service.search_memory(task_id="task-999")) == 0
    assert len(await service.search_memory(task_id="task-888")) == 1

    # Expiry pruning test: create memory with past expires_at
    past_iso = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    expired_entry, _ = await service.store_memory(
        content="Ephemeral memory",
        expires_at=past_iso,
    )

    # By default, expired memories are excluded from search
    active_search = await service.search_memory(query="Ephemeral")
    assert len(active_search) == 0

    # Prune expired
    pruned = await service.prune_expired()
    assert pruned >= 1
    assert await service.get_memory(expired_entry.id) is None
