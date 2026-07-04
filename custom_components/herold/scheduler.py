"""Deferred notifications: herold.schedule and herold.remind_self.

Schedules persist in the store and are re-armed on boot. Deliveries missed
while Home Assistant was down still fire within SCHEDULE_GRACE_MINUTES;
older ones are marked expired.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import re
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ID,
    ATTR_SCHEDULED_FOR,
    EVENT_EXPIRED,
    EVENT_SCHEDULED,
    SCHEDULE_GRACE_MINUTES,
    signal_schedule,
)
from .models import Notification, Schedule

if TYPE_CHECKING:
    from collections.abc import Callable

    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)

_DURATION_RE = re.compile(r"(\d+)\s*([dhms])")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_DURATION_UNITS = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}


def parse_when(value: str) -> datetime:
    """Parse a schedule time: '+1h30m', '18:00' or an ISO datetime.

    Returns an aware UTC datetime. Plain times resolve to the next
    occurrence in local time (today, or tomorrow if already past).
    """
    raw = value.strip()

    if raw.startswith("+"):
        matches = _DURATION_RE.findall(raw[1:])
        if not matches:
            raise HomeAssistantError(f"Cannot parse duration: {value!r}")
        delta = timedelta(
            **{_DURATION_UNITS[unit]: int(amount) for amount, unit in matches}
        )
        if delta <= timedelta(0):
            raise HomeAssistantError(f"Duration must be positive: {value!r}")
        return dt_util.utcnow() + delta

    if _TIME_RE.match(raw):
        parsed_time = dt_util.parse_time(raw)
        if parsed_time is None:
            raise HomeAssistantError(f"Cannot parse time: {value!r}")
        local_now = dt_util.now()
        candidate = local_now.replace(
            hour=parsed_time.hour,
            minute=parsed_time.minute,
            second=parsed_time.second,
            microsecond=0,
        )
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return dt_util.as_utc(candidate)

    parsed = dt_util.parse_datetime(raw)
    if parsed is None:
        raise HomeAssistantError(f"Cannot parse datetime: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return dt_util.as_utc(parsed)


class HeroldScheduler:
    """Owns deferred notifications and their timers."""

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator
        self.schedules: dict[str, Schedule] = {}
        self._timers: dict[str, Callable[[], None]] = {}

    async def async_setup(self) -> None:
        """Restore schedules from the store; fire or expire missed ones."""
        grace = timedelta(minutes=SCHEDULE_GRACE_MINUTES)
        now = dt_util.utcnow()
        for raw in list(self.coordinator.store.schedules.values()):
            schedule = Schedule.from_dict(raw)
            self.schedules[schedule.id] = schedule
            if schedule.scheduled_for > now:
                self._arm_timer(schedule)
            elif now - schedule.scheduled_for <= grace:
                _LOGGER.debug(
                    "Schedule %s missed during downtime; firing within grace",
                    schedule.id,
                )
                await self._async_fire(schedule)
            else:
                self._drop(schedule)
                self.coordinator.hass.bus.async_fire(
                    EVENT_EXPIRED, {ATTR_ID: schedule.id, "reason": "missed"}
                )
                _LOGGER.debug("Schedule %s expired (missed too long)", schedule.id)
        self._notify_change()

    async def async_shutdown(self) -> None:
        """Cancel all timers."""
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()

    @property
    def pending(self) -> list[Schedule]:
        """Return all schedules, soonest first."""
        return sorted(
            self.schedules.values(), key=lambda item: item.scheduled_for
        )

    async def async_add(self, schedule: Schedule) -> None:
        """Persist and arm a new schedule."""
        self.schedules[schedule.id] = schedule
        self.coordinator.store.schedules[schedule.id] = schedule.to_dict()
        self.coordinator.store.async_schedule_save()
        self._arm_timer(schedule)
        self.coordinator.hass.bus.async_fire(
            EVENT_SCHEDULED,
            {
                ATTR_ID: schedule.id,
                ATTR_SCHEDULED_FOR: schedule.scheduled_for.isoformat(),
            },
        )
        _LOGGER.debug(
            "Scheduled %s for %s", schedule.id, schedule.scheduled_for
        )
        self.coordinator.add_history(
            "scheduled",
            str(schedule.payload.get("message") or ""),
            at=schedule.scheduled_for.isoformat(),
            priority=schedule.payload.get("priority"),
        )
        self._notify_change()

    async def async_cancel(self, schedule_id: str) -> bool:
        """Cancel a schedule; returns False if unknown."""
        schedule = self.schedules.get(schedule_id)
        if schedule is None:
            return False
        self._drop(schedule)
        _LOGGER.debug("Schedule %s cancelled", schedule_id)
        self._notify_change()
        return True

    def _arm_timer(self, schedule: Schedule) -> None:
        async def _fire(_now: datetime) -> None:
            self._timers.pop(schedule.id, None)
            await self._async_fire(schedule)
            self._notify_change()

        self._timers[schedule.id] = async_track_point_in_time(
            self.coordinator.hass, _fire, schedule.scheduled_for
        )

    async def _async_fire(self, schedule: Schedule) -> None:
        """Run the deferred notification through the normal pipeline."""
        self._drop(schedule)
        notification = Notification.from_dict(
            {**schedule.payload, "id": schedule.id}
        )
        await self.coordinator.async_send(notification)

    def _drop(self, schedule: Schedule) -> None:
        self.schedules.pop(schedule.id, None)
        cancel = self._timers.pop(schedule.id, None)
        if cancel:
            cancel()
        self.coordinator.store.schedules.pop(schedule.id, None)
        self.coordinator.store.async_schedule_save()

    @callback
    def _notify_change(self) -> None:
        async_dispatcher_send(
            self.coordinator.hass,
            signal_schedule(self.coordinator.entry.entry_id),
        )
