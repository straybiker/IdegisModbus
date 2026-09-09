"""Tests for the Idegis Modbus client helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.idegis_modbus.client import (
    IdegisModbusClient,
    IdegisModbusError,
)


class FakeDevice:
    """In-memory holding-register bank that records the frames it received.

    It replaces a single Modbus frame, not a whole operation, so the client's
    own locking and read-modify-write sequencing stay under test.
    """

    def __init__(self, registers: dict[int, int] | None = None) -> None:
        self.registers: dict[int, int] = dict(registers or {})
        self.frames: list[tuple[str, int]] = []

    async def run(self, method_name: str, *args, **kwargs):
        """Stand in for IdegisModbusClient._async_run_locked."""
        address = args[0]
        self.frames.append((method_name, address))
        # Yield so concurrent operations can interleave if the lock allows it.
        await asyncio.sleep(0)

        if method_name in ("read_holding_registers", "read_input_registers"):
            count = kwargs["count"]
            return SimpleNamespace(
                registers=[self.registers.get(address + i, 0) for i in range(count)],
                isError=lambda: False,
            )
        if method_name == "write_register":
            self.registers[address] = kwargs["value"]
            return SimpleNamespace(isError=lambda: False)
        raise AssertionError(f"unexpected frame {method_name}")


def make_client(device: FakeDevice) -> IdegisModbusClient:
    """Build a client wired to a fake device with no request pacing."""
    client = IdegisModbusClient("127.0.0.1", 4196, 1, 2, 0)
    client._async_run_locked = device.run
    return client


@pytest.mark.asyncio
async def test_async_write_relay_state_preserves_schedule_bits() -> None:
    """Turning a relay on/off should preserve unrelated bits."""
    device = FakeDevice({0x110: 0b0000_0001_0000_1111})
    await make_client(device).async_write_relay_state(0x110, True)
    assert device.registers[0x110] == 0b0100_0001_0000_1111


@pytest.mark.asyncio
async def test_async_write_relay_state_forces_manual_mode_off_bit15() -> None:
    """Turning a relay off should also clear auto mode."""
    device = FakeDevice({0x110: 0b1100_0000_0000_0000})
    await make_client(device).async_write_relay_state(0x110, False)
    assert device.registers[0x110] == 0


@pytest.mark.asyncio
async def test_async_write_register_bit_preserves_unrelated_bits() -> None:
    """Writing a control-word bit should preserve every other bit."""
    device = FakeDevice({0x56: 0b0000_0000_0000_0101})
    await make_client(device).async_write_register_bit(0x56, 6, True)
    assert device.registers[0x56] == 0b0000_0000_0100_0101


@pytest.mark.asyncio
async def test_async_write_register_bit_can_clear_bit() -> None:
    """Clearing a control-word bit should preserve every other bit."""
    device = FakeDevice({0x56: 0b0000_0000_0100_0101})
    await make_client(device).async_write_register_bit(0x56, 6, False)
    assert device.registers[0x56] == 0b0000_0000_0000_0101


@pytest.mark.asyncio
async def test_concurrent_bit_writes_do_not_lose_updates() -> None:
    """Two switches sharing one register must not clobber each other.

    Register 0x56 carries ph_intelligent_dosing (bit 6) and ph_tank_detection
    (bit 7). If the lock is released between the read and the write, both
    operations read the same value and the second write drops the first bit.
    """
    device = FakeDevice({0x56: 0})
    client = make_client(device)

    await asyncio.gather(
        client.async_write_register_bit(0x56, 6, True),
        client.async_write_register_bit(0x56, 7, True),
    )

    assert device.registers[0x56] == 0b1100_0000


@pytest.mark.asyncio
async def test_concurrent_relay_write_and_bit_write_are_serialised() -> None:
    """A relay write must not interleave with a bit write on the same register."""
    device = FakeDevice({0x110: 0})
    client = make_client(device)

    await asyncio.gather(
        client.async_write_relay_state(0x110, True),
        client.async_write_register_bit(0x110, 3, True),
    )

    # Whichever order they run in, both bits survive.
    assert device.registers[0x110] == (1 << 14) | (1 << 3)


@pytest.mark.asyncio
async def test_pulse_release_preserves_bits_set_during_the_pulse() -> None:
    """The pulse release must re-read instead of writing a stale snapshot.

    Buttons and switches share register 0x56. Writing back the pre-pulse value
    would erase any bit the controller latched while the pulse was held.
    """
    device = FakeDevice({0x56: 0})
    client = make_client(device)

    async def latch_another_bit() -> None:
        await asyncio.sleep(0.01)
        device.registers[0x56] |= 1 << 6

    await asyncio.gather(
        client.async_write_register_bit_pulse(0x56, 14, pulse_ms=40),
        latch_another_bit(),
    )

    assert device.registers[0x56] == 1 << 6
    assert device.frames == [
        ("read_holding_registers", 0x56),
        ("write_register", 0x56),
        ("read_holding_registers", 0x56),
        ("write_register", 0x56),
    ]


@pytest.mark.asyncio
async def test_short_register_response_raises() -> None:
    """A truncated response must raise instead of causing an IndexError."""
    device = FakeDevice({0x40: 1})

    async def short_read(method_name: str, *args, **kwargs):
        return SimpleNamespace(registers=[1], isError=lambda: False)

    client = make_client(device)
    client._async_run_locked = short_read

    with pytest.raises(IdegisModbusError, match="returned 1 of 4 registers"):
        await client.async_read_input_registers(0x40, 4)


def test_slave_keyword_prefers_device_id_when_available() -> None:
    """pymodbus 3.10+ takes device_id; older releases take slave."""
    client = IdegisModbusClient("127.0.0.1", 4196, 1, 2, 0)

    def new_api(address: int, *, count: int = 1, device_id: int = 1) -> None: ...

    assert client._slave_keyword(new_api) == "device_id"


def test_slave_keyword_falls_back_to_slave() -> None:
    """The keyword is resolved from the signature, not from a TypeError."""
    client = IdegisModbusClient("127.0.0.1", 4196, 1, 2, 0)

    def old_api(address: int, *, count: int = 1, slave: int = 1) -> None: ...

    assert client._slave_keyword(old_api) == "slave"


def test_slave_keyword_is_resolved_only_once() -> None:
    """The resolved keyword is cached across calls."""
    client = IdegisModbusClient("127.0.0.1", 4196, 1, 2, 0)

    def old_api(address: int, *, slave: int = 1) -> None: ...

    def new_api(address: int, *, device_id: int = 1) -> None: ...

    assert client._slave_keyword(old_api) == "slave"
    assert client._slave_keyword(new_api) == "slave"
