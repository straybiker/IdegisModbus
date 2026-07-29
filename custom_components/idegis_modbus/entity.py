"""Entity helpers for Idegis Modbus."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import IdegisModbusCoordinator


class IdegisEntity(CoordinatorEntity[IdegisModbusCoordinator]):
    """Base entity for Idegis Modbus."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IdegisModbusCoordinator,
        entry: ConfigEntry,
        unique_key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_key}"
        self._attr_name = name
        self._attr_entity_registry_visible_default = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=self._entry.title,
            configuration_url=f"http://{self._entry.data['host']}:{self._entry.data['port']}",
        )

