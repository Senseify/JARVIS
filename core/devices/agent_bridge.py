"""Windows Agent Bridge managing WebSocket connections, heartbeats, and command dispatch."""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import WebSocket, WebSocketDisconnect

from core import __version__
from core.constants import DeviceStatus, DeviceType
from core.devices.registry import DeviceRegistry
from core.models.devices import Device
from core.models.protocol import (
    AgentMessage,
    AgentRegistrationPayload,
    CommandRequestPayload,
    CommandResultPayload,
    HeartbeatAckPayload,
    HeartbeatPayload,
    MessageType,
    RegisterAckPayload,
)

logger = logging.getLogger(__name__)


class ConnectedAgentSession:
    """Represents an active WebSocket session with a remote machine agent."""

    def __init__(self, device_id: str, websocket: WebSocket, registration: AgentRegistrationPayload):
        self.device_id = device_id
        self.websocket = websocket
        self.registration = registration
        self.connected_at = datetime.now(timezone.utc)
        self.last_heartbeat = datetime.now(timezone.utc)
        self.pending_commands: Dict[str, asyncio.Future[CommandResultPayload]] = {}

    def update_heartbeat(self) -> None:
        self.last_heartbeat = datetime.now(timezone.utc)


class AgentBridge:
    """Coordinates connected machine agents, heartbeat monitoring, and command routing."""

    def __init__(self, device_registry: DeviceRegistry):
        self.device_registry = device_registry
        self._sessions: Dict[str, ConnectedAgentSession] = {}
        self._lock = asyncio.Lock()

    def is_connected(self, device_id: str) -> bool:
        """Check if an agent is currently connected."""
        return device_id in self._sessions

    def get_session(self, device_id: str) -> Optional[ConnectedAgentSession]:
        """Get the active session for a device ID."""
        return self._sessions.get(device_id)

    def list_connected_devices(self) -> List[str]:
        """List device IDs of currently connected agents."""
        return list(self._sessions.keys())

    async def handle_agent_connection(self, websocket: WebSocket) -> None:
        """Process incoming WebSocket lifecycle for a machine agent."""
        await websocket.accept()
        current_device_id: Optional[str] = None

        try:
            # 1. Initial Handshake: Expect REGISTER message
            initial_text = await websocket.receive_text()
            try:
                initial_data = json.loads(initial_text)
                msg = AgentMessage.model_validate(initial_data)
            except Exception as e:
                err_msg = AgentMessage(
                    correlation_id="initial",
                    message_type=MessageType.ERROR,
                    error=f"Malformed registration message: {e}",
                )
                await websocket.send_text(err_msg.model_dump_json())
                await websocket.close(code=1008)
                return

            if msg.message_type != MessageType.REGISTER:
                err_msg = AgentMessage(
                    correlation_id=msg.correlation_id,
                    message_type=MessageType.ERROR,
                    error="Expected 'register' as initial message.",
                )
                await websocket.send_text(err_msg.model_dump_json())
                await websocket.close(code=1008)
                return

            reg = AgentRegistrationPayload.model_validate(msg.payload)
            current_device_id = reg.device_id

            # Determine device type (default to WINDOWS_HOST if platform is windows)
            dev_type = DeviceType.WINDOWS_HOST if "win" in reg.platform.lower() else DeviceType.GENERIC_HOST

            device = Device(
                id=reg.device_id,
                name=reg.hostname,
                device_type=dev_type,
                status=DeviceStatus.ONLINE,
                capabilities=reg.capabilities,
                last_seen=datetime.now(timezone.utc),
                metadata={
                    "platform": reg.platform,
                    "agent_version": reg.agent_version,
                    **reg.metadata,
                },
            )

            async with self._lock:
                # Handle existing/duplicate session for same device cleanly
                old_session = self._sessions.get(current_device_id)
                if old_session:
                    logger.warning(f"Closing existing duplicate session for device {current_device_id}")
                    for fut in old_session.pending_commands.values():
                        if not fut.done():
                            fut.set_exception(ConnectionResetError("New agent session registered for device."))

                session = ConnectedAgentSession(
                    device_id=current_device_id,
                    websocket=websocket,
                    registration=reg,
                )
                self._sessions[current_device_id] = session

            await self.device_registry.register(device)

            # Send REGISTER_ACK
            ack_payload = RegisterAckPayload(
                device_id=current_device_id,
                server_version=__version__,
                heartbeat_interval_seconds=5.0,
                message="Registered with JARVIS Core",
            )
            ack_msg = AgentMessage(
                correlation_id=msg.correlation_id,
                message_type=MessageType.REGISTER_ACK,
                payload=ack_payload.model_dump(),
            )
            await websocket.send_text(ack_msg.model_dump_json())
            logger.info(f"Agent {current_device_id} ({reg.hostname}) registered successfully.")

            # 2. Continuous Message Processing Loop
            while True:
                text = await websocket.receive_text()
                try:
                    data = json.loads(text)
                    incoming = AgentMessage.model_validate(data)
                except Exception as e:
                    logger.warning(f"Failed to parse message from agent {current_device_id}: {e}")
                    continue

                session.update_heartbeat()

                if incoming.message_type == MessageType.HEARTBEAT:
                    hb = HeartbeatPayload.model_validate(incoming.payload)
                    device.last_seen = datetime.now(timezone.utc)
                    device.status = DeviceStatus.ONLINE
                    await self.device_registry.register(device)

                    hb_ack = HeartbeatAckPayload(device_id=current_device_id)
                    ack_resp = AgentMessage(
                        correlation_id=incoming.correlation_id,
                        message_type=MessageType.HEARTBEAT_ACK,
                        payload=hb_ack.model_dump(),
                    )
                    await websocket.send_text(ack_resp.model_dump_json())

                elif incoming.message_type == MessageType.COMMAND_RESULT:
                    try:
                        cmd_res = CommandResultPayload.model_validate(incoming.payload)
                        req_id = cmd_res.request_id
                        fut = session.pending_commands.get(req_id)
                        if fut and not fut.done():
                            fut.set_result(cmd_res)
                    except Exception as e:
                        logger.error(f"Error processing command result from {current_device_id}: {e}")

                elif incoming.message_type == MessageType.DISCONNECT:
                    logger.info(f"Agent {current_device_id} requested disconnect.")
                    break

        except WebSocketDisconnect:
            logger.info(f"Agent connection dropped: {current_device_id}")
        except Exception as e:
            logger.error(f"Error in agent connection {current_device_id}: {e}")
        finally:
            if current_device_id:
                async with self._lock:
                    closed_session = self._sessions.pop(current_device_id, None)
                    if closed_session:
                        for fut in closed_session.pending_commands.values():
                            if not fut.done():
                                fut.set_exception(ConnectionResetError("Agent disconnected."))

                # Update device status in registry
                dev = await self.device_registry.get(current_device_id)
                if dev:
                    dev.status = DeviceStatus.OFFLINE
                    await self.device_registry.register(dev)
                logger.info(f"Cleaned up session for agent {current_device_id}.")

    async def send_command(
        self,
        device_id: str,
        capability: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> CommandResultPayload:
        """Dispatch a command to a connected agent and await its response."""
        session = self.get_session(device_id)
        if not session:
            raise KeyError(f"Device '{device_id}' is not currently connected to Core.")

        # Validate capability
        if capability not in session.registration.capabilities:
            raise ValueError(
                f"Capability '{capability}' is not supported by agent {device_id}. "
                f"Supported capabilities: {session.registration.capabilities}"
            )

        cmd_req = CommandRequestPayload(
            device_id=device_id,
            capability=capability,
            parameters=parameters or {},
        )

        msg = AgentMessage(
            correlation_id=cmd_req.request_id,
            message_type=MessageType.COMMAND_REQUEST,
            payload=cmd_req.model_dump(),
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[CommandResultPayload] = loop.create_future()
        session.pending_commands[cmd_req.request_id] = future

        try:
            await session.websocket.send_text(msg.model_dump_json())
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"Command '{capability}' on device {device_id} timed out after {timeout}s.")
        finally:
            session.pending_commands.pop(cmd_req.request_id, None)
