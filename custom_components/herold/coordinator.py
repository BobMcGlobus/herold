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
from homeassistant.helpers import llm
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .channels import (
    BaseChannel,
    ChannelUnavailable,
    InternalChannel,
    PushChannel,
    TelegramChannel,
    TodoChannel,
    VoiceChannel,
)
from .const import (
    CHANNEL_INTERNAL,
    CHANNEL_PUSH,
    CHANNEL_TELEGRAM,
    CHANNEL_TODO,
    CHANNEL_VOICE,
    CONF_ENABLE_OFFLINE_FALLBACK,
    CONF_EXTERNAL_DND_ENTITY,
    CONF_FALLBACK_TTS,
    CONF_INTERNET_SENSOR,
    CONF_RECIPIENT,
    CONF_ROOMS,
    EVENT_DELIVERED,
    HISTORY_MAX_ENTRIES,
    P0_RATE_LIMIT_PER_HOUR,
    TODO_STATUS_DONE,
    TODO_STATUS_OPEN,
    signal_delivery,
    signal_dnd,
    signal_history,
    signal_todo,
)
from .dispatcher import DispatchContext, select_channels, should_deliver
from .llm_tools import HeroldAPI
from .models import DeliveryResult, DNDState, Notification, Query, Room
from .query_manager import QueryManager
from .rate_limiter import RateLimiter
from .room_router import select_room
from .scheduler import HeroldScheduler
from .store import HeroldStore

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

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
        self.scheduler = HeroldScheduler(self)
        self.rate_limiter = RateLimiter(self)
        self.last_result: DeliveryResult | None = None
        self.last_priority: int | None = None
        self._p0_timestamps: list[float] = []
        self._dnd_session_unsubs: list[Callable[[], None]] = []
        self._dnd_restored_from_session = False
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
            CHANNEL_INTERNAL: InternalChannel(),
            CHANNEL_TODO: TodoChannel(),
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
        await self.scheduler.async_setup()
        self._async_restore_dnd_session()

        self._unsubs.append(
            llm.async_register_api(self.hass, HeroldAPI(self.hass, self))
        )

    async def async_shutdown(self) -> None:
        """Detach listeners and flush the store on unload."""
        await self.scheduler.async_shutdown()
        await self.query_manager.async_shutdown()
        self.rate_limiter.shutdown()
        self._clear_dnd_session_listeners()
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
    def set_master_dnd(self, active: bool, from_session: bool = False) -> None:
        """Update the internal DND switch state and notify listeners."""
        if not from_session:
            # Manual toggle ends any running DND session
            self._clear_dnd_session_listeners()
            self.store.dnd_session = None
            self.store.async_schedule_save()
        self.dnd_state.master_active = active
        async_dispatcher_send(self.hass, signal_dnd(self.entry.entry_id))

    @property
    def dnd_restored_from_session(self) -> bool:
        """True if the boot-time session restore already decided the DND state."""
        return self._dnd_restored_from_session

    @property
    def dnd_session(self) -> dict[str, Any] | None:
        """Return the active DND session, if any."""
        return self.store.dnd_session

    async def async_dnd_session(
        self, until: datetime | None, until_home: bool
    ) -> None:
        """Activate DND with an automatic end condition."""
        self._clear_dnd_session_listeners()
        self.store.dnd_session = {
            "until": until.isoformat() if until else None,
            "until_home": until_home,
        }
        self.store.async_schedule_save()
        self.set_master_dnd(True, from_session=True)
        self._arm_dnd_session(until, until_home)

    @callback
    def _async_restore_dnd_session(self) -> None:
        """Re-arm a persisted DND session after a restart."""
        session = self.store.dnd_session
        if not session:
            return
        self._dnd_restored_from_session = True
        until_raw = session.get("until")
        until = dt_util.parse_datetime(until_raw) if until_raw else None
        until_home = bool(session.get("until_home"))
        if until and until <= dt_util.utcnow():
            self._end_dnd_session()
            return
        self.dnd_state.master_active = True
        self._arm_dnd_session(until, until_home)

    @callback
    def _arm_dnd_session(
        self, until: datetime | None, until_home: bool
    ) -> None:
        if until:

            async def _expire(_now: datetime) -> None:
                self._end_dnd_session()

            self._dnd_session_unsubs.append(
                async_track_point_in_time(self.hass, _expire, until)
            )
        recipient = self.config.get(CONF_RECIPIENT)
        if until_home and recipient:

            @callback
            def _person_changed(event: Event[EventStateChangedData]) -> None:
                new_state = event.data["new_state"]
                if new_state is not None and new_state.state == STATE_HOME:
                    self._end_dnd_session()

            self._dnd_session_unsubs.append(
                async_track_state_change_event(
                    self.hass, [recipient], _person_changed
                )
            )

    @callback
    def _end_dnd_session(self) -> None:
        self._clear_dnd_session_listeners()
        self.store.dnd_session = None
        self.store.async_schedule_save()
        self.set_master_dnd(False, from_session=True)
        _LOGGER.debug("DND session ended")

    @callback
    def _clear_dnd_session_listeners(self) -> None:
        for unsub in self._dnd_session_unsubs:
            unsub()
        self._dnd_session_unsubs.clear()

    @callback
    def note_delivery(self, result: DeliveryResult, priority: int) -> None:
        """Record the most recent delivery for the debug sensor."""
        self.last_result = result
        self.last_priority = priority

    @callback
    def add_history(self, kind: str, summary: str, **extra: Any) -> None:
        """Prepend an entry to the history ring buffer."""
        entry: dict[str, Any] = {
            "when": dt_util.utcnow().isoformat(),
            "kind": kind,
            "summary": summary[:160],
        }
        entry.update({key: value for key, value in extra.items() if value})
        history = self.store.history
        history.insert(0, entry)
        del history[HISTORY_MAX_ENTRIES:]
        self.store.async_schedule_save()
        async_dispatcher_send(self.hass, signal_history(self.entry.entry_id))

    @callback
    def p0_allowed(self) -> bool:
        """Anti-runaway rate limit for P0 internal triggers (rolling hour)."""
        now = dt_util.utcnow().timestamp()
        self._p0_timestamps = [
            stamp for stamp in self._p0_timestamps if now - stamp < 3600
        ]
        if len(self._p0_timestamps) >= P0_RATE_LIMIT_PER_HOUR:
            return False
        self._p0_timestamps.append(now)
        return True

    # -- Todo inbox (backing storage for todo.herold_inbox) -----------------

    @callback
    def async_add_todo_item(
        self, uid: str, summary: str, description: str | None = None
    ) -> None:
        """Add (or replace) an inbox item."""
        items = self.store.todo_items
        items[:] = [item for item in items if item.get("uid") != uid]
        items.append(
            {
                "uid": uid,
                "summary": summary,
                "status": TODO_STATUS_OPEN,
                "description": description,
                "created_at": dt_util.utcnow().isoformat(),
            }
        )
        self._todo_changed()

    @callback
    def async_update_todo_item(
        self,
        uid: str | None,
        summary: str | None = None,
        status: str | None = None,
        description: str | None = None,
    ) -> bool:
        """Update an inbox item; returns False if unknown."""
        for item in self.store.todo_items:
            if item.get("uid") == uid:
                if summary is not None:
                    item["summary"] = summary
                if status is not None:
                    item["status"] = status
                item["description"] = description
                self._todo_changed()
                return True
        return False

    @callback
    def async_complete_todo_item(self, uid: str) -> bool:
        """Mark an open inbox item as done; returns False if unknown."""
        for item in self.store.todo_items:
            if item.get("uid") == uid and item.get("status") == TODO_STATUS_OPEN:
                item["status"] = TODO_STATUS_DONE
                self._todo_changed()
                return True
        return False

    @callback
    def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete inbox items."""
        drop = set(uids)
        items = self.store.todo_items
        items[:] = [item for item in items if item.get("uid") not in drop]
        self._todo_changed()

    @callback
    def _todo_changed(self) -> None:
        self.store.async_schedule_save()
        async_dispatcher_send(self.hass, signal_todo(self.entry.entry_id))

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
            result.reason = reason
            self.note_delivery(result, notification.priority)
            self.add_history(
                "dropped",
                notification.message,
                priority=notification.priority,
                reason=reason,
            )
            async_dispatcher_send(self.hass, signal_delivery(self.entry.entry_id))
            return result

        allowed, limit_reason = self.rate_limiter.check(notification)
        if not allowed:
            _LOGGER.debug(
                "Rate limiter held notification %s: %s",
                notification.id,
                limit_reason,
            )
            result.reason = limit_reason
            self.note_delivery(result, notification.priority)
            self.add_history(
                "rate_limited",
                notification.message,
                priority=notification.priority,
                reason=limit_reason,
            )
            async_dispatcher_send(self.hass, signal_delivery(self.entry.entry_id))
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
        self.add_history(
            "delivered",
            notification.message,
            priority=notification.priority,
            channels=result.channels_used,
            room=result.room_used,
            errors=result.errors or None,
        )
        async_dispatcher_send(self.hass, signal_delivery(self.entry.entry_id))
        return result

    async def async_ask(self, query: Query) -> DeliveryResult:
        """Run the dispatch pipeline for a query."""
        return await self.query_manager.async_ask(query)
