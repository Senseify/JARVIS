"""Windows Agent client connecting to JARVIS Core over WebSocket."""

import asyncio
from datetime import datetime, timezone
import json
import logging
import platform
import socket
import sys
import time
from typing import Any, Dict, Optional
from uuid import uuid4

import websockets
from websockets.exceptions import ConnectionClosed

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
from windows_agent.capabilities import CapabilityRegistry

logger = logging.getLogger(__name__)


class WindowsAgent:
    """Standalone machine agent that registers with JARVIS Core and executes authorized capabilities."""

    def __init__(
        self,
        core_url: str = "ws://127.0.0.1:8000/ws/agent",
        device_id: Optional[str] = None,
        hostname: Optional[str] = None,
        heartbeat_interval: float = 5.0,
        agent_version: str = "0.1.0",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.core_url = core_url
        self.device_id = device_id or f"win-agent-{socket.gethostname()}"
        self.hostname = hostname or socket.gethostname()
        self.heartbeat_interval = heartbeat_interval
        self.agent_version = agent_version
        self.metadata = metadata or {}
        self.start_time = time.time()

        self.capabilities = CapabilityRegistry(
            agent_version=self.agent_version,
            start_time=self.start_time,
        )

        self._ws = None
        self._running = False
        self._connected = False
        self._main_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        """Check whether the agent is currently connected to Core."""
        return self._connected and self._ws is not None

    async def start(self) -> None:
        """Start the agent connection loop in the background."""
        self._running = True
        self._main_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Cleanly disconnect and stop the agent."""
        self._running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()

        if self._ws:
            try:
                disc_msg = AgentMessage(
                    correlation_id=str(uuid4()),
                    message_type=MessageType.DISCONNECT,
                    payload={"device_id": self.device_id},
                )
                await self._ws.send(disc_msg.model_dump_json())
                await self._ws.close()
            except Exception:
                pass

        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass

        self._connected = False
        logger.info(f"Windows Agent {self.device_id} stopped.")

    async def _run_loop(self) -> None:
        """Persistent connection and reconnect loop."""
        while self._running:
            try:
                logger.info(f"Connecting to JARVIS Core at {self.core_url}...")
                async with websockets.connect(self.core_url) as ws:
                    self._ws = ws
                    # 1. Perform Registration Handshake
                    registered = await self._perform_registration(ws)
                    if not registered:
                        logger.error("Registration failed. Retrying in 3 seconds...")
                        await asyncio.sleep(3.0)
                        continue

                    self._connected = True
                    logger.info(f"Windows Agent connected and registered with Core.")

                    # 2. Start periodic heartbeat task
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

                    # 3. Message reception loop
                    await self._message_loop(ws)

            except ConnectionClosed as e:
                logger.warning(f"Connection to Core closed: {e}")
            except Exception as e:
                logger.warning(f"Agent connection error: {e}")
            finally:
                self._connected = False
                self._ws = None
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()

            if self._running:
                await asyncio.sleep(2.0)

    async def _perform_registration(self, ws) -> bool:
        """Send registration envelope and await REGISTER_ACK."""
        reg_payload = AgentRegistrationPayload(
            device_id=self.device_id,
            hostname=self.hostname,
            platform=platform.system(),
            agent_version=self.agent_version,
            capabilities=self.capabilities.list_capabilities(),
            metadata=self.metadata,
        )

        corr_id = str(uuid4())
        msg = AgentMessage(
            correlation_id=corr_id,
            message_type=MessageType.REGISTER,
            payload=reg_payload.model_dump(),
        )

        await ws.send(msg.model_dump_json())
        resp_text = await ws.recv()
        resp_data = json.loads(resp_text)
        resp_msg = AgentMessage.model_validate(resp_data)

        if resp_msg.message_type == MessageType.REGISTER_ACK:
            ack = RegisterAckPayload.model_validate(resp_msg.payload)
            self.heartbeat_interval = ack.heartbeat_interval_seconds
            logger.info(f"Core acknowledged registration: {ack.message}")
            return True
        else:
            logger.error(f"Unexpected response to registration: {resp_msg}")
            return False

    async def _heartbeat_loop(self, ws) -> None:
        """Periodically emit HEARTBEAT messages to Core."""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                uptime = time.time() - self.start_time
                hb_payload = HeartbeatPayload(
                    device_id=self.device_id,
                    uptime_seconds=round(uptime, 2),
                    status="online",
                )
                msg = AgentMessage(
                    correlation_id=str(uuid4()),
                    message_type=MessageType.HEARTBEAT,
                    payload=hb_payload.model_dump(),
                )
                await ws.send(msg.model_dump_json())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat send failed: {e}")
                break

    async def _message_loop(self, ws) -> None:
        """Process messages received from Core."""
        async for raw_message in ws:
            try:
                data = json.loads(raw_message)
                msg = AgentMessage.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to parse incoming message from Core: {e}")
                continue

            if msg.message_type == MessageType.COMMAND_REQUEST:
                await self._handle_command_request(ws, msg)
            elif msg.message_type == MessageType.HEARTBEAT_ACK:
                pass
            elif msg.message_type == MessageType.DISCONNECT:
                logger.info("Core requested disconnect.")
                break

    async def _handle_command_request(self, ws, msg: AgentMessage) -> None:
        """Execute requested capability and reply with CommandResultPayload."""
        try:
            req = CommandRequestPayload.model_validate(msg.payload)
        except Exception as e:
            err_result = CommandResultPayload(
                request_id=msg.correlation_id,
                device_id=self.device_id,
                capability="unknown",
                success=False,
                error=f"Malformed command request payload: {e}",
            )
            reply = AgentMessage(
                correlation_id=msg.correlation_id,
                message_type=MessageType.COMMAND_RESULT,
                payload=err_result.model_dump(),
            )
            await ws.send(reply.model_dump_json())
            return

        try:
            result_data = await self.capabilities.execute(
                req.capability,
                req.parameters,
                request_id=req.request_id,
            )
            cmd_result = CommandResultPayload(
                request_id=req.request_id,
                device_id=self.device_id,
                capability=req.capability,
                success=True,
                result=result_data,
            )
        except Exception as e:
            logger.warning(f"Command execution error for {req.capability}: {e}")
            cmd_result = CommandResultPayload(
                request_id=req.request_id,
                device_id=self.device_id,
                capability=req.capability,
                success=False,
                error=str(e),
            )

        reply = AgentMessage(
            correlation_id=req.request_id,
            message_type=MessageType.COMMAND_RESULT,
            payload=cmd_result.model_dump(),
        )
        await ws.send(reply.model_dump_json())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = WindowsAgent()

    async def main():
        await agent.start()
        print(f"Windows Agent started. Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await agent.stop()

    asyncio.run(main())
