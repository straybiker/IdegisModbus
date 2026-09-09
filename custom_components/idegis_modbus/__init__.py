"""The Idegis Modbus integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .client import IdegisModbusClient
from .const import (
    CONF_MESSAGE_WAIT_MS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_FORCE_REFRESH,
)
from .coordinator import IdegisModbusCoordinator

LOGGER = logging.getLogger(__name__)

type IdegisConfigEntry = ConfigEntry[IdegisModbusCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from yaml (not supported)."""
    hass.data.setdefault(DOMAIN, {})

    async def async_force_refresh(call: ServiceCall) -> None:
        # Only loaded entries have runtime_data. Touching an entry that failed
        # to set up raises AttributeError and kills the whole service call.
        entries: list[IdegisConfigEntry] = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise HomeAssistantError("No loaded Idegis Modbus entries")

        for entry in entries:
            await entry.runtime_data.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_FORCE_REFRESH):
        hass.services.async_register(
            DOMAIN,
            SERVICE_FORCE_REFRESH,
            async_force_refresh,
            schema=vol.Schema({}),
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: IdegisConfigEntry) -> bool:
    """Set up Idegis Modbus from a config entry."""
    client = IdegisModbusClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        slave=entry.data["slave"],
        timeout=entry.data[CONF_TIMEOUT],
        message_wait_ms=entry.data[CONF_MESSAGE_WAIT_MS],
    )

    coordinator = IdegisModbusCoordinator(
        hass,
        client,
        name=entry.title,
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # A failed setup never reaches async_unload_entry, so close the socket
        # here. HA retries setup on a backoff and would otherwise leak one
        # connection per attempt.
        await client.async_close()
        raise

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IdegisConfigEntry) -> bool:
    """Unload an Idegis Modbus entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_close()
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: IdegisConfigEntry) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
