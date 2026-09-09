"""Config flow for Idegis Modbus."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TIMEOUT
from homeassistant.data_entry_flow import FlowResult

from .client import IdegisModbusClient, IdegisModbusError
from .const import (
    CONF_ENABLE_BUTTONS,
    CONF_ENABLE_DIAGNOSTICS,
    CONF_ENABLE_INPUTS,
    CONF_ENABLE_UV,
    CONF_MESSAGE_WAIT_MS,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_ENABLE_BUTTONS,
    DEFAULT_ENABLE_DIAGNOSTICS,
    DEFAULT_ENABLE_INPUTS,
    DEFAULT_ENABLE_UV,
    DEFAULT_MESSAGE_WAIT_MS,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

LOGGER = logging.getLogger(__name__)

# Bounded so a bad value cannot flood the RS-485 bus or stall every poll.
PORT_RANGE = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))
SLAVE_RANGE = vol.All(vol.Coerce(int), vol.Range(min=1, max=247))
TIMEOUT_RANGE = vol.All(vol.Coerce(int), vol.Range(min=1, max=60))
MESSAGE_WAIT_RANGE = vol.All(vol.Coerce(int), vol.Range(min=0, max=5000))
SCAN_INTERVAL_RANGE = vol.All(vol.Coerce(int), vol.Range(min=5, max=3600))


def _user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Build the config flow schema."""
    user_input = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=user_input.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
            vol.Required(
                CONF_PORT, default=user_input.get(CONF_PORT, DEFAULT_PORT)
            ): PORT_RANGE,
            vol.Required(
                CONF_SLAVE, default=user_input.get(CONF_SLAVE, DEFAULT_SLAVE)
            ): SLAVE_RANGE,
            vol.Required(
                CONF_TIMEOUT, default=user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
            ): TIMEOUT_RANGE,
            vol.Required(
                CONF_MESSAGE_WAIT_MS,
                default=user_input.get(CONF_MESSAGE_WAIT_MS, DEFAULT_MESSAGE_WAIT_MS),
            ): MESSAGE_WAIT_RANGE,
        }
    )


def _unique_id(data: dict[str, Any]) -> str:
    """Build the entry unique id from the connection details."""
    return f"{data[CONF_HOST]}:{data[CONF_PORT]}:{data[CONF_SLAVE]}"


def _options_schema(options: dict[str, Any] | None = None) -> vol.Schema:
    """Build the options schema."""
    options = options or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): SCAN_INTERVAL_RANGE,
            vol.Required(
                CONF_ENABLE_UV, default=options.get(CONF_ENABLE_UV, DEFAULT_ENABLE_UV)
            ): bool,
            vol.Required(
                CONF_ENABLE_INPUTS,
                default=options.get(CONF_ENABLE_INPUTS, DEFAULT_ENABLE_INPUTS),
            ): bool,
            vol.Required(
                CONF_ENABLE_DIAGNOSTICS,
                default=options.get(
                    CONF_ENABLE_DIAGNOSTICS, DEFAULT_ENABLE_DIAGNOSTICS
                ),
            ): bool,
            vol.Required(
                CONF_ENABLE_BUTTONS,
                default=options.get(CONF_ENABLE_BUTTONS, DEFAULT_ENABLE_BUTTONS),
            ): bool,
        }
    )


async def _validate_connection(data: dict[str, Any]) -> None:
    """Validate user-supplied connection details."""
    client = IdegisModbusClient(
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        slave=data[CONF_SLAVE],
        timeout=data[CONF_TIMEOUT],
        message_wait_ms=data[CONF_MESSAGE_WAIT_MS],
    )
    try:
        await client.async_connect()
        await client.async_read_input_registers(0x40, 1)
    finally:
        await client.async_close()


class IdegisModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Idegis Modbus."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(_unique_id(user_input))
            self._abort_if_unique_id_configured()
            try:
                await _validate_connection(user_input)
            except IdegisModbusError as err:
                LOGGER.debug("Connection validation failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                LOGGER.exception("Unexpected error validating the Idegis connection")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_ENABLE_UV: DEFAULT_ENABLE_UV,
                        CONF_ENABLE_INPUTS: DEFAULT_ENABLE_INPUTS,
                        CONF_ENABLE_DIAGNOSTICS: DEFAULT_ENABLE_DIAGNOSTICS,
                        CONF_ENABLE_BUTTONS: DEFAULT_ENABLE_BUTTONS,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfigure flow."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        assert entry is not None

        errors: dict[str, str] = {}
        defaults = {**entry.data, CONF_NAME: entry.title}

        if user_input is not None:
            unique_id = _unique_id(user_input)
            collides = any(
                other.entry_id != entry.entry_id and other.unique_id == unique_id
                for other in self.hass.config_entries.async_entries(DOMAIN)
            )
            if collides:
                errors["base"] = "already_configured"
            else:
                try:
                    await _validate_connection(user_input)
                except IdegisModbusError as err:
                    LOGGER.debug("Connection validation failed: %s", err)
                    errors["base"] = "cannot_connect"
                except Exception:
                    LOGGER.exception(
                        "Unexpected error validating the Idegis connection"
                    )
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(unique_id)
                    self.hass.config_entries.async_update_entry(
                        entry,
                        title=user_input[CONF_NAME],
                        data=user_input,
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(defaults),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "IdegisModbusOptionsFlow":
        """Create the options flow."""
        return IdegisModbusOptionsFlow(config_entry)


class IdegisModbusOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Idegis Modbus."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(dict(self._config_entry.options)),
        )

