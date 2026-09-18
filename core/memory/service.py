"""High-level memory service providing deterministic search, scoring, deduplication, and lifecycle management."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from core.memory.store import MemoryStore
from core.models.memory import (
    MemoryCreateRequest,
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
    MemoryUpdateRequest,
)

logger = logging.getLogger(__name__)


class MemoryService:
    """Service governing structured memory persistence, deduplication, and deterministic retrieval."""

    def __init__(self, store: MemoryStore):
        self.store = store

    async def store_memory(
        self,
        content: str,
        memory_type: Union[MemoryType, str] = MemoryType.FACT,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "user",
        task_id: Optional[str] = None,
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        expires_at: Optional[str] = None,
        allow_duplicate: bool = False,
    ) -> Tuple[MemoryEntry, bool]:
        """Store a memory entry with automated normalization and deduplication.

        Returns:
            Tuple of (MemoryEntry, is_new: bool). If duplicate was detected and updated, is_new is False.
        """
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)

        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Memory content cannot be empty.")

        metadata = metadata or {}
        tags = [t.strip() for t in (tags or []) if t.strip()]
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Deduplication check
        if not allow_duplicate:
            normalized = clean_content.lower()
            existing = await self.store.find_duplicate(normalized, memory_type)
            if existing:
                logger.debug(f"Deduplicating memory against existing entry {existing.id}")
                # Refresh timestamp, boost importance, and merge tags/metadata
                existing.updated_at = now_iso
                existing.importance = max(existing.importance, importance)
                existing.tags = sorted(list(set(existing.tags + tags)))
                existing.metadata.update(metadata)
                if expires_at is not None:
                    existing.expires_at = expires_at

                updated_entry = await self.store.store(existing)
                return updated_entry, False

        # 2. Fresh entry creation
        new_entry = MemoryEntry(
            memory_type=memory_type,
            content=clean_content,
            metadata=metadata,
            source=source,
            task_id=task_id,
            created_at=now_iso,
            updated_at=now_iso,
            importance=importance,
            tags=tags,
            expires_at=expires_at,
        )
        stored_entry = await self.store.store(new_entry)
        return stored_entry, True

    async def search_memory(
        self,
        query: Optional[str] = None,
        memory_type: Optional[Union[MemoryType, str]] = None,
        tags: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        min_importance: float = 0.0,
        limit: int = 10,
        include_expired: bool = False,
    ) -> List[MemorySearchResult]:
        """Search and deterministically rank memories based on relevance, keywords, tags, recency, and importance."""
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)

        # Retrieve candidate entries
        type_str = memory_type.value if memory_type else None
        candidates = await self.store.list(
            limit=500,
            offset=0,
            memory_type=type_str,
            task_id=task_id,
            include_expired=include_expired,
        )

        scored_results: List[MemorySearchResult] = []
        now_dt = datetime.now(timezone.utc)
        query_tokens = [t.lower() for t in query.split()] if query and query.strip() else []
        query_clean = query.strip().lower() if query and query.strip() else ""
        target_tags = set(t.strip().lower() for t in (tags or []) if t.strip())

        for entry in candidates:
            if entry.importance < min_importance:
                continue

            score = 0.0
            reasons = []
            content_lower = entry.content.lower()

            # 1. Keyword scoring (weight: up to 0.40)
            if query_tokens:
                matched_tokens = [tok for tok in query_tokens if tok in content_lower]
                if matched_tokens:
                    token_ratio = len(matched_tokens) / len(query_tokens)
                    exact_sub = 0.10 if query_clean in content_lower else 0.0
                    kw_score = min(0.40, (token_ratio * 0.30) + exact_sub)
                    score += kw_score
                    reasons.append(f"keyword_match({len(matched_tokens)}/{len(query_tokens)})")
            elif not query:
                # Neutral baseline when no query string provided
                score += 0.20
                reasons.append("unfiltered_query")

            # 2. Tag scoring (weight: up to 0.25)
            if target_tags:
                entry_tag_set = set(t.lower() for t in entry.tags)
                tag_matches = target_tags & entry_tag_set
                if tag_matches:
                    tag_score = min(0.25, (len(tag_matches) / len(target_tags)) * 0.25)
                    score += tag_score
                    reasons.append(f"tag_match({len(tag_matches)})")
            elif entry.tags:
                score += 0.05
                reasons.append("tagged_entry")

            # If a query was specified, discard candidate if neither keywords nor tags matched
            if (query_tokens or target_tags) and not any("match" in r for r in reasons):
                continue

            # 3. Category match bonus (weight: up to 0.15)
            if memory_type and entry.memory_type == memory_type:
                score += 0.15
                reasons.append(f"category({entry.memory_type.value})")
            else:
                score += 0.05

            # 4. Importance contribution (weight: up to 0.10)
            imp_contrib = entry.importance * 0.10
            score += imp_contrib
            reasons.append(f"importance({round(entry.importance, 2)})")

            # 5. Recency decay contribution (weight: up to 0.10)
            try:
                updated_dt = datetime.fromisoformat(entry.updated_at)
                elapsed_hours = max(0.0, (now_dt - updated_dt).total_seconds() / 3600.0)
                recency_contrib = 0.10 / (1.0 + (elapsed_hours / 24.0))
                score += recency_contrib
                reasons.append("recency")
            except Exception:
                score += 0.05

            total_relevance = round(score, 4)
            scored_results.append(
                MemorySearchResult(
                    entry=entry,
                    relevance_score=total_relevance,
                    match_reasons=reasons,
                )
            )

        # Deterministic sort: score DESC, updated_at DESC, id ASC
        scored_results.sort(
            key=lambda item: (-item.relevance_score, item.entry.updated_at, item.entry.id),
            reverse=False,
        )

        return scored_results[:limit]

    async def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """Fetch memory entry by ID."""
        return await self.store.get(memory_id)

    async def update_memory(
        self,
        memory_id: str,
        update_req: MemoryUpdateRequest,
    ) -> Optional[MemoryEntry]:
        """Update fields of an existing memory entry."""
        entry = await self.store.get(memory_id)
        if not entry:
            return None

        if update_req.content is not None:
            clean = update_req.content.strip()
            if not clean:
                raise ValueError("Updated content cannot be empty.")
            entry.content = clean

        if update_req.metadata is not None:
            entry.metadata.update(update_req.metadata)

        if update_req.importance is not None:
            entry.importance = update_req.importance

        if update_req.tags is not None:
            entry.tags = sorted(list(set(t.strip() for t in update_req.tags if t.strip())))

        if update_req.expires_at is not None:
            entry.expires_at = update_req.expires_at

        entry.updated_at = datetime.now(timezone.utc).isoformat()
        return await self.store.store(entry)

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a single memory entry."""
        return await self.store.delete(memory_id)

    async def clear_task_memory(self, task_id: str) -> int:
        """Delete all memories associated with a given task ID."""
        return await self.store.clear_by_task(task_id)

    async def prune_expired(self) -> int:
        """Prune expired memories."""
        return await self.store.prune_expired()
