"""Data coordinator for Idegis Modbus."""

from __future__ import annotations

from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import IdegisModbusClient, IdegisModbusError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    HOLDING_BLOCKS,
    INPUT_BLOCKS,
    OUTPUT_STATE_INPUT_REGISTERS,
    OUTPUT_SWITCH_REGISTERS,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class IdegisData:
    """Snapshot of the raw register state."""

    input_registers: dict[int, int] = field(default_factory=dict)
    holding_registers: dict[int, int] = field(default_factory=dict)


class IdegisModbusCoordinator(DataUpdateCoordinator[IdegisData]):
    """Coordinate all polling and writes for an Idegis device."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: IdegisModbusClient,
        name: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=name,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> IdegisData:
        """Fetch all configured Modbus blocks."""
        try:
            input_registers: dict[int, int] = {}
            holding_registers: dict[int, int] = {}

            for block in INPUT_BLOCKS:
                values = await self.client.async_read_input_registers(
                    block.start, block.count
                )
                for offset, value in enumerate(values):
                    input_registers[block.start + offset] = value

            for block in HOLDING_BLOCKS:
                values = await self.client.async_read_holding_registers(
                    block.start, block.count
                )
                for offset, value in enumerate(values):
                    holding_registers[block.start + offset] = value

            return IdegisData(
                input_registers=input_registers,
                holding_registers=holding_registers,
            )
        except IdegisModbusError as err:
            raise UpdateFailed(str(err)) from err

    def get_input(self, address: int) -> int | None:
        """Return an input register value."""
        if self.data is None:
            return None
        return self.data.input_registers.get(address)

    def get_holding(self, address: int) -> int | None:
        """Return a holding register value."""
        if self.data is None:
            return None
        return self.data.holding_registers.get(address)

    def get_input_bit(self, address: int, bit: int) -> bool | None:
        """Return a bit from an input register."""
        value = self.get_input(address)
        if value is None:
            return None
        return bool(value & (1 << bit))

    def get_holding_bit(self, address: int, bit: int) -> bool | None:
        """Return a bit from a holding register."""
        value = self.get_holding(address)
        if value is None:
            return None
        return bool(value & (1 << bit))

    def get_u32_input(self, lsb_address: int) -> int | None:
        """Return a uint32 assembled from two input registers."""
        low = self.get_input(lsb_address)
        high = self.get_input(lsb_address + 1)
        if low is None or high is None:
            return None
        return low | (high << 16)

    async def _async_write(
        self,
        action: str,
        coro: Coroutine[Any, Any, None],
    ) -> None:
        """Run a write, translate Modbus errors, then refresh.

        HomeAssistantError renders as a readable message in the UI. A raw
        IdegisModbusError surfaces as "unknown error".
        """
        try:
            await coro
        except IdegisModbusError as err:
            raise HomeAssistantError(f"Idegis Modbus {action} failed: {err}") from err
        await self.async_request_refresh()

    async def async_set_relay(self, relay_key: str, is_on: bool) -> None:
        """Write a relay state and refresh."""
        await self._async_write(
            f"relay write for {relay_key}",
            self.client.async_write_relay_state(
                OUTPUT_SWITCH_REGISTERS[relay_key], is_on
            ),
        )

    def get_relay_state(self, relay_key: str) -> bool | None:
        """Return the current relay state from the input status register."""
        return self.get_input_bit(OUTPUT_STATE_INPUT_REGISTERS[relay_key], 0)

    async def async_set_holding_value(self, address: int, value: int) -> None:
        """Write a holding register and refresh."""
        await self._async_write(
            f"write of 0x{address:X}",
            self.client.async_write_register(address, value),
        )

    async def async_set_holding_bit(self, address: int, bit: int, is_on: bool) -> None:
        """Write one bit in a holding register and refresh."""
        await self._async_write(
            f"bit write of 0x{address:X}.{bit}",
            self.client.async_write_register_bit(address, bit, is_on),
        )

    async def async_press_button(self, address: int, bit: int) -> None:
        """Press a pulse-style maintenance action."""
        await self._async_write(
            f"pulse of 0x{address:X}.{bit}",
            self.client.async_write_register_bit_pulse(address, bit),
        )
