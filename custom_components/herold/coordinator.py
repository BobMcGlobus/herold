"""Central state holder for the Herold integration.

Not a DataUpdateCoordinator — Herold does not poll. The coordinator owns the
configured rooms, the channel instances, the merged DND state, the store and
the query manager, and runs the dispatch pipeline for outgoing notifications.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_HOME, STATE_ON
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .channels import (
    BaseChannel,
    ChannelUnavailable,
    PushChannel,
    TelegramChannel,
    VoiceChannel,
)
from .const import (
    CHANNEL_PUSH,
    CHANNEL_TELEGRAM,
    CHANNEL_VOICE,
    CONF_ENABLE_OFFLINE_FALLBACK,
    CONF_EXTERNAL_DND_ENTITY,
    CONF_FALLBACK_TTS,
    CONF_INTERNET_SENSOR,
    CONF_RECIPIENT,
    CONF_ROOMS,
    EVENT_DELIVERED,
    signal_delivery,
    signal_dnd,
)
from .dispatcher import DispatchContext, select_channels, should_deliver
from .models import DeliveryResult, DNDState, Notification, Query, Room
from .query_manager import QueryManager
from .room_router import select_room
from .store import HeroldStore

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HeroldCoordinator:
    """Owns configuration, rooms, channels, store and the dispatch pipeline."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config: dict[str, Any] = {**entry.data, **entry.options}
        self.rooms: list[Room] = []
        self.channels: dict[str, BaseChannel] = {}
        self.dnd_state = DNDState()
        self.store = HeroldStore(hass, entry.entry_id)
        self.query_manager = QueryManager(self)
        self.last_result: DeliveryResult | None = None
        self.last_priority: int | None = None
        self._unsubs: list[Callable[[], None]] = []

    async def async_setup(self) -> None:
        """Load store and rooms, initialize channels, attach listeners."""
        await self.store.async_load()
        self.rooms = [Room.from_dict(raw) for raw in self.config.get(CONF_ROOMS, [])]

        voice_offline_capable = bool(
            self.config.get(CONF_ENABLE_OFFLINE_FALLBACK)
            and self.config.get(CONF_FALLBACK_TTS)
        )
        self.channels = {
            CHANNEL_VOICE: VoiceChannel(offline_capable=voice_offline_capable),
            CHANNEL_PUSH: PushChannel(),
            CHANNEL_TELEGRAM: TelegramChannel(),
        }

        external = self.config.get(CONF_EXTERNAL_DND_ENTITY)
        if external:
            self.dnd_state.external_active = self.hass.states.is_state(
                external, STATE_ON
            )
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, [external], self._async_external_dnd_changed
                )
            )

        occupancy_entities = sorted(
            {
                entity_id
                for room in self.rooms
                for entity_id in room.occupancy_entities
            }
        )
        if occupancy_entities:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, occupancy_entities, self._async_occupancy_changed
                )
            )

        await self.query_manager.async_setup()

    async def async_shutdown(self) -> None:
        """Detach listeners and flush the store on unload."""
        await self.query_manager.async_shutdown()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self.store.async_flush()

    @property
    def internet_available(self) -> bool:
        """Return True if the configured internet sensor reports online."""
        sensor = self.config.get(CONF_INTERNET_SENSOR)
        if not sensor:
            return True
        return self.hass.states.is_state(sensor, STATE_ON)

    @property
    def is_home(self) -> bool:
        """Return True if the configured recipient person is home."""
        recipient = self.config.get(CONF_RECIPIENT)
        if not recipient:
            return True
        return self.hass.states.is_state(recipient, STATE_HOME)

    def is_dnd_active(self) -> bool:
        """Return the merged DND state (internal switch OR external entity)."""
        return self.dnd_state.effective

    @callback
    def set_master_dnd(self, active: bool) -> None:
        """Update the internal DND switch state and notify listeners."""
        self.dnd_state.master_active = active
        async_dispatcher_send(self.hass, signal_dnd(self.entry.entry_id))

    @callback
    def note_delivery(self, result: DeliveryResult, priority: int) -> None:
        """Record the most recent delivery for the debug sensor."""
        self.last_result = result
        self.last_priority = priority

    @callback
    def _async_external_dnd_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        new_state = event.data["new_state"]
        self.dnd_state.external_active = (
            new_state is not None and new_state.state == STATE_ON
        )
        async_dispatcher_send(self.hass, signal_dnd(self.entry.entry_id))

    @callback
    def _async_occupancy_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Track room activations for conflict resolution and fallback."""
        new_state = event.data["new_state"]
        if new_state is None or new_state.state != STATE_ON:
            return
        entity_id = event.data["entity_id"]
        now = dt_util.utcnow()
        for room in self.rooms:
            if entity_id in room.occupancy_entities:
                self.store.room_last_activation[room.name] = now
                self.store.last_known_room = room.name
                self.store.last_room_activity = now
        self.store.async_schedule_save()

    async def async_get_active_room(self) -> Room | None:
        """Return the room voice output should go to, if any."""
        return select_room(self)

    async def async_get_channel(self, name: str) -> BaseChannel:
        """Return a channel by name."""
        return self.channels[name]

    async def async_send(self, notification: Notification) -> DeliveryResult:
        """Run the full dispatch pipeline for one notification."""
        ctx = DispatchContext(
            coordinator=self,
            is_home=self.is_home,
            is_dnd=self.is_dnd_active(),
            internet_available=self.internet_available,
        )
        result = DeliveryResult(notification_id=notification.id)

        deliver, reason = should_deliver(notification, ctx)
        if not deliver:
            _LOGGER.debug("Dropping notification %s: %s", notification.id, reason)
            return result

        active_room = await self.async_get_active_room()
        for channel in select_channels(notification, ctx):
            try:
                await channel.deliver(notification, self)
            except ChannelUnavailable as err:
                result.errors[channel.name] = str(err)
                _LOGGER.debug(
                    "Channel %s unavailable for %s: %s",
                    channel.name,
                    notification.id,
                    err,
                )
            except HomeAssistantError as err:
                result.errors[channel.name] = str(err)
                _LOGGER.warning(
                    "Delivery via %s failed for %s: %s",
                    channel.name,
                    notification.id,
                    err,
                )
            else:
                result.channels_used.append(channel.name)
                room_name = (
                    active_room.name
                    if channel.name == CHANNEL_VOICE and active_room
                    else None
                )
                if room_name:
                    result.room_used = room_name
                self.hass.bus.async_fire(
                    EVENT_DELIVERED,
                    {
                        "id": notification.id,
                        "channel": channel.name,
                        "room": room_name,
                        "priority": notification.priority,
                    },
                )

        self.note_delivery(result, notification.priority)
        async_dispatcher_send(self.hass, signal_delivery(self.entry.entry_id))
        return result

    async def async_ask(self, query: Query) -> DeliveryResult:
        """Run the dispatch pipeline for a query."""
        return await self.query_manager.async_ask(query)
