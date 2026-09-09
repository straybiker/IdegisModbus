"""Constants for the Idegis Modbus integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DOMAIN: Final = "idegis_modbus"
MANUFACTURER: Final = "Idegis"
MODEL: Final = "Domotic 2 LS"
DEFAULT_NAME: Final = "Idegis Pool"

CONF_MESSAGE_WAIT_MS: Final = "message_wait_ms"
CONF_SLAVE: Final = "slave"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_ENABLE_UV: Final = "enable_uv"
CONF_ENABLE_INPUTS: Final = "enable_inputs"
CONF_ENABLE_DIAGNOSTICS: Final = "enable_diagnostics"
CONF_ENABLE_BUTTONS: Final = "enable_buttons"

DEFAULT_PORT: Final = 4196
DEFAULT_SLAVE: Final = 1
DEFAULT_TIMEOUT: Final = 2
DEFAULT_SCAN_INTERVAL: Final = 15
DEFAULT_MESSAGE_WAIT_MS: Final = 100
DEFAULT_ENABLE_UV: Final = True
DEFAULT_ENABLE_INPUTS: Final = True
DEFAULT_ENABLE_DIAGNOSTICS: Final = True
DEFAULT_ENABLE_BUTTONS: Final = True

PLATFORMS: Final = [
    "binary_sensor",
    "button",
    "number",
    "sensor",
    "switch",
]

SERVICE_FORCE_REFRESH: Final = "force_refresh"


@dataclass(frozen=True, slots=True)
class RegisterBlock:
    """A contiguous block of registers to fetch."""

    start: int
    count: int


INPUT_BLOCKS: Final = (
    # 0x24-0x2A is the contiguous alarm region documented in the v1.63 register
    # table: Flow, Electrolysis, PH, CL, Temp, Salt, UV reset. One read instead
    # of three. 0x25 and 0x27-0x29 are implemented but not yet exposed.
    RegisterBlock(0x24, 7),
    RegisterBlock(0x40, 14),
    RegisterBlock(0x51, 1),
    RegisterBlock(0x56, 6),
    RegisterBlock(0x81, 3),
    RegisterBlock(0x86, 6),
    RegisterBlock(0xB1, 1),
    RegisterBlock(0xC1, 1),
    RegisterBlock(0xD4, 8),
    RegisterBlock(0xF0, 2),
    RegisterBlock(0x100, 1),
    RegisterBlock(0x110, 7),
)

# Every block costs one Modbus round trip plus one message_wait_ms gap, so
# merge where possible. Only merge across addresses the v1.63 register table
# documents as implemented: a range covering an unimplemented register can be
# rejected with an ILLEGAL DATA ADDRESS exception, failing the whole read.
HOLDING_BLOCKS: Final = (
    RegisterBlock(0x06, 1),
    RegisterBlock(0x0D, 1),
    RegisterBlock(0x41, 2),
    RegisterBlock(0x56, 2),
    RegisterBlock(0x87, 2),
)

OUTPUT_SWITCH_REGISTERS: Final = {
    "pool_pump": 0x110,
    "relay_square": 0x118,
    "relay_triangle": 0x120,
    "pool_led_light": 0x128,
}

OUTPUT_STATE_INPUT_REGISTERS: Final = {
    "pool_pump": 0x110,
    "relay_square": 0x112,
    "relay_triangle": 0x114,
    "pool_led_light": 0x116,
}
