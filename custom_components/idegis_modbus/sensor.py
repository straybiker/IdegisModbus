"""Sensor platform for Idegis Modbus."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_DIAGNOSTICS, CONF_ENABLE_UV
from .descriptions import SENSOR_DESCRIPTIONS, SensorDescription
from .entity import IdegisEntity


class IdegisSensor(IdegisEntity, SensorEntity):
    """Representation of an Idegis sensor."""

    _description: SensorDescription

    def __init__(
        self,
        entry: ConfigEntry,
        description: SensorDescription,
    ) -> None:
        coordinator = entry.runtime_data
        super().__init__(coordinator, entry, description.key, description.name)
        self._description = description
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default

    @property
    def native_value(self):
        """Return the current sensor value."""
        return self._description.value_fn(self.coordinator)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Idegis sensors."""
    include_diagnostics = entry.options.get(CONF_ENABLE_DIAGNOSTICS, True)
    include_uv = entry.options.get(CONF_ENABLE_UV, True)
    entities = [
        IdegisSensor(entry, description)
        for description in SENSOR_DESCRIPTIONS
        if (include_diagnostics or description.entity_category is None)
        and (include_uv or description.feature_group != "uv")
    ]
    async_add_entities(entities)
