"""UniLED NETwork Device Handler."""
from __future__ import annotations
from typing import Any, Final
from ..device import UniledDevice, ParseNotificationError
from ..model import UniledModel
from ..const import (
    UNILED_COMMAND_SETTLE_DELAY as UNILED_NET_COMMAND_SETTLE_DELAY,
)

import async_timeout
import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

UNILED_TRANSPORT_NET: Final = "net"


##
## UniLed NETwork Model Handler
##
class UniledNetModel(UniledModel):
    """UniLED NETwork Model Class"""


##
## UniLed NETwork Device Handler
##
class UniledNetDevice(UniledDevice):
    """UniLED NETwork Device Class"""

    @staticmethod
    def match_model_name(model_name: str) -> UniledNetModel | None:
        """Lookup model from name."""
        from .models import UNILED_NET_MODELS

        for model in UNILED_NET_MODELS:
            if model.model_name.upper() == str(model_name).upper():
                return model
        return None

    def __init__(
        self,
        config: Any,
        host: str,
        port: int,
        model_name: str | None = None,
    ) -> None:
        """Initialize network device."""
        self._host = host
        self._port = int(port)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._io_lock = asyncio.Lock()
        super().__init__(config)
        if model_name is not None and self._model is None:
            self._set_model(self.match_model_name(model_name))

    def _set_model(self, model: UniledNetModel | None) -> None:
        """Set model instance."""
        if self._model is None and isinstance(model, UniledNetModel):
            self._model = model
            self._create_channels()
            _LOGGER.debug("%s: Set network model as '%s'", self.name, model.model_name)

    @property
    def transport(self) -> str:
        """Return the device transport."""
        return UNILED_TRANSPORT_NET

    @property
    def name(self) -> str:
        """Return a human-friendly name."""
        if self._model is not None:
            return f"{self._model.model_name} ({self._host})"
        return self._host

    @property
    def address(self) -> str:
        """Return the device network address."""
        return self._host

    @property
    def available(self) -> bool:
        """Return whether the socket is connected."""
        return bool(self._writer and not self._writer.is_closing())

    async def update(self, retry: int | None = None) -> bool:
        """Update device state."""
        if self._model is None:
            return False
        query = self._model.build_state_query(self)
        if not query:
            return False
        try:
            packet = await self._transact(query)
            parsed = self._model.parse_notifications(self, 0, packet)
            return bool(parsed)
        except ParseNotificationError as ex:
            _LOGGER.warning("%s: Failed to parse network packet: %s", self.name, str(ex))
            return False
        except Exception:
            _LOGGER.warning("%s: Failed network update", self.name, exc_info=True)
            return False

    async def stop(self) -> None:
        """Close connection."""
        await self._disconnect()

    async def send(
        self, commands: list[bytes] | bytes, retry: int | None = None
    ) -> bool:
        """Send command(s) to a network device."""
        if not commands:
            return False
        if not isinstance(commands, list):
            commands = [commands]
        try:
            await self._ensure_connected()
            async with self._io_lock:
                for command in commands:
                    if not command:
                        continue
                    self._writer.write(command)
                    await self._writer.drain()
                    if len(commands) > 1:
                        await asyncio.sleep(UNILED_NET_COMMAND_SETTLE_DELAY)
            return True
        except Exception:
            _LOGGER.warning("%s: Network send failed", self.name, exc_info=True)
            await self._disconnect()
            return False

    async def _transact(self, command: bytes, timeout: float = 5.0) -> bytearray:
        """Send a command and read back one packet response."""
        await self._ensure_connected()
        async with self._io_lock:
            self._writer.write(command)
            await self._writer.drain()
            async with async_timeout.timeout(timeout):
                return await self._read_packet()

    async def _read_packet(self) -> bytearray:
        """Read one BanlanX network packet."""
        assert self._reader is not None  # nosec
        header = await self._reader.readexactly(13)
        if header[0:7] != b"SPTECH\x00":
            raise ParseNotificationError(f"Unexpected net packet header: {header.hex()}")
        payload_size = int.from_bytes(header[11:13], byteorder="big")
        payload = await self._reader.readexactly(payload_size) if payload_size else b""
        return bytearray(header + payload)

    async def _ensure_connected(self) -> None:
        """Ensure TCP connection exists."""
        if self.available and self._reader is not None:
            return
        await self._disconnect()
        _LOGGER.debug("%s: Connecting to %s:%s", self.name, self._host, self._port)
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        _LOGGER.debug("%s: Connected to %s:%s", self.name, self._host, self._port)

    async def _disconnect(self) -> None:
        """Disconnect TCP socket."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None
