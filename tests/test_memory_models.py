"""Tests for memory models, validation rules, and request schemas."""

import pytest
from pydantic import ValidationError

from core.models.memory import (
    MemoryCreateRequest,
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
    MemoryUpdateRequest,
)


def test_memory_types_enum():
    """Verify all required memory categories exist in MemoryType enum."""
    expected = {"fact", "preference", "instruction", "task_context", "observation", "outcome", "system"}
    actual = {t.value for t in MemoryType}
    assert expected == actual


def test_memory_entry_validation():
    """Verify MemoryEntry strict validation and defaults."""
    entry = MemoryEntry(
        content="User preferred browser is Edge.",
        memory_type=MemoryType.PREFERENCE,
        source="user",
        importance=0.8,
        tags=["browser", "settings"],
    )

    assert entry.id is not None
    assert entry.content == "User preferred browser is Edge."
    assert entry.memory_type == MemoryType.PREFERENCE
    assert entry.importance == 0.8
    assert "browser" in entry.tags
    assert entry.created_at is not None
    assert entry.updated_at is not None
    assert entry.expires_at is None

    # Importance range validation
    with pytest.raises(ValidationError):
        MemoryEntry(content="Invalid", importance=-0.1)
    with pytest.raises(ValidationError):
        MemoryEntry(content="Invalid", importance=1.1)

    # Empty content rejected
    with pytest.raises(ValidationError):
        MemoryEntry(content="")

    # Forbidden extra keys
    with pytest.raises(ValidationError):
        MemoryEntry(content="Extra", forbidden_key="value")


def test_memory_create_request_validation():
    """Verify MemoryCreateRequest validation."""
    req = MemoryCreateRequest(
        content="System RAM is 32GB",
        memory_type=MemoryType.FACT,
        importance=0.7,
        tags=["hardware"],
    )
    assert req.content == "System RAM is 32GB"
    assert req.importance == 0.7
    assert req.allow_duplicate is False

    # Extra parameters forbidden
    with pytest.raises(ValidationError):
        MemoryCreateRequest(content="Valid", invalid_param=True)


def test_memory_update_request_validation():
    """Verify MemoryUpdateRequest validation."""
    req = MemoryUpdateRequest(
        content="Updated RAM is 64GB",
        importance=0.9,
        tags=["hardware", "upgraded"],
    )
    assert req.content == "Updated RAM is 64GB"
    assert req.importance == 0.9

    # Importance bounds
    with pytest.raises(ValidationError):
        MemoryUpdateRequest(importance=2.0)


def test_memory_search_result_model():
    """Verify MemorySearchResult composite model."""
    entry = MemoryEntry(content="Search result sample")
    res = MemorySearchResult(
        entry=entry,
        relevance_score=0.8523,
        match_reasons=["keyword_match(2/2)", "tag_match(1)"],
    )
    assert res.relevance_score == 0.8523
    assert len(res.match_reasons) == 2
    assert res.entry.content == "Search result sample"
