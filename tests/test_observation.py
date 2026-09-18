"""Tests for Phase 5 screen state models, capture parameters, temporary observation store, and adaptive observation policy."""

import os
from pathlib import Path
import time
import pytest
from pydantic import ValidationError

from windows_agent.observation.capture import ScreenCapture
from windows_agent.observation.models import (
    CaptureRegion,
    CaptureScreenParams,
    ScreenState,
)
from windows_agent.observation.policy import (
    AdaptiveObservationPolicy,
    ObservationTrigger,
)
from windows_agent.observation.store import ObservationStore


def test_screen_state_validation():
    """Verify ScreenState schema, unique capture_id generation, and metadata fields."""
    state = ScreenState(
        width=1920,
        height=1080,
        monitor_index=1,
        active_window={"title": "Notepad", "handle": 12345},
        file_path="/tmp/jarvis_obs/test.png",
        metadata={"custom": "info"},
    )

    assert state.width == 1920
    assert state.height == 1080
    assert state.monitor_index == 1
    assert state.active_window["title"] == "Notepad"
    assert state.file_path == "/tmp/jarvis_obs/test.png"
    assert state.metadata["custom"] == "info"
    assert len(state.capture_id) > 10
    assert state.timestamp is not None

    dumped = state.model_dump()
    assert "raw_bytes" not in dumped
    assert dumped["width"] == 1920
    assert dumped["capture_id"] == state.capture_id


def test_capture_screen_params_validation():
    """Verify CaptureScreenParams validation rules."""
    # Valid default params
    params = CaptureScreenParams()
    assert params.monitor_index is None
    assert params.region is None

    # Valid custom params with region
    region = CaptureRegion(top=100, left=150, width=800, height=600)
    params_with_region = CaptureScreenParams(monitor_index=1, region=region)
    assert params_with_region.monitor_index == 1
    assert params_with_region.region.width == 800

    # Invalid: extra fields forbidden
    with pytest.raises(ValidationError):
        CaptureScreenParams(unexpected_key="invalid")

    # Invalid: non-positive monitor index
    with pytest.raises(ValidationError):
        CaptureScreenParams(monitor_index=0)


def test_capture_region_validation():
    """Verify CaptureRegion bounds validation."""
    # Valid region
    reg = CaptureRegion(top=0, left=0, width=100, height=200)
    assert reg.width == 100

    # Invalid: negative coordinates
    with pytest.raises(ValidationError):
        CaptureRegion(top=-10, left=0, width=100, height=200)

    with pytest.raises(ValidationError):
        CaptureRegion(top=0, left=-5, width=100, height=200)

    # Invalid: non-positive dimensions
    with pytest.raises(ValidationError):
        CaptureRegion(top=0, left=0, width=0, height=200)

    with pytest.raises(ValidationError):
        CaptureRegion(top=0, left=0, width=100, height=0)


def test_observation_store_lifecycle(tmp_path):
    """Verify observation storage, metadata retrieval, image bytes retrieval, and clear."""
    store = ObservationStore(base_dir=str(tmp_path), max_age_seconds=10.0, max_items=5)

    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    cid = "obs-test-123"

    # Store observation
    path_str = store.store(capture_id=cid, image_bytes=dummy_png, metadata={"source": "test"})
    assert os.path.exists(path_str)
    assert Path(path_str).read_bytes() == dummy_png

    # Retrieve metadata
    meta = store.get(cid)
    assert meta is not None
    assert meta["capture_id"] == cid
    assert meta["size_bytes"] == len(dummy_png)
    assert meta["metadata"]["source"] == "test"

    # Retrieve image bytes
    bytes_out = store.get_image_bytes(cid)
    assert bytes_out == dummy_png

    # Non-existent observation
    assert store.get("non-existent") is None
    assert store.get_image_bytes("non-existent") is None

    # Clear store
    store.clear()
    assert not os.path.exists(path_str)
    assert store.get(cid) is None


def test_observation_store_retention_pruning(tmp_path):
    """Verify age-based expiration and count-based pruning in ObservationStore."""
    # Store with max_age = 0.2 seconds, max_items = 3
    store = ObservationStore(base_dir=str(tmp_path), max_age_seconds=0.2, max_items=3)

    dummy_bytes = b"fake-png-payload"

    # Add 3 items
    for i in range(3):
        store.store(f"cid-{i}", dummy_bytes, metadata={"index": i})

    assert len(store._index) == 3

    # Add 4th item -> should prune count excess (oldest first)
    store.store("cid-3", dummy_bytes, metadata={"index": 3})
    assert len(store._index) <= 3
    # cid-0 was oldest, should have been pruned
    assert store.get("cid-0") is None
    assert store.get("cid-3") is not None

    # Wait for age expiration
    time.sleep(0.3)
    pruned = store.prune()
    assert pruned >= 3
    assert len(store._index) == 0


def test_adaptive_observation_policy():
    """Verify policy decisions across all lifecycle triggers."""
    policy = AdaptiveObservationPolicy(capture_on_error=True)

    # IDLE: strictly no continuous capture
    assert policy.should_observe(ObservationTrigger.IDLE) is False
    assert policy.should_observe(ObservationTrigger.IDLE, require_pre_observe=True) is False

    # BEFORE_ACTION: only when pre-observe requested
    assert policy.should_observe(ObservationTrigger.BEFORE_ACTION, require_pre_observe=False) is False
    assert policy.should_observe(ObservationTrigger.BEFORE_ACTION, require_pre_observe=True) is True

    # AFTER_ACTION: only when verification required
    assert policy.should_observe(ObservationTrigger.AFTER_ACTION, require_verification=False) is False
    assert policy.should_observe(ObservationTrigger.AFTER_ACTION, require_verification=True) is True

    # VERIFYING: always capture current state
    assert policy.should_observe(ObservationTrigger.VERIFYING) is True

    # ERROR: capture when capture_on_error is enabled
    assert policy.should_observe(ObservationTrigger.ERROR) is True
    no_error_policy = AdaptiveObservationPolicy(capture_on_error=False)
    assert no_error_policy.should_observe(ObservationTrigger.ERROR) is False

    # RECOVERING: capture before retry
    assert policy.should_observe(ObservationTrigger.RECOVERING) is True


@pytest.mark.asyncio
async def test_screen_capture_execution(tmp_path):
    """Verify ScreenCapture executes request-driven captures and writes to ObservationStore."""
    store = ObservationStore(base_dir=str(tmp_path), max_age_seconds=60.0)
    capture_service = ScreenCapture(store=store)

    state = await capture_service.capture()
    assert isinstance(state, ScreenState)
    assert state.capture_id is not None
    assert state.width > 0
    assert state.height > 0
    assert state.file_path is not None
    assert os.path.exists(state.file_path)

    # Partial region capture
    region_params = CaptureScreenParams(region=CaptureRegion(top=10, left=10, width=100, height=100))
    region_state = await capture_service.capture(region_params)
    assert region_state.width <= 100
    assert region_state.height <= 100
    assert os.path.exists(region_state.file_path)
