"""Device registry foundation for authorized JARVIS devices."""

import logging
from typing import Dict, List, Optional
from core.models.devices import Device
from core.constants import DeviceStatus
from core.persistence.database import Database

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """Registry managing authorized devices in the JARVIS ecosystem."""

    def __init__(self, database: Optional[Database] = None):
        self.database = database
        self._devices: Dict[str, Device] = {}

    async def register(self, device: Device) -> None:
        """Register or update an authorized device."""
        self._devices[device.id] = device
        if self.database is not None:
            await self.database.save_device(device)
        logger.info(f"Registered device: {device.name} ({device.id})")

    async def remove(self, device_id: str) -> bool:
        """Remove a device by ID."""
        existed = device_id in self._devices
        if existed:
            del self._devices[device_id]
        if self.database is not None:
            db_removed = await self.database.delete_device(device_id)
            return existed or db_removed
        return existed

    async def get(self, device_id: str) -> Optional[Device]:
        """Retrieve a device by ID from memory or database."""
        if device_id in self._devices:
            return self._devices[device_id]
        if self.database is not None:
            device = await self.database.get_device(device_id)
            if device:
                self._devices[device.id] = device
            return device
        return None

    async def list_devices(self) -> List[Device]:
        """List all authorized devices."""
        if self.database is not None:
            devices = await self.database.list_devices()
            for d in devices:
                self._devices[d.id] = d
            return devices
        return list(self._devices.values())

    async def is_available(self, device_id: str) -> bool:
        """Check if a device is registered and online."""
        device = await self.get(device_id)
        if not device:
            return False
        return device.status == DeviceStatus.ONLINE
