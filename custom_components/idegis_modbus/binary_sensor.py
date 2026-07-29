"""Binary sensor platform for Idegis Modbus."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_DIAGNOSTICS, CONF_ENABLE_INPUTS, CONF_ENABLE_UV
from .descriptions import BINARY_SENSOR_DESCRIPTIONS, BinarySensorDescription
from .entity import IdegisEntity


class IdegisBinarySensor(IdegisEntity, BinarySensorEntity):
    """Representation of an Idegis binary sensor."""

    _description: BinarySensorDescription

    def __init__(self, entry: ConfigEntry, description: BinarySensorDescription) -> None:
        coordinator = entry.runtime_data
        super().__init__(coordinator, entry, description.key, description.name)
        self._description = description
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def is_on(self) -> bool | None:
        """Return the current binary sensor state."""
        return self._description.value_fn(self.coordinator)


def _is_enabled(entry: ConfigEntry, description: BinarySensorDescription) -> bool:
    if description.feature_group == "inputs":
        return entry.options.get(CONF_ENABLE_INPUTS, True)
    if description.feature_group == "uv":
        return entry.options.get(CONF_ENABLE_UV, True)
    if description.entity_category is not None:
        return entry.options.get(CONF_ENABLE_DIAGNOSTICS, True)
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Idegis binary sensors."""
    entities = [
        IdegisBinarySensor(entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
        if _is_enabled(entry, description)
    ]
    async_add_entities(entities)
