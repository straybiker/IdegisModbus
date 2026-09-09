"""Entity descriptions for Idegis Modbus."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .coordinator import IdegisModbusCoordinator


NumericValueFn = Callable[[IdegisModbusCoordinator], int | float | None]
SensorValueFn = Callable[[IdegisModbusCoordinator], int | float | datetime | None]
BoolValueFn = Callable[[IdegisModbusCoordinator], bool | None]


@dataclass(frozen=True, slots=True)
class SensorDescription:
    key: str
    name: str
    value_fn: SensorValueFn
    icon: str | None = None
    native_unit_of_measurement: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    entity_category: EntityCategory | None = None
    enabled_default: bool = True
    feature_group: str = "core"


@dataclass(frozen=True, slots=True)
class BinarySensorDescription:
    key: str
    name: str
    value_fn: BoolValueFn
    icon: str | None = None
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    enabled_default: bool = True
    feature_group: str = "core"


@dataclass(frozen=True, slots=True)
class NumberDescription:
    key: str
    name: str
    value_fn: NumericValueFn
    write_address: int
    min_value: float
    max_value: float
    step: float
    multiplier: int = 1
    native_unit_of_measurement: str | None = None
    icon: str | None = None


@dataclass(frozen=True, slots=True)
class SwitchDescription:
    key: str
    name: str
    value_fn: BoolValueFn | None = None
    write_address: int | None = None
    bit: int | None = None
    icon: str | None = None
    entity_category: EntityCategory | None = None
    feature_group: str = "core"


@dataclass(frozen=True, slots=True)
class ButtonDescription:
    key: str
    name: str
    write_address: int
    bit: int
    icon: str | None = None
    entity_category: EntityCategory | None = EntityCategory.CONFIG
    feature_group: str = "maintenance"


def _scaled_input(address: int, scale: float) -> NumericValueFn:
    return lambda coordinator: (
        None
        if coordinator.get_input(address) is None
        else round(coordinator.get_input(address) * scale, 2)
    )


def _scaled_holding(address: int, scale: float) -> NumericValueFn:
    return lambda coordinator: (
        None
        if coordinator.get_holding(address) is None
        else round(coordinator.get_holding(address) * scale, 2)
    )


def _packed_time(address: int) -> SensorValueFn:
    """Decode a packed clock time from an input register.

    The v1.63 register table calls 0xF0 and 0xF1 "HHMM (hora/minuto)", but the
    hour sits in the LOW byte and the minute in the high byte. Read as a plain
    integer the register looks like nonsense: 20:09 arrives as 2324.

    Reports what the controller believes, which is what drives its own
    scheduling. It is deliberately not corrected towards astronomical truth --
    Home Assistant already knows the real sunrise from the configured home
    coordinates via sun.sun.

    The register carries only an hour and a minute, so today's local date is
    attached. The controller does not recompute at midnight: shortly after
    00:00 these registers still hold the previous day's times, which differ by
    a couple of minutes at this latitude. Treat the value as "the controller's
    current idea of sunrise", not as an almanac entry for today.
    """

    def value(coordinator: IdegisModbusCoordinator) -> datetime | None:
        raw = coordinator.get_input(address)
        # Both registers are volatile with a factory default of 0, so zero
        # means the controller has not computed a time yet.
        if not raw:
            return None
        hour, minute = raw & 0xFF, (raw >> 8) & 0xFF
        if hour > 23 or minute > 59:
            return None
        # Attach the zone to a naive wall-clock time so zoneinfo picks the
        # right offset. Adding a timedelta to local midnight would drift by an
        # hour on the two daylight-saving transition days.
        naive = datetime.combine(dt_util.now().date(), time(hour, minute))
        return naive.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

    return value


def _input_mask(address: int, mask: int) -> BoolValueFn:
    """True when any masked bit of an input register is set.

    The alarm words carry several causes each. Masking to the bits the v1.63
    register table documents as implemented stops an undocumented bit from
    raising a false alarm.
    """
    return lambda coordinator: (
        None
        if coordinator.get_input(address) is None
        else bool(coordinator.get_input(address) & mask)
    )


SWITCH_DESCRIPTIONS = (
    SwitchDescription("pool_pump", "Pool Pump"),
    SwitchDescription("relay_square", "Relay Square"),
    SwitchDescription("relay_triangle", "Relay Triangle"),
    SwitchDescription("pool_led_light", "Pool Led Light"),
    SwitchDescription(
        "ph_intelligent_dosing",
        "PH Intelligent Dosing",
        lambda coordinator: coordinator.get_holding_bit(0x56, 6),
        write_address=0x56,
        bit=6,
        icon="mdi:brain",
        entity_category=EntityCategory.CONFIG,
    ),
    SwitchDescription(
        "ph_tank_detection",
        "PH Tank Detection",
        lambda coordinator: coordinator.get_holding_bit(0x56, 7),
        write_address=0x56,
        bit=7,
        icon="mdi:bottle-tonic-plus-outline",
        entity_category=EntityCategory.CONFIG,
    ),
)

SENSOR_DESCRIPTIONS = (
    SensorDescription(
        "water_temperature",
        "Water Temperature",
        _scaled_input(0xB1, 0.1),
        native_unit_of_measurement="°C",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorDescription(
        "salt_concentration",
        "Salt Concentration",
        _scaled_input(0xC1, 0.01),
        native_unit_of_measurement="g/L",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:shaker",
    ),
    SensorDescription(
        "current_ph",
        "Current PH",
        _scaled_input(0x51, 0.01),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorDescription(
        "target_ph",
        "Target PH",
        _scaled_holding(0x57, 0.01),
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "current_orp",
        "Current ORP",
        lambda coordinator: coordinator.get_input(0x81),
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorDescription(
        "target_orp",
        "Target ORP",
        lambda coordinator: coordinator.get_holding(0x87),
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "current_free_chlorine",
        "Current Free Chlorine",
        _scaled_input(0x83, 0.01),
        native_unit_of_measurement="ppm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cup-water",
    ),
    SensorDescription(
        "target_free_chlorine",
        "Target Free Chlorine",
        _scaled_holding(0x88, 0.01),
        native_unit_of_measurement="ppm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "electrolysis_production",
        "Electrolysis Production",
        lambda coordinator: coordinator.get_input(0x42),
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
    ),
    SensorDescription(
        "target_electrolysis_production",
        "Target Electrolysis Production",
        lambda coordinator: coordinator.get_holding(0x41),
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "cell_current",
        "Cell Current",
        _scaled_input(0x43, 0.01),
        native_unit_of_measurement="A",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.CURRENT,
    ),
    SensorDescription(
        "cell_voltage",
        "Cell Voltage",
        _scaled_input(0x44, 0.01),
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorDescription(
        "instant_chlorine_production",
        "Instant Chlorine Production",
        lambda coordinator: coordinator.get_input(0x45),
        native_unit_of_measurement="g/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:beaker-outline",
    ),
    SensorDescription(
        "chlorine_produced_today",
        "Chlorine Produced Today",
        lambda coordinator: coordinator.get_input(0x46),
        native_unit_of_measurement="g",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "electrolysis_time_today",
        "Electrolysis Time Today",
        lambda coordinator: coordinator.get_input(0x47),
        native_unit_of_measurement="min",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "total_electrolysis_hours",
        "Total Electrolysis Hours",
        lambda coordinator: coordinator.get_u32_input(0x48),
        native_unit_of_measurement="h",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "partial_electrolysis_hours",
        "Partial Electrolysis Hours",
        lambda coordinator: coordinator.get_u32_input(0x4A),
        native_unit_of_measurement="h",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "ph_pump_percentage",
        "PH Pump Percentage",
        lambda coordinator: coordinator.get_input(0x58),
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "ph_pump_total_hours",
        "PH Pump Total Hours",
        lambda coordinator: coordinator.get_input(0x5A),
        native_unit_of_measurement="h",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "ph_pump_partial_hours",
        "PH Pump Partial Hours",
        lambda coordinator: coordinator.get_input(0x5B),
        native_unit_of_measurement="h",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "cl_pump_percentage",
        "CL Pump Percentage",
        lambda coordinator: coordinator.get_input(0x88),
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    SensorDescription(
        "uv_total_lamp_hours",
        "UV Total Lamp Hours",
        lambda coordinator: coordinator.get_u32_input(0xD6),
        native_unit_of_measurement="h",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="uv",
    ),
    SensorDescription(
        "uv_current_lamp_hours",
        "UV Current Lamp Hours",
        lambda coordinator: coordinator.get_u32_input(0xD9),
        native_unit_of_measurement="h",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="uv",
    ),
    SensorDescription(
        "uv_total_ignitions",
        "UV Total Ignitions",
        lambda coordinator: coordinator.get_input(0xD5),
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="uv",
    ),
    SensorDescription(
        "uv_lamp_partial_ignitions",
        "UV Lamp Partial Ignitions",
        lambda coordinator: coordinator.get_input(0xD8),
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="uv",
    ),
    SensorDescription(
        "sunrise",
        "Sunrise",
        _packed_time(0xF0),
        icon="mdi:weather-sunset-up",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorDescription(
        "sunset",
        "Sunset",
        _packed_time(0xF1),
        icon="mdi:weather-sunset-down",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

BINARY_SENSOR_DESCRIPTIONS = (
    BinarySensorDescription(
        "electrolysis_running",
        "Electrolisys ON",
        lambda coordinator: coordinator.get_input_bit(0x40, 0),
    ),
    BinarySensorDescription(
        "water_flow_problem",
        "Water Flow Problem",
        lambda coordinator: coordinator.get_input_bit(0x24, 0),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    BinarySensorDescription(
        "ph_tank_alarm",
        "PH Tank Alarm",
        lambda coordinator: coordinator.get_input_bit(0x26, 5),
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    # Alarm words 0x25/0x27/0x28/0x29 arrive inside the 0x24-0x2A read, so
    # these cost no extra Modbus traffic. Each mask covers exactly the bits
    # the v1.63 register table marks as implemented.
    BinarySensorDescription(
        "electrolysis_alarm",
        "Electrolysis Alarm",
        # bit 0 check_cell, bit 1 low_conductivity, bit 2 high_conductivity
        _input_mask(0x25, 0b0000_0111),
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:flash-alert",
    ),
    BinarySensorDescription(
        "chlorine_alarm",
        "Chlorine Alarm",
        # bits 0-5 low/high ORP, PPM and probe mA; bits 6-9 tank, pumpstop,
        # blown fuse and pump maintenance
        _input_mask(0x27, 0b0011_1111_1111),
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:flask-outline",
    ),
    BinarySensorDescription(
        "temperature_alarm",
        "Temperature Alarm",
        # bit 0 low_temperature, bit 1 high_temperature
        _input_mask(0x28, 0b0000_0011),
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:thermometer-alert",
    ),
    BinarySensorDescription(
        "salt_alarm",
        "Salt Alarm",
        # bit 0 low_salt, bit 1 high_salt
        _input_mask(0x29, 0b0000_0011),
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:shaker-outline",
    ),
    BinarySensorDescription(
        "ph_tank_input",
        "PH Tank Input",
        lambda coordinator: coordinator.get_input_bit(0x56, 2),
        icon="mdi:bottle-tonic",
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    BinarySensorDescription(
        "ph_tank_detection_enabled",
        "PH Tank Detection Enabled",
        lambda coordinator: coordinator.get_holding_bit(0x56, 7),
        icon="mdi:bottle-tonic-plus-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        feature_group="diagnostic",
    ),
    BinarySensorDescription(
        "digital_input_1",
        "Digital Input 1",
        lambda coordinator: coordinator.get_input_bit(0x100, 0),
        feature_group="inputs",
    ),
    BinarySensorDescription(
        "digital_input_2",
        "Digital Input 2",
        lambda coordinator: coordinator.get_input_bit(0x100, 1),
        feature_group="inputs",
    ),
    BinarySensorDescription(
        "digital_input_3",
        "Digital Input 3",
        lambda coordinator: coordinator.get_input_bit(0x100, 2),
        feature_group="inputs",
    ),
    BinarySensorDescription(
        "digital_input_4",
        "Digital Input 4",
        lambda coordinator: coordinator.get_input_bit(0x100, 3),
        feature_group="inputs",
    ),
    BinarySensorDescription(
        "uv_available",
        "UV Available",
        lambda coordinator: coordinator.get_holding_bit(0x06, 6),
        feature_group="uv",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorDescription(
        "uv_enabled",
        "UV Enabled",
        lambda coordinator: coordinator.get_holding_bit(0x0D, 6),
        feature_group="uv",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorDescription(
        "uv_light",
        "UV Light",
        lambda coordinator: coordinator.get_input_bit(0xD4, 0),
        feature_group="uv",
    ),
    BinarySensorDescription(
        "uv_ballast_problem",
        "UV Ballast Problem",
        lambda coordinator: coordinator.get_input_bit(0x2A, 0),
        feature_group="uv",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorDescription(
        "uv_fuse_problem",
        "UV Fuse Problem",
        lambda coordinator: coordinator.get_input_bit(0x2A, 1),
        feature_group="uv",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorDescription(
        "pool_pump_state",
        "Pool Pump State",
        lambda coordinator: coordinator.get_relay_state("pool_pump"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorDescription(
        "relay_square_state",
        "Relay Square State",
        lambda coordinator: coordinator.get_relay_state("relay_square"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorDescription(
        "relay_triangle_state",
        "Relay Triangle State",
        lambda coordinator: coordinator.get_relay_state("relay_triangle"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorDescription(
        "pool_led_light_state",
        "Pool Led Light State",
        lambda coordinator: coordinator.get_relay_state("pool_led_light"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

NUMBER_DESCRIPTIONS = (
    NumberDescription(
        "target_ph",
        "Target PH",
        _scaled_holding(0x57, 0.01),
        write_address=0x57,
        min_value=7.00,
        max_value=7.80,
        step=0.01,
        multiplier=100,
        native_unit_of_measurement="pH",
        icon="mdi:ph",
    ),
    NumberDescription(
        "target_orp",
        "Target ORP",
        lambda coordinator: coordinator.get_holding(0x87),
        write_address=0x87,
        min_value=600,
        max_value=850,
        step=1,
        native_unit_of_measurement="mV",
        icon="mdi:gauge",
    ),
    NumberDescription(
        "target_free_chlorine",
        "Target Free Chlorine",
        _scaled_holding(0x88, 0.01),
        write_address=0x88,
        min_value=0.30,
        max_value=3.50,
        step=0.01,
        multiplier=100,
        native_unit_of_measurement="ppm",
        icon="mdi:flask-outline",
    ),
    NumberDescription(
        "target_electrolysis_production",
        "Target Electrolysis Production",
        lambda coordinator: coordinator.get_holding(0x41),
        write_address=0x41,
        min_value=0,
        max_value=100,
        step=1,
        native_unit_of_measurement="%",
        icon="mdi:water-percent",
    ),
)

BUTTON_DESCRIPTIONS = (
    ButtonDescription(
        "reset_partial_electrolysis_hours",
        "Reset Partial Electrolysis Hours",
        write_address=0x40,
        bit=14,
        icon="mdi:counter",
    ),
    ButtonDescription(
        "reset_ph_pumpstop",
        "Reset PH Pumpstop",
        write_address=0x56,
        bit=13,
        icon="mdi:pump-off",
    ),
    ButtonDescription(
        "reset_ph_tank_alarm",
        "Reset PH Tank Alarm",
        write_address=0x26,
        bit=5,
        icon="mdi:bottle-tonic-outline",
    ),
    ButtonDescription(
        "reset_ph_pump_partial_hours",
        "Reset PH Pump Partial Hours",
        write_address=0x56,
        bit=15,
        icon="mdi:pump",
    ),
    ButtonDescription(
        "reset_cl_pumpstop",
        "Reset CL Pumpstop",
        write_address=0x86,
        bit=13,
        icon="mdi:pump-off",
    ),
    ButtonDescription(
        "reset_ph_dose",
        "Restart PH Dose",
        write_address=0x56,
        bit=14,
        icon="mdi:restart",
    ),
    ButtonDescription(
        "reset_cl_dose",
        "Restart CL Dose",
        write_address=0x86,
        bit=14,
        icon="mdi:restart",
    ),
    ButtonDescription(
        "reset_uv_hours_ignitions",
        "Reset UV Hours And Ignitions",
        write_address=0xD0,
        bit=15,
        icon="mdi:lightbulb-auto",
    ),
)
