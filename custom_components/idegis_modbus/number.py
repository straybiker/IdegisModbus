"""Number platform for Idegis Modbus."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .descriptions import NUMBER_DESCRIPTIONS, NumberDescription
from .entity import IdegisEntity


class IdegisNumber(IdegisEntity, NumberEntity):
    """Representation of an Idegis writable number."""

    _description: NumberDescription

    def __init__(self, entry: ConfigEntry, description: NumberDescription) -> None:
        coordinator = entry.runtime_data
        super().__init__(coordinator, entry, description.key, description.name)
        self._description = description
        self._attr_native_min_value = description.min_value
        self._attr_native_max_value = description.max_value
        self._attr_native_step = description.step
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_icon = description.icon

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        value = self._description.value_fn(self.coordinator)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write the target register."""
        register_value = round(value * self._description.multiplier)
        await self.coordinator.async_set_holding_value(
            self._description.write_address, int(register_value)
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Idegis numbers."""
    async_add_entities([IdegisNumber(entry, description) for description in NUMBER_DESCRIPTIONS])

