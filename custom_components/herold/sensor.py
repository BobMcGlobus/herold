"""Sensors: last delivery (debug), pending query count, last query."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, signal_delivery, signal_query
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
    async_add_entities(
        [
            HeroldLastDeliverySensor(coordinator),
            HeroldPendingCountSensor(coordinator),
            HeroldLastQuerySensor(coordinator),
        ]
    )


class HeroldSignalSensor(HeroldEntity, SensorEntity):
    """Base for sensors that refresh on a dispatcher signal."""

    _signal: staticmethod

    async def async_added_to_hass(self) -> None:
        """Subscribe to the relevant signal."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                type(self)._signal(self.coordinator.entry.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class HeroldLastDeliverySensor(HeroldSignalSensor):
    """Shows the channel(s) of the most recent delivery."""

    _attr_translation_key = "last_delivery"
    _attr_icon = "mdi:bell-outline"
    _signal = staticmethod(signal_delivery)

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
        if result is None:
            return {}
        return {
            "notification_id": result.notification_id,
            "room": result.room_used,
            "timestamp": result.timestamp.isoformat(),
            "priority": self.coordinator.last_priority,
            "errors": result.errors,
        }


class HeroldPendingCountSensor(HeroldSignalSensor):
    """Number of queries waiting for an answer."""

    _attr_translation_key = "pending_count"
    _attr_icon = "mdi:comment-question-outline"
    _attr_native_unit_of_measurement = "queries"
    _signal = staticmethod(signal_query)

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_pending_count"

    @property
    def native_value(self) -> int:
        """Return the number of pending queries."""
        return len(self.coordinator.query_manager.pending)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """List the pending queries."""
        return {
            "queries": [
                {
                    "id": query.id,
                    "question": query.question,
                    "mode": query.mode,
                    "priority": query.priority,
                    "created_at": query.created_at.isoformat(),
                }
                for query in self.coordinator.query_manager.pending
            ]
        }


class HeroldLastQuerySensor(HeroldSignalSensor):
    """The most recent query with its full lifecycle state."""

    _attr_translation_key = "last_query"
    _attr_icon = "mdi:comment-question"
    _signal = staticmethod(signal_query)

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_last_query"

    @property
    def native_value(self) -> str:
        """Return the question text (state max length safe)."""
        query = self.coordinator.query_manager.last_query
        if query is None:
            return "none"
        return query.question[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the query lifecycle details."""
        query = self.coordinator.query_manager.last_query
        if query is None:
            return {}
        return {
            "id": query.id,
            "mode": query.mode,
            "choices": query.choices,
            "priority": query.priority,
            "status": query.status,
            "answer": query.answer,
            "answered_via": query.answered_via,
            "created_at": query.created_at.isoformat(),
            "timeout_at": query.timeout_at.isoformat(),
            "channels_delivered": query.channels_delivered,
        }
