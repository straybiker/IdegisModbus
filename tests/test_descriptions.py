"""Tests for the Idegis Modbus entity descriptions."""

from __future__ import annotations

from custom_components.idegis_modbus.coordinator import IdegisData
from custom_components.idegis_modbus.descriptions import BINARY_SENSOR_DESCRIPTIONS


class StubCoordinator:
    """Serves register values without a Modbus connection."""

    def __init__(self, input_registers: dict[int, int]) -> None:
        self.data = IdegisData(input_registers=input_registers, holding_registers={})

    def get_input(self, address: int) -> int | None:
        return self.data.input_registers.get(address)


def _value_fn(key: str):
    return next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == key).value_fn


def test_alarm_keys_are_unique() -> None:
    """Duplicate keys would collide in the entity registry."""
    keys = [d.key for d in BINARY_SENSOR_DESCRIPTIONS]
    assert len(keys) == len(set(keys))


def test_alarm_is_off_when_no_documented_bit_is_set() -> None:
    """A zero alarm word means no alarm."""
    assert _value_fn("salt_alarm")(StubCoordinator({0x29: 0})) is False


def test_alarm_is_on_for_each_documented_bit() -> None:
    """low_salt is bit 0 and high_salt is bit 1."""
    value_fn = _value_fn("salt_alarm")
    assert value_fn(StubCoordinator({0x29: 1 << 0})) is True
    assert value_fn(StubCoordinator({0x29: 1 << 1})) is True


def test_alarm_ignores_undocumented_bits() -> None:
    """An undocumented bit must not raise a false alarm."""
    # 0x28 documents bits 0 and 1 only.
    assert _value_fn("temperature_alarm")(StubCoordinator({0x28: 1 << 7})) is False


def test_chlorine_alarm_covers_bits_zero_to_nine() -> None:
    """0x27 documents ten implemented causes."""
    value_fn = _value_fn("chlorine_alarm")
    for bit in range(10):
        assert value_fn(StubCoordinator({0x27: 1 << bit})) is True
    assert value_fn(StubCoordinator({0x27: 1 << 10})) is False


def test_alarm_is_unknown_before_the_first_poll() -> None:
    """A missing register reads as unknown, not as a cleared alarm."""
    assert _value_fn("electrolysis_alarm")(StubCoordinator({})) is None
