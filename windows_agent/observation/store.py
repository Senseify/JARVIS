"""Temporary observation storage with explicit lifecycle management and retention pruning."""

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ObservationStore:
    """Manages short-lived local storage of captured screenshots and metadata."""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        max_age_seconds: float = 300.0,
        max_items: int = 50,
    ):
        self.base_dir = Path(base_dir or os.path.join(tempfile.gettempdir(), "jarvis_observations"))
        self.max_age_seconds = max_age_seconds
        self.max_items = max_items
        self._index: Dict[str, Dict[str, Any]] = {}
        self._init_store()

    def _init_store(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def store(self, capture_id: str, image_bytes: bytes, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Write raw screenshot bytes to temporary file and record metadata."""
        file_name = f"obs_{capture_id}.png"
        target_path = self.base_dir / file_name

        target_path.write_bytes(image_bytes)

        record = {
            "capture_id": capture_id,
            "file_path": str(target_path),
            "size_bytes": len(image_bytes),
            "stored_at": time.time(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._index[capture_id] = record
        self.prune()
        logger.debug(f"Stored observation {capture_id} at {target_path}")
        return str(target_path)

    def get(self, capture_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored metadata for an observation ID."""
        return self._index.get(capture_id)

    def get_image_bytes(self, capture_id: str) -> Optional[bytes]:
        """Read and return image bytes if available."""
        record = self.get(capture_id)
        if not record:
            return None
        path = Path(record["file_path"])
        if path.exists():
            return path.read_bytes()
        return None

    def prune(self) -> int:
        """Prune entries exceeding maximum retention age or maximum item count."""
        now = time.time()
        expired_ids = []

        # 1. Age-based expiration
        for cid, entry in self._index.items():
            if now - entry["stored_at"] > self.max_age_seconds:
                expired_ids.append(cid)

        # 2. Count-based pruning (oldest first)
        remaining = len(self._index) - len(expired_ids)
        if remaining > self.max_items:
            excess = remaining - self.max_items
            sorted_by_age = sorted(
                [entry for cid, entry in self._index.items() if cid not in expired_ids],
                key=lambda x: x["stored_at"],
            )
            for old_entry in sorted_by_age[:excess]:
                expired_ids.append(old_entry["capture_id"])

        # Delete expired files and remove from index
        pruned_count = 0
        for cid in set(expired_ids):
            entry = self._index.pop(cid, None)
            if entry:
                try:
                    p = Path(entry["file_path"])
                    if p.exists():
                        p.unlink()
                    pruned_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete observation file {entry['file_path']}: {e}")

        return pruned_count

    def clear(self) -> None:
        """Clear all stored screenshots and reset index."""
        for cid, entry in list(self._index.items()):
            try:
                p = Path(entry["file_path"])
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        self._index.clear()
