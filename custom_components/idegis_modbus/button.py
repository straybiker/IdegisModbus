"""Button platform for Idegis Modbus."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_BUTTONS
from .descriptions import BUTTON_DESCRIPTIONS, ButtonDescription
from .entity import IdegisEntity


class IdegisButton(IdegisEntity, ButtonEntity):
    """Representation of an Idegis maintenance button."""

    _description: ButtonDescription

    def __init__(self, entry: ConfigEntry, description: ButtonDescription) -> None:
        coordinator = entry.runtime_data
        super().__init__(coordinator, entry, description.key, description.name)
        self._description = description
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category

    async def async_press(self) -> None:
        """Press the maintenance button."""
        await self.coordinator.async_press_button(
            self._description.write_address,
            self._description.bit,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Idegis buttons."""
    if not entry.options.get(CONF_ENABLE_BUTTONS, True):
        return
    async_add_entities([IdegisButton(entry, description) for description in BUTTON_DESCRIPTIONS])

