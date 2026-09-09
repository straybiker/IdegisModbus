"""Low-level Modbus client for Idegis devices."""

from __future__ import annotations

import asyncio
import inspect
import logging
from time import monotonic
from typing import Any

from pymodbus.client import AsyncModbusTcpClient

LOGGER = logging.getLogger(__name__)


class IdegisModbusError(Exception):
    """Raised when the Modbus client cannot complete an operation."""


class IdegisModbusClient:
    """Thin async wrapper around pymodbus with pacing and locking.

    The lock is held for a complete logical operation, not for a single frame.
    Read-modify-write helpers must not release it between the read and the
    write, or a concurrent poll or write clobbers the result.
    """

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
        self._slave_kwarg: str | None = None

    async def async_connect(self) -> None:
        """Ensure the TCP client is connected."""
        async with self._lock:
            await self._async_connect_locked()

    async def async_close(self) -> None:
        """Close the underlying client."""
        async with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None

    async def _async_connect_locked(self) -> None:
        """Connect if needed. The caller must hold the lock."""
        if self._client is None:
            self._client = AsyncModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=self.timeout,
            )

        if self._client.connected:
            return

        try:
            connected = await self._client.connect()
        except Exception as err:
            raise IdegisModbusError(
                f"Unable to connect to Idegis bridge at {self.host}:{self.port}: {err}"
            ) from err

        if not connected:
            raise IdegisModbusError(
                f"Unable to connect to Idegis bridge at {self.host}:{self.port}"
            )

    async def _async_wait_gap(self) -> None:
        """Enforce a delay between Modbus frames."""
        elapsed = monotonic() - self._last_request
        wait_seconds = (self.message_wait_ms / 1000) - elapsed
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

    def _slave_keyword(self, method: Any) -> str:
        """Return the keyword pymodbus uses for the unit id.

        pymodbus renamed 'slave' to 'device_id' in 3.10. Resolve it once from
        the signature instead of provoking a TypeError on every single call.
        """
        if self._slave_kwarg is None:
            try:
                parameters = inspect.signature(method).parameters
            except (TypeError, ValueError):
                self._slave_kwarg = "slave"
            else:
                if "device_id" in parameters:
                    self._slave_kwarg = "device_id"
                elif "slave" in parameters:
                    self._slave_kwarg = "slave"
                else:
                    self._slave_kwarg = "device_id"
            LOGGER.debug("pymodbus unit-id keyword resolved to %s", self._slave_kwarg)
        return self._slave_kwarg

    async def _async_run_locked(self, method_name: str, *args, **kwargs):
        """Send one Modbus frame. The caller must hold the lock."""
        await self._async_connect_locked()
        await self._async_wait_gap()

        client = self._client
        if client is None:
            raise IdegisModbusError("Modbus client was closed during the request")

        method = getattr(client, method_name)
        kwargs[self._slave_keyword(method)] = self.slave
        try:
            response = await method(*args, **kwargs)
        except IdegisModbusError:
            raise
        except Exception as err:
            raise IdegisModbusError(
                f"Modbus call {method_name} failed: {err}"
            ) from err
        finally:
            # Pace off the last attempt, successful or not.
            self._last_request = monotonic()

        if response is None:
            raise IdegisModbusError(f"Empty response from {method_name}")
        if getattr(response, "isError", lambda: False)():
            raise IdegisModbusError(f"Modbus error on {method_name}: {response}")

        return response

    async def _async_read_registers_locked(
        self,
        method_name: str,
        address: int,
        count: int,
    ) -> list[int]:
        """Read a register block. The caller must hold the lock."""
        response = await self._async_run_locked(method_name, address, count=count)
        registers = getattr(response, "registers", None)
        if registers is None:
            raise IdegisModbusError(
                f"{method_name} response does not contain registers"
            )
        if len(registers) < count:
            raise IdegisModbusError(
                f"{method_name} at 0x{address:X} returned "
                f"{len(registers)} of {count} registers"
            )
        return list(registers)

    async def _async_write_register_locked(self, address: int, value: int) -> None:
        """Write one holding register. The caller must hold the lock."""
        await self._async_run_locked("write_register", address, value=value)

    async def async_read_input_registers(self, address: int, count: int) -> list[int]:
        """Read input registers."""
        async with self._lock:
            return await self._async_read_registers_locked(
                "read_input_registers", address, count
            )

    async def async_read_holding_registers(self, address: int, count: int) -> list[int]:
        """Read holding registers."""
        async with self._lock:
            return await self._async_read_registers_locked(
                "read_holding_registers", address, count
            )

    async def async_write_register(self, address: int, value: int) -> None:
        """Write a single holding register."""
        async with self._lock:
            await self._async_write_register_locked(address, value)

    async def _async_read_holding_locked(self, address: int) -> int:
        """Read one holding register. The caller must hold the lock."""
        registers = await self._async_read_registers_locked(
            "read_holding_registers", address, 1
        )
        return registers[0]

    async def async_write_register_bit_pulse(
        self,
        address: int,
        bit: int,
        pulse_ms: int = 200,
    ) -> None:
        """Pulse a bit in a holding register, preserving the rest of the register."""
        async with self._lock:
            current = await self._async_read_holding_locked(address)
            await self._async_write_register_locked(address, current | (1 << bit))
            await asyncio.sleep(pulse_ms / 1000)
            # Re-read before releasing. The controller latches its own bits in
            # this register, so the pre-pulse snapshot is already stale and
            # writing it back would erase those changes.
            latest = await self._async_read_holding_locked(address)
            await self._async_write_register_locked(address, latest & ~(1 << bit))

    async def async_write_register_bit(
        self,
        address: int,
        bit: int,
        is_on: bool,
    ) -> None:
        """Set or clear a bit in a holding register, preserving the rest."""
        async with self._lock:
            current = await self._async_read_holding_locked(address)
            if is_on:
                next_value = current | (1 << bit)
            else:
                next_value = current & ~(1 << bit)
            await self._async_write_register_locked(address, next_value)

    async def async_write_relay_state(self, address: int, is_on: bool) -> None:
        """Put an output relay into manual mode and set bit 14 on/off."""
        async with self._lock:
            current = await self._async_read_holding_locked(address)
            # Clear auto/manual and on/off, keep the rest of the scheduling bits untouched.
            next_value = current & ~((1 << 14) | (1 << 15))
            if is_on:
                next_value |= 1 << 14
            LOGGER.debug(
                "Writing relay state at 0x%X: current=%s next=%s",
                address,
                current,
                next_value,
            )
            await self._async_write_register_locked(address, next_value)
