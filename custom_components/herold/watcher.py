"""State-triggered reminders: "erinnere mich, wenn die Haustür aufgeht".

A watch is the scheduler's sibling — same payload, same persistence, but
armed with a state listener instead of a timer. Watches are one-shot by
default and carry a TTL so a forgotten trigger does not fire months later.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ID,
    EVENT_EXPIRED,
    EVENT_WATCH_ARMED,
    EVENT_WATCH_TRIGGERED,
    signal_watch,
)
from .models import Notification, Watch

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)

_IGNORED_STATES = ("unknown", "unavailable")


class HeroldWatcher:
    """Owns state-triggered reminders and their listener."""

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator
        self.watches: dict[str, Watch] = {}
        self._unsub: Callable[[], None] | None = None
        self._unsub_expiry: Callable[[], None] | None = None

    async def async_setup(self) -> None:
        """Restore watches from the store, dropping expired ones."""
        now = dt_util.utcnow()
        for raw in list(self.coordinator.store.watches.values()):
            watch = Watch.from_dict(raw)
            if watch.expires_at and watch.expires_at <= now:
                self._forget(watch.id)
                self.coordinator.hass.bus.async_fire(
                    EVENT_EXPIRED, {ATTR_ID: watch.id, "reason": "watch_ttl"}
                )
                continue
            self.watches[watch.id] = watch
        self._rearm()
        self._notify_change()

    async def async_shutdown(self) -> None:
        """Detach the state listener."""
        self._detach()

    @property
    def active(self) -> list[Watch]:
        """Return all armed watches, oldest first."""
        return sorted(self.watches.values(), key=lambda watch: watch.created_at)

    async def async_add(self, watch: Watch) -> None:
        """Persist and arm a new watch."""
        state = self.coordinator.hass.states.get(watch.entity_id)
        if state is not None and not watch.friendly_name:
            watch.friendly_name = state.attributes.get("friendly_name")

        self.watches[watch.id] = watch
        self.coordinator.store.watches[watch.id] = watch.to_dict()
        self.coordinator.store.async_schedule_save()
        self._rearm()

        self.coordinator.hass.bus.async_fire(
            EVENT_WATCH_ARMED,
            {
                ATTR_ID: watch.id,
                "entity_id": watch.entity_id,
                "condition": watch.describe(),
            },
        )
        self.coordinator.add_history(
            "watch_armed",
            str(watch.payload.get("message") or ""),
            condition=watch.describe(),
        )
        _LOGGER.debug("Watch %s armed: %s", watch.id, watch.describe())
        self._notify_change()

    async def async_cancel(self, watch_id: str) -> bool:
        """Cancel a watch; returns False if unknown."""
        if watch_id not in self.watches:
            return False
        self._forget(watch_id)
        self._rearm()
        _LOGGER.debug("Watch %s cancelled", watch_id)
        self._notify_change()
        return True

    def _forget(self, watch_id: str) -> None:
        self.watches.pop(watch_id, None)
        self.coordinator.store.watches.pop(watch_id, None)
        self.coordinator.store.async_schedule_save()

    def _detach(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    def _rearm(self) -> None:
        """Listen to exactly the entities that currently have watches."""
        self._detach()
        entity_ids = sorted({watch.entity_id for watch in self.watches.values()})
        if not entity_ids:
            return
        self._unsub = async_track_state_change_event(
            self.coordinator.hass, entity_ids, self._async_state_changed
        )

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        if new_state is None or new_state.state in _IGNORED_STATES:
            return
        old = event.data["old_state"]
        old_value = (
            old.state if old is not None and old.state not in _IGNORED_STATES
            else None
        )
        entity_id = event.data["entity_id"]
        now = dt_util.utcnow()

        for watch in list(self.watches.values()):
            if watch.entity_id != entity_id:
                continue
            if watch.expires_at and watch.expires_at <= now:
                self._forget(watch.id)
                self.coordinator.hass.bus.async_fire(
                    EVENT_EXPIRED, {ATTR_ID: watch.id, "reason": "watch_ttl"}
                )
                continue
            if watch.matches(old_value, new_state.state):
                self.coordinator.hass.async_create_task(
                    self._async_fire(watch, new_state.state)
                )

    async def _async_fire(self, watch: Watch, state: str) -> None:
        """Run the watch payload through the normal pipeline."""
        if watch.once:
            self._forget(watch.id)
            self._rearm()

        self.coordinator.hass.bus.async_fire(
            EVENT_WATCH_TRIGGERED,
            {
                ATTR_ID: watch.id,
                "entity_id": watch.entity_id,
                "state": state,
                "condition": watch.describe(),
            },
        )
        _LOGGER.debug(
            "Watch %s triggered by %s = %s", watch.id, watch.entity_id, state
        )
        notification = Notification.from_dict({**watch.payload, "id": watch.id})
        await self.coordinator.async_send(notification)
        self._notify_change()

    @callback
    def _notify_change(self) -> None:
        async_dispatcher_send(
            self.coordinator.hass, signal_watch(self.coordinator.entry.entry_id)
        )


def ttl_to_expiry(ttl_hours: int | None) -> datetime | None:
    """Convert a TTL in hours to an absolute expiry (None = never)."""
    if not ttl_hours:
        return None
    return dt_util.utcnow() + timedelta(hours=ttl_hours)
