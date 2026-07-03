"""Debug sensor: last delivery result."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, signal_delivery
from .entity import HeroldEntity

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
    """Set up the sensor platform."""
    coordinator: HeroldCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HeroldLastDeliverySensor(coordinator)])


class HeroldLastDeliverySensor(HeroldEntity, SensorEntity):
    """Shows the channel(s) of the most recent delivery."""

    _attr_translation_key = "last_delivery"
    _attr_icon = "mdi:bell-outline"

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_last_delivery"

    @property
    def native_value(self) -> str:
        """Return the last channel(s) used, or 'none'."""
        result = self.coordinator.last_result
        if result is None or not result.channels_used:
            return "none"
        return ", ".join(result.channels_used)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose delivery details for debugging."""
        result = self.coordinator.last_result
        notification = self.coordinator.last_notification
        if result is None:
            return {}
        return {
            "notification_id": result.notification_id,
            "room": result.room_used,
            "timestamp": result.timestamp.isoformat(),
            "priority": notification.priority if notification else None,
            "errors": result.errors,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to delivery updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_delivery(self.coordinator.entry.entry_id),
                self._handle_delivery,
            )
        )

    @callback
    def _handle_delivery(self) -> None:
        self.async_write_ha_state()
