"""Binary sensors: internet connectivity mirror and effective DND state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_INTERNET_SENSOR, DOMAIN, signal_dnd, signal_query
from .entity import HeroldEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import Event, EventStateChangedData, HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import HeroldCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: HeroldCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HeroldOnlineBinarySensor(coordinator),
            HeroldDNDActiveBinarySensor(coordinator),
            HeroldAnyPendingBinarySensor(coordinator),
        ]
    )


class HeroldOnlineBinarySensor(HeroldEntity, BinarySensorEntity):
    """Mirrors the configured internet detection sensor."""

    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_online"

    @property
    def is_on(self) -> bool:
        """Return True while the internet connection is up."""
        return self.coordinator.internet_available

    async def async_added_to_hass(self) -> None:
        """Follow the source sensor."""
        await super().async_added_to_hass()
        source = self.coordinator.config.get(CONF_INTERNET_SENSOR)
        if source:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [source], self._handle_source_change
                )
            )

    @callback
    def _handle_source_change(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()


class HeroldDNDActiveBinarySensor(HeroldEntity, BinarySensorEntity):
    """Effective DND state: internal switch OR external entity."""

    _attr_translation_key = "dnd_active"
    _attr_icon = "mdi:bell-off-outline"

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_dnd_active"

    @property
    def is_on(self) -> bool:
        """Return the merged DND state."""
        return self.coordinator.is_dnd_active()

    async def async_added_to_hass(self) -> None:
        """Subscribe to DND updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_dnd(self.coordinator.entry.entry_id),
                self._handle_dnd_update,
            )
        )

    @callback
    def _handle_dnd_update(self) -> None:
        self.async_write_ha_state()


class HeroldAnyPendingBinarySensor(HeroldEntity, BinarySensorEntity):
    """On while at least one query waits for an answer."""

    _attr_translation_key = "any_pending"
    _attr_icon = "mdi:comment-question-outline"

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_any_pending"

    @property
    def is_on(self) -> bool:
        """Return True if any query is pending."""
        return bool(self.coordinator.query_manager.pending)

    async def async_added_to_hass(self) -> None:
        """Subscribe to query updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_query(self.coordinator.entry.entry_id),
                self._handle_query_update,
            )
        )

    @callback
    def _handle_query_update(self) -> None:
        self.async_write_ha_state()
