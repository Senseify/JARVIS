"""Tests for ToolRegistry, DemoTool, and DeviceRegistry."""

import pytest
from core.constants import DeviceStatus, DeviceType
from core.models.devices import Device
from core.models.tasks import Task
from core.persistence.database import Database
from core.runtime.context import ExecutionContext
from core.tools.demo import DemoVerificationTool
from core.tools.registry import ToolRegistry
from core.devices.registry import DeviceRegistry


@pytest.mark.asyncio
async def test_tool_registry_operations():
    """Verify tool registration, retrieval, execution, and unregistration."""
    registry = ToolRegistry()
    demo_tool = DemoVerificationTool()

    assert not registry.has_tool("demo_verification_tool")
    registry.register_tool(demo_tool)
    assert registry.has_tool("demo_verification_tool")

    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "demo_verification_tool"

    # Execute tool
    task = Task(input="Test tool")
    context = ExecutionContext(task=task)
    result = await registry.execute_tool(
        "demo_verification_tool",
        context,
        check_name="test_check",
        expected_value="passed",
    )
    assert result["status"] == "passed"
    assert result["matched_expected"] is True
    assert len(context.action_results) == 1

    # Unregister
    removed = registry.unregister_tool("demo_verification_tool")
    assert removed is True
    assert not registry.has_tool("demo_verification_tool")


@pytest.mark.asyncio
async def test_device_registry_operations(tmp_path):
    """Verify device registration, retrieval, removal, and availability."""
    db = Database(db_path=str(tmp_path / "dev_reg.db"))
    await db.connect()
    registry = DeviceRegistry(database=db)

    device = Device(
        name="Test Windows Host",
        device_type=DeviceType.WINDOWS_HOST,
        status=DeviceStatus.ONLINE,
        capabilities=["screen_capture"],
    )
    await registry.register(device)

    retrieved = await registry.get(device.id)
    assert retrieved is not None
    assert retrieved.name == "Test Windows Host"

    # Availability
    assert await registry.is_available(device.id) is True

    # Mark busy/offline
    device.status = DeviceStatus.BUSY
    await registry.register(device)
    assert await registry.is_available(device.id) is False

    # Remove
    removed = await registry.remove(device.id)
    assert removed is True
    assert await registry.get(device.id) is None

    await db.close()
