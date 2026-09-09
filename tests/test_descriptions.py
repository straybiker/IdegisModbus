"""Tests for the Idegis Modbus entity descriptions."""

from __future__ import annotations

import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.util import dt as dt_util

from custom_components.idegis_modbus.coordinator import IdegisData
from custom_components.idegis_modbus.descriptions import (
    BINARY_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
)


class StubCoordinator:
    """Serves register values without a Modbus connection."""

    def __init__(self, input_registers: dict[int, int]) -> None:
        self.data = IdegisData(input_registers=input_registers, holding_registers={})

    def get_input(self, address: int) -> int | None:
        return self.data.input_registers.get(address)


def _value_fn(key: str):
    return next(d for d in BINARY_SENSOR_DESCRIPTIONS if d.key == key).value_fn


def _sensor(key: str):
    return next(d for d in SENSOR_DESCRIPTIONS if d.key == key)


def _packed(hour: int, minute: int) -> int:
    """Pack a time the way the controller does: hour low, minute high."""
    return (minute << 8) | hour


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


@pytest.mark.parametrize(
    ("key", "address", "raw", "hour", "minute"),
    [
        # Captured from the controller on 10/09/2026: 07:03 and 20:09.
        ("sunrise", 0xF0, 775, 7, 3),
        ("sunset", 0xF1, 2324, 20, 9),
    ],
)
def test_packed_time_decodes_captured_values(key, address, raw, hour, minute) -> None:
    """The hour is in the low byte and the minute in the high byte."""
    value = _sensor(key).value_fn(StubCoordinator({address: raw}))
    assert (value.hour, value.minute) == (hour, minute)
    assert value.second == 0 and value.microsecond == 0


def test_packed_time_is_timezone_aware_and_dated_today() -> None:
    """A TIMESTAMP sensor must return an aware datetime."""
    value = _sensor("sunrise").value_fn(StubCoordinator({0xF0: _packed(7, 3)}))
    assert value.tzinfo is not None
    assert value.utcoffset() is not None
    assert value.date() == dt_util.now().date()


def test_packed_time_round_trips_every_valid_clock_time() -> None:
    """Decoding is the exact inverse of the controller's packing."""
    for hour in range(24):
        for minute in (0, 1, 29, 30, 59):
            value = _sensor("sunset").value_fn(
                StubCoordinator({0xF1: _packed(hour, minute)})
            )
            # 00:00 packs to 0, which means "not computed yet".
            if hour == 0 and minute == 0:
                assert value is None
                continue
            assert (value.hour, value.minute) == (hour, minute)


def test_packed_time_is_unknown_when_not_yet_computed() -> None:
    """Both registers are volatile with a factory default of 0."""
    assert _sensor("sunrise").value_fn(StubCoordinator({0xF0: 0})) is None


def test_packed_time_is_unknown_before_the_first_poll() -> None:
    assert _sensor("sunset").value_fn(StubCoordinator({})) is None


@pytest.mark.parametrize("raw", [24, _packed(25, 0), _packed(7, 60), _packed(9, 99)])
def test_packed_time_rejects_impossible_clock_values(raw) -> None:
    """A bad read must show as unknown rather than a plausible wrong time."""
    assert _sensor("sunrise").value_fn(StubCoordinator({0xF0: raw})) is None


def test_packed_time_would_reject_the_old_plain_integer_reading() -> None:
    """Guards the bug this replaced.

    Reading 0xF1 as a plain integer gave 2324, which looked like a number but
    was not a time. Decoded it is 20:09; the naive minutes-since-midnight
    reading would have been 38:44.
    """
    value = _sensor("sunset").value_fn(StubCoordinator({0xF1: 2324}))
    assert value.hour * 60 + value.minute == 20 * 60 + 9 != 2324


def test_sunrise_and_sunset_are_timestamp_sensors() -> None:
    for key in ("sunrise", "sunset"):
        d = _sensor(key)
        assert d.device_class is SensorDeviceClass.TIMESTAMP
        # A timestamp cannot carry a unit or a numeric state class.
        assert d.native_unit_of_measurement is None
        assert d.state_class is None
        assert d.enabled_default is True
