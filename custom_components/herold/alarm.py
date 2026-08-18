"""Alarm clock built on the existing delivery machinery.

An alarm is a repeating P4 announcement that has to be dismissed rather than
a fire-and-forget notification. Ringing ramps the room volume up over
successive rings, flashes the room's alarm lights and gives up after
``alarm_max_rings`` so a missed alarm does not run forever.

Snooze re-arms the ring loop; dismiss ends it and — for repeating alarms —
schedules the next weekday occurrence.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import (
    ALARM_RAMP,
    ALARM_RING_INTERVAL_SECONDS,
    ALARM_STATUS_ARMED,
    ALARM_STATUS_DONE,
    ALARM_STATUS_RINGING,
    ALARM_STATUS_SNOOZED,
    ATTR_ID,
    CONF_ALARM_MAX_RINGS,
    CONF_ALARM_SNOOZE_MINUTES,
    DEFAULT_ALARM_MAX_RINGS,
    DEFAULT_ALARM_SNOOZE_MINUTES,
    EVENT_ALARM_DISMISSED,
    EVENT_ALARM_SET,
    EVENT_ALARM_SNOOZED,
    EVENT_ALARM_TRIGGERED,
    PRIORITY_ALARM,
    VOLUME_LOUD,
    signal_alarm,
)
from .models import Alarm

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)


class AlarmManager:
    """Owns alarm entries, their timers and the ringing loop."""

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator
        self.alarms: dict[str, Alarm] = {}
        self._timers: dict[str, Callable[[], None]] = {}

    async def async_setup(self) -> None:
        """Restore alarms and re-arm their timers."""
        for raw in list(self.coordinator.store.alarms.values()):
            alarm = Alarm.from_dict(raw)
            # A restart during ringing stops the loop; re-arm for next time.
            if alarm.status in (ALARM_STATUS_RINGING, ALARM_STATUS_SNOOZED):
                alarm.status = ALARM_STATUS_ARMED
                alarm.rings = 0
            self.alarms[alarm.id] = alarm
            self._reschedule(alarm)
        self._notify_change()

    async def async_shutdown(self) -> None:
        """Cancel all timers."""
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    @property
    def active(self) -> list[Alarm]:
        """Return enabled alarms, next one first."""
        return sorted(
            (alarm for alarm in self.alarms.values() if alarm.enabled),
            key=lambda alarm: alarm.next_trigger or dt_util.utcnow(),
        )

    @property
    def next_alarm(self) -> Alarm | None:
        """Return the alarm that fires next, if any."""
        upcoming = [
            alarm for alarm in self.active if alarm.next_trigger is not None
        ]
        return upcoming[0] if upcoming else None

    @property
    def ringing(self) -> Alarm | None:
        """Return the currently ringing alarm, if any."""
        return next(
            (
                alarm
                for alarm in self.alarms.values()
                if alarm.status == ALARM_STATUS_RINGING
            ),
            None,
        )

    async def async_add(self, alarm: Alarm) -> Alarm:
        """Store and arm a new alarm."""
        if alarm.next_occurrence() is None:
            raise HomeAssistantError(
                f"Alarm time {alarm.time!r} is not a valid time of day"
            )
        self.alarms[alarm.id] = alarm
        self._reschedule(alarm)
        self.coordinator.hass.bus.async_fire(
            EVENT_ALARM_SET,
            {
                ATTR_ID: alarm.id,
                "time": alarm.time,
                "days": alarm.days,
                "label": alarm.label,
                "next_trigger": (
                    alarm.next_trigger.isoformat() if alarm.next_trigger else None
                ),
            },
        )
        self.coordinator.add_history(
            "alarm_set", alarm.label or alarm.describe(), when=alarm.describe()
        )
        _LOGGER.debug("Alarm %s set: %s", alarm.id, alarm.describe())
        self._notify_change()
        return alarm

    async def async_cancel(self, alarm_id: str) -> bool:
        """Remove an alarm entirely; returns False if unknown."""
        if alarm_id not in self.alarms:
            return False
        self._cancel_timer(alarm_id)
        self.alarms.pop(alarm_id, None)
        self.coordinator.store.alarms.pop(alarm_id, None)
        self.coordinator.store.async_schedule_save()
        _LOGGER.debug("Alarm %s cancelled", alarm_id)
        self._notify_change()
        return True

    async def async_snooze(
        self, alarm_id: str | None = None, minutes: int | None = None
    ) -> Alarm:
        """Snooze the ringing alarm (or a named one)."""
        alarm = self._resolve(alarm_id)
        delay = minutes or self.coordinator.config.get(
            CONF_ALARM_SNOOZE_MINUTES, DEFAULT_ALARM_SNOOZE_MINUTES
        )
        alarm.status = ALARM_STATUS_SNOOZED
        alarm.next_trigger = dt_util.utcnow() + timedelta(minutes=delay)
        self._arm_timer(alarm)
        self._persist(alarm)
        self.coordinator.hass.bus.async_fire(
            EVENT_ALARM_SNOOZED, {ATTR_ID: alarm.id, "minutes": delay}
        )
        self.coordinator.add_history(
            "alarm_snoozed", alarm.label or alarm.describe(), minutes=delay
        )
        _LOGGER.debug("Alarm %s snoozed for %s min", alarm.id, delay)
        self._notify_change()
        return alarm

    async def async_dismiss(self, alarm_id: str | None = None) -> Alarm:
        """Stop the ringing alarm and arm the next occurrence."""
        alarm = self._resolve(alarm_id)
        alarm.rings = 0
        self._cancel_timer(alarm.id)
        if alarm.is_repeating:
            alarm.status = ALARM_STATUS_ARMED
            self._reschedule(alarm)
        else:
            alarm.status = ALARM_STATUS_DONE
            alarm.next_trigger = None
            self._persist(alarm)
        self.coordinator.hass.bus.async_fire(
            EVENT_ALARM_DISMISSED, {ATTR_ID: alarm.id}
        )
        self.coordinator.add_history(
            "alarm_dismissed", alarm.label or alarm.describe()
        )
        _LOGGER.debug("Alarm %s dismissed", alarm.id)
        self._notify_change()
        return alarm

    def _resolve(self, alarm_id: str | None) -> Alarm:
        if alarm_id:
            alarm = self.alarms.get(alarm_id)
            if alarm is None:
                raise HomeAssistantError(f"Unknown alarm id: {alarm_id}")
            return alarm
        ringing = self.ringing
        if ringing is None:
            raise HomeAssistantError("No alarm is currently ringing")
        return ringing

    # -- Scheduling ---------------------------------------------------------

    def _reschedule(self, alarm: Alarm) -> None:
        """Compute and arm the next occurrence of an alarm."""
        if not alarm.enabled or alarm.status == ALARM_STATUS_DONE:
            alarm.next_trigger = None
            self._persist(alarm)
            return
        alarm.next_trigger = alarm.next_occurrence()
        self._persist(alarm)
        if alarm.next_trigger is not None:
            self._arm_timer(alarm)

    def _arm_timer(self, alarm: Alarm) -> None:
        self._cancel_timer(alarm.id)
        if alarm.next_trigger is None:
            return

        async def _fire(_now: datetime) -> None:
            self._timers.pop(alarm.id, None)
            await self._async_ring(alarm)

        self._timers[alarm.id] = async_track_point_in_time(
            self.coordinator.hass, _fire, alarm.next_trigger
        )

    def _cancel_timer(self, alarm_id: str) -> None:
        cancel = self._timers.pop(alarm_id, None)
        if cancel:
            cancel()

    # -- Ringing ------------------------------------------------------------

    async def _async_ring(self, alarm: Alarm) -> None:
        """Ring once and schedule the next ring until dismissed."""
        if not alarm.enabled:
            return
        max_rings = self.coordinator.config.get(
            CONF_ALARM_MAX_RINGS, DEFAULT_ALARM_MAX_RINGS
        )
        if alarm.rings >= max_rings:
            _LOGGER.debug(
                "Alarm %s gave up after %s rings", alarm.id, alarm.rings
            )
            await self.async_dismiss(alarm.id)
            return

        first_ring = alarm.rings == 0
        alarm.status = ALARM_STATUS_RINGING
        alarm.rings += 1
        self._persist(alarm)

        if first_ring:
            self.coordinator.hass.bus.async_fire(
                EVENT_ALARM_TRIGGERED,
                {
                    ATTR_ID: alarm.id,
                    "label": alarm.label,
                    "time": alarm.time,
                },
            )
            self.coordinator.add_history(
                "alarm_triggered", alarm.label or alarm.message
            )

        try:
            await self.coordinator.async_ring_alarm(
                message=alarm.message,
                ramp=self._ramp_factor(alarm.rings),
                priority=PRIORITY_ALARM,
                volume_level=VOLUME_LOUD,
                flash=first_ring,
            )
        except Exception:
            # One failed ring must not end the alarm — the next one is armed
            # below and may well succeed (speaker back online, TTS reachable).
            _LOGGER.exception("Alarm %s could not ring", alarm.id)

        # Next ring, unless the user dismissed/snoozed while we were speaking.
        if alarm.status != ALARM_STATUS_RINGING:
            return
        alarm.next_trigger = dt_util.utcnow() + timedelta(
            seconds=ALARM_RING_INTERVAL_SECONDS
        )
        self._arm_timer(alarm)
        self._persist(alarm)
        self._notify_change()

    @staticmethod
    def _ramp_factor(ring: int) -> float:
        """Return the volume factor for this ring (gentle start, louder later)."""
        index = min(max(ring - 1, 0), len(ALARM_RAMP) - 1)
        return ALARM_RAMP[index]

    def _persist(self, alarm: Alarm) -> None:
        self.coordinator.store.alarms[alarm.id] = alarm.to_dict()
        self.coordinator.store.async_schedule_save()

    @callback
    def _notify_change(self) -> None:
        async_dispatcher_send(
            self.coordinator.hass, signal_alarm(self.coordinator.entry.entry_id)
        )
