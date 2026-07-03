"""Test button for the Herold integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity

from .const import DOMAIN, PRIORITY_NORMAL, TEST_NOTIFICATION_MESSAGE
from .entity import HeroldEntity
from .models import Notification

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import HeroldCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    coordinator: HeroldCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HeroldTestButton(coordinator)])


class HeroldTestButton(HeroldEntity, ButtonEntity):
    """Sends a P2 test notification through the full dispatch pipeline."""

    _attr_translation_key = "test"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_test"

    async def async_press(self) -> None:
        """Send the test notification."""
        notification = Notification(
            message=TEST_NOTIFICATION_MESSAGE, priority=PRIORITY_NORMAL
        )
        await self.coordinator.async_send(notification)
