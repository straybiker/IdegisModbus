"""Low-level Modbus client for Idegis devices."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic

from pymodbus.client import AsyncModbusTcpClient

LOGGER = logging.getLogger(__name__)


class IdegisModbusError(Exception):
    """Raised when the Modbus client cannot complete an operation."""


class IdegisModbusClient:
    """Thin async wrapper around pymodbus with pacing and locking."""

    def __init__(
        self,
        host: str,
        port: int,
        slave: int,
        timeout: int,
        message_wait_ms: int,
    ) -> None:
        self.host = host
        self.port = port
        self.slave = slave
        self.timeout = timeout
        self.message_wait_ms = message_wait_ms
        self._client: AsyncModbusTcpClient | None = None
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def async_connect(self) -> None:
        """Ensure the TCP client is connected."""
        if self._client is None:
            self._client = AsyncModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=self.timeout,
            )

        if self._client.connected:
            return

        connected = await self._client.connect()
        if not connected:
            raise IdegisModbusError(
                f"Unable to connect to Idegis bridge at {self.host}:{self.port}"
            )

    async def async_close(self) -> None:
        """Close the underlying client."""
        if self._client is not None:
            self._client.close()

    async def _async_wait_gap(self) -> None:
        """Enforce a delay between Modbus frames."""
        elapsed = monotonic() - self._last_request
        wait_seconds = (self.message_wait_ms / 1000) - elapsed
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

    async def _async_run(self, method_name: str, *args, **kwargs):
        """Serialize Modbus access and validate responses."""
        async with self._lock:
            await self.async_connect()
            await self._async_wait_gap()

            assert self._client is not None
            method = getattr(self._client, method_name)
            try:
                response = await method(*args, device_id=self.slave, **kwargs)
            except TypeError:
                # pymodbus < 3.10 uses 'slave=' instead of 'device_id='
                response = await method(*args, slave=self.slave, **kwargs)
            self._last_request = monotonic()

            if response is None:
                raise IdegisModbusError(f"Empty response from {method_name}")
            if getattr(response, "isError", lambda: False)():
                raise IdegisModbusError(f"Modbus error on {method_name}: {response}")

            return response

    async def async_read_input_registers(self, address: int, count: int) -> list[int]:
        """Read input registers."""
        response = await self._async_run("read_input_registers", address, count=count)
        registers = getattr(response, "registers", None)
        if registers is None:
            raise IdegisModbusError("Input register response does not contain registers")
        return list(registers)

    async def async_read_holding_registers(self, address: int, count: int) -> list[int]:
        """Read holding registers."""
        response = await self._async_run("read_holding_registers", address, count=count)
        registers = getattr(response, "registers", None)
        if registers is None:
            raise IdegisModbusError(
                "Holding register response does not contain registers"
            )
        return list(registers)

    async def async_write_register(self, address: int, value: int) -> None:
        """Write a single holding register."""
        await self._async_run("write_register", address, value=value)

    async def async_write_register_bit_pulse(
        self,
        address: int,
        bit: int,
        pulse_ms: int = 200,
    ) -> None:
        """Pulse a bit in a holding register, preserving the rest of the register."""
        current = (await self.async_read_holding_registers(address, 1))[0]
        pressed = current | (1 << bit)
        released = current & ~(1 << bit)
        await self.async_write_register(address, pressed)
        await asyncio.sleep(pulse_ms / 1000)
        await self.async_write_register(address, released)

    async def async_write_register_bit(
        self,
        address: int,
        bit: int,
        is_on: bool,
    ) -> None:
        """Set or clear a bit in a holding register, preserving the rest."""
        current = (await self.async_read_holding_registers(address, 1))[0]
        if is_on:
            next_value = current | (1 << bit)
        else:
            next_value = current & ~(1 << bit)
        await self.async_write_register(address, next_value)

    async def async_write_relay_state(self, address: int, is_on: bool) -> None:
        """Put an output relay into manual mode and set bit 14 on/off."""
        current = (await self.async_read_holding_registers(address, 1))[0]
        # Clear auto/manual and on/off, keep the rest of the scheduling bits untouched.
        next_value = current & ~((1 << 14) | (1 << 15))
        if is_on:
            next_value |= 1 << 14
        LOGGER.debug(
            "Writing relay state at 0x%X: current=%s next=%s", address, current, next_value
        )
        await self.async_write_register(address, next_value)
