"""Alarm clock: scheduling, the ring loop and getting-up verification.

Three things make this more than a repeating notification:

* **Urgency profiles** decide how stubborn an alarm is — ring spacing, how
  often it retries, how fast the volume climbs and how many snoozes it
  grants before it refuses to be quiet.
* **Getting-up verification** uses the bed sensor: a dismiss while still
  lying down is treated as a reflex, and the alarm resumes.
* **A pre-alarm phase** brings lights up long before the sound and the
  blinds shortly before it, because waking out of light sleep beats being
  startled out of deep sleep.
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any, Final

from homeassistant.const import STATE_ON
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import (
    ALARM_STATUS_ARMED,
    ALARM_STATUS_DONE,
    ALARM_STATUS_RINGING,
    ALARM_STATUS_SNOOZED,
    ALARM_STATUS_VERIFYING,
    ATTR_ID,
    CONF_ALARM_COVER_LEAD_MINUTES,
    CONF_ALARM_LIGHT_LEAD_MINUTES,
    CONF_ALARM_SICK_ENTITY,
    CONF_ALARM_SNOOZE_MINUTES,
    CONF_ALARM_VERIFY_DISMISS,
    CONF_ALARM_VERIFY_SECONDS,
    CONF_ALARM_WORKDAY_SENSOR,
    DEFAULT_ALARM_COVER_LEAD_MINUTES,
    DEFAULT_ALARM_LIGHT_LEAD_MINUTES,
    DEFAULT_ALARM_MESSAGE,
    DEFAULT_ALARM_SNOOZE_MINUTES,
    DEFAULT_ALARM_VERIFY_DISMISS,
    DEFAULT_ALARM_VERIFY_SECONDS,
    EVENT_ALARM_DISMISSED,
    EVENT_ALARM_PRE,
    EVENT_ALARM_SET,
    EVENT_ALARM_SKIPPED,
    EVENT_ALARM_SNOOZED,
    EVENT_ALARM_TRIGGERED,
    signal_alarm,
)
from .models import Alarm

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)


# Optional alarm fields the editor may empty out again.
_CLEARABLE_ALARM_FIELDS: Final = frozenset(
    {
        "label",
        "key",
        "routine",
        "sound",
        "sound_media_type",
        "target",
        "valid_until",
    }
)


class AlarmManager:
    """Owns alarm entries, their timers and the ringing loop."""

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator
        self.alarms: dict[str, Alarm] = {}
        self._timers: dict[str, list[Callable[[], None]]] = {}

    async def async_setup(self) -> None:
        """Restore alarms, drop expired ones and re-arm their timers."""
        for raw in list(self.coordinator.store.alarms.values()):
            alarm = Alarm.from_dict(raw)
            if alarm.is_expired:
                self.coordinator.store.alarms.pop(alarm.id, None)
                continue
            # A restart mid-ring stops the loop; re-arm for the next time.
            if alarm.status in (
                ALARM_STATUS_RINGING,
                ALARM_STATUS_SNOOZED,
                ALARM_STATUS_VERIFYING,
            ):
                alarm.status = ALARM_STATUS_ARMED
                alarm.rings = 0
                alarm.snoozes = 0
            self.alarms[alarm.id] = alarm
            self._reschedule(alarm)
        self.coordinator.store.async_schedule_save()
        self._notify_change()

    async def async_shutdown(self) -> None:
        """Cancel all timers."""
        for cancels in self._timers.values():
            for cancel in cancels:
                cancel()
        self._timers.clear()

    # -- Queries -----------------------------------------------------------

    @property
    def all_alarms(self) -> list[Alarm]:
        """Every alarm, enabled or not, next one first."""
        far_future = dt_util.utcnow() + timedelta(days=3650)
        return sorted(
            self.alarms.values(),
            key=lambda alarm: alarm.next_trigger or far_future,
        )

    @property
    def active(self) -> list[Alarm]:
        """Enabled alarms, next one first."""
        return [alarm for alarm in self.all_alarms if alarm.enabled]

    @property
    def next_alarm(self) -> Alarm | None:
        """The alarm that fires next, if any."""
        upcoming = [
            alarm for alarm in self.active if alarm.next_trigger is not None
        ]
        return upcoming[0] if upcoming else None

    @property
    def ringing(self) -> Alarm | None:
        """The currently ringing alarm, if any."""
        return next(
            (
                alarm
                for alarm in self.alarms.values()
                if alarm.status in (ALARM_STATUS_RINGING, ALARM_STATUS_VERIFYING)
            ),
            None,
        )

    # -- Mutations ---------------------------------------------------------

    async def async_add(self, alarm: Alarm) -> Alarm:
        """Store and arm an alarm, replacing one with the same key.

        The key lets an automation own an alarm: running it twice updates
        the entry instead of piling up duplicates.
        """
        if alarm.next_occurrence() is None:
            raise HomeAssistantError(
                f"Alarm time {alarm.time!r} is not a valid time of day"
            )
        if alarm.key:
            for existing in list(self.alarms.values()):
                if existing.key == alarm.key and existing.id != alarm.id:
                    await self.async_cancel(existing.id)

        self.alarms[alarm.id] = alarm
        self._reschedule(alarm)
        self.coordinator.hass.bus.async_fire(
            EVENT_ALARM_SET,
            {
                ATTR_ID: alarm.id,
                "time": alarm.time,
                "days": alarm.days,
                "label": alarm.label,
                "key": alarm.key,
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

    async def async_update(self, alarm_id: str, changes: dict[str, Any]) -> Alarm:
        """Apply field changes and re-arm; used by the card's editor."""
        alarm = self.alarms.get(alarm_id)
        if alarm is None:
            raise HomeAssistantError(f"Unknown alarm id: {alarm_id}")
        for name, value in changes.items():
            if value is None or not hasattr(alarm, name):
                continue
            # The card sends "" for an optional field the user emptied —
            # without this, a routine or an expiry could never be removed
            # again, only replaced.
            if value == "":
                if name in _CLEARABLE_ALARM_FIELDS:
                    value = None
                elif name == "message":
                    # An emptied wake message means "use the default again",
                    # not "wake me in silence".
                    value = DEFAULT_ALARM_MESSAGE
            setattr(alarm, name, value)
        if alarm.next_occurrence() is None:
            raise HomeAssistantError(
                f"Alarm time {alarm.time!r} is not a valid time of day"
            )
        # Editing an alarm always starts a fresh cycle.
        alarm.rings = 0
        alarm.snoozes = 0
        if alarm.status in (ALARM_STATUS_DONE, ALARM_STATUS_SNOOZED):
            alarm.status = ALARM_STATUS_ARMED
        self._reschedule(alarm)
        _LOGGER.debug("Alarm %s updated: %s", alarm.id, alarm.describe())
        self._notify_change()
        return alarm

    async def async_cancel(self, alarm_id: str) -> bool:
        """Remove an alarm entirely; returns False if unknown."""
        if alarm_id not in self.alarms:
            return False
        self._cancel_timers(alarm_id)
        self.alarms.pop(alarm_id, None)
        self.coordinator.store.alarms.pop(alarm_id, None)
        self.coordinator.store.async_schedule_save()
        _LOGGER.debug("Alarm %s cancelled", alarm_id)
        self._notify_change()
        return True

    async def async_skip_next(self, alarm_id: str) -> Alarm:
        """Skip one occurrence of a repeating alarm without deleting it."""
        alarm = self.alarms.get(alarm_id)
        if alarm is None:
            raise HomeAssistantError(f"Unknown alarm id: {alarm_id}")
        if not alarm.is_repeating:
            raise HomeAssistantError(
                "Only repeating alarms can skip an occurrence — cancel the "
                "one-shot instead"
            )
        alarm.skip_next = True
        self._reschedule(alarm)
        self.coordinator.hass.bus.async_fire(
            EVENT_ALARM_SKIPPED, {ATTR_ID: alarm.id, "reason": "requested"}
        )
        _LOGGER.debug("Alarm %s will skip its next occurrence", alarm.id)
        self._notify_change()
        return alarm

    async def async_snooze(
        self, alarm_id: str | None = None, minutes: int | None = None
    ) -> Alarm:
        """Snooze the ringing alarm, honouring the urgency budget."""
        alarm = self._resolve(alarm_id)
        base = minutes or int(
            self.coordinator.config.get(
                CONF_ALARM_SNOOZE_MINUTES, DEFAULT_ALARM_SNOOZE_MINUTES
            )
        )
        delay = alarm.snooze_minutes(base)
        if delay is None:
            _LOGGER.debug("Alarm %s refused a snooze (budget spent)", alarm.id)
            raise HomeAssistantError(
                "Kein Schlummern mehr übrig — dieser Wecker besteht darauf, "
                "dass du aufstehst"
            )

        alarm.snoozes += 1
        alarm.status = ALARM_STATUS_SNOOZED
        alarm.next_trigger = dt_util.utcnow() + timedelta(minutes=delay)
        self._cancel_timers(alarm.id)
        self._arm_ring_timer(alarm)
        self._persist(alarm)
        self.coordinator.hass.bus.async_fire(
            EVENT_ALARM_SNOOZED,
            {ATTR_ID: alarm.id, "minutes": delay, "snoozes_used": alarm.snoozes},
        )
        self.coordinator.add_history(
            "alarm_snoozed", alarm.label or alarm.describe(), minutes=delay
        )
        _LOGGER.debug("Alarm %s snoozed for %s min", alarm.id, delay)
        self._notify_change()
        return alarm

    async def async_dismiss(
        self, alarm_id: str | None = None, verified: bool = False
    ) -> Alarm:
        """Stop the alarm — but only if the user actually got up.

        A dismiss while the bed sensor still reports occupancy is a reflex,
        not a decision, so the alarm goes into a short grace period and
        resumes if nothing changed.
        """
        alarm = self._resolve(alarm_id)

        if not verified and self._verification_wanted() and self.coordinator.in_bed:
            alarm.status = ALARM_STATUS_VERIFYING
            self._cancel_timers(alarm.id)
            self._arm_verify_timer(alarm)
            self._persist(alarm)
            _LOGGER.debug(
                "Alarm %s dismissed while still in bed — verifying", alarm.id
            )
            self._notify_change()
            return alarm

        await self._async_finish(alarm)
        return alarm

    async def _async_finish(self, alarm: Alarm) -> None:
        """Really end the alarm: routine, then reschedule or clean up."""
        alarm.rings = 0
        alarm.snoozes = 0
        self._cancel_timers(alarm.id)
        await self.coordinator.alarm_output.async_routine(alarm)

        if alarm.is_repeating and not alarm.is_expired:
            alarm.status = ALARM_STATUS_ARMED
            self._reschedule(alarm)
        else:
            # One-shots and expired temporary alarms remove themselves
            # instead of lingering as dead rows in the list.
            self.alarms.pop(alarm.id, None)
            self.coordinator.store.alarms.pop(alarm.id, None)
            self.coordinator.store.async_schedule_save()

        self.coordinator.hass.bus.async_fire(
            EVENT_ALARM_DISMISSED, {ATTR_ID: alarm.id}
        )
        self.coordinator.add_history(
            "alarm_dismissed", alarm.label or alarm.describe()
        )
        _LOGGER.debug("Alarm %s dismissed", alarm.id)
        self._notify_change()

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

    # -- Blocking ----------------------------------------------------------

    def is_blocked(self, alarm: Alarm) -> str | None:
        """Return a reason if a work alarm must not ring today.

        Only alarms flagged ``workday_only`` are affected — a temporary or
        explicitly set alarm still rings on a holiday, which is usually the
        whole point of setting one.
        """
        if not alarm.workday_only:
            return None
        config = self.coordinator.config
        states = self.coordinator.hass.states

        sick = config.get(CONF_ALARM_SICK_ENTITY)
        if sick and states.is_state(sick, STATE_ON):
            return "sick day"

        workday = config.get(CONF_ALARM_WORKDAY_SENSOR)
        if workday:
            state = states.get(workday)
            if state is not None and state.state != STATE_ON:
                return "not a workday"
        return None

    # -- Scheduling --------------------------------------------------------

    def _reschedule(self, alarm: Alarm) -> None:
        """Compute the next occurrence and arm every timer around it."""
        self._cancel_timers(alarm.id)
        if not alarm.enabled or alarm.status == ALARM_STATUS_DONE:
            alarm.next_trigger = None
            self._persist(alarm)
            return

        moment = alarm.next_occurrence()
        if moment is not None and alarm.skip_next:
            # Look past the skipped occurrence so the sensor shows the real
            # next ring rather than one that will not happen.
            moment = alarm.next_occurrence(after=moment)
        alarm.next_trigger = moment
        self._persist(alarm)
        if moment is None:
            return
        self._arm_ring_timer(alarm)
        self._arm_pre_timers(alarm)

    def _add_timer(self, alarm_id: str, cancel: Callable[[], None]) -> None:
        self._timers.setdefault(alarm_id, []).append(cancel)

    def _cancel_timers(self, alarm_id: str) -> None:
        for cancel in self._timers.pop(alarm_id, []):
            cancel()

    def _arm_ring_timer(self, alarm: Alarm) -> None:
        if alarm.next_trigger is None:
            return

        async def _fire(_now: datetime) -> None:
            await self._async_ring(alarm)

        self._add_timer(
            alarm.id,
            async_track_point_in_time(
                self.coordinator.hass, _fire, alarm.next_trigger
            ),
        )

    def _arm_pre_timers(self, alarm: Alarm) -> None:
        """Arm the sunrise phase: lights early, blinds shortly before."""
        if alarm.next_trigger is None:
            return
        config = self.coordinator.config
        now = dt_util.utcnow()

        for lead_key, default, kind in (
            (
                CONF_ALARM_LIGHT_LEAD_MINUTES,
                DEFAULT_ALARM_LIGHT_LEAD_MINUTES,
                "lights",
            ),
            (
                CONF_ALARM_COVER_LEAD_MINUTES,
                DEFAULT_ALARM_COVER_LEAD_MINUTES,
                "covers",
            ),
        ):
            lead = int(config.get(lead_key, default))
            if lead <= 0:
                continue
            moment = alarm.next_trigger - timedelta(minutes=lead)
            if moment <= now:
                continue

            async def _fire(_now: datetime, kind: str = kind) -> None:
                await self._async_pre_alarm(alarm, kind)

            self._add_timer(
                alarm.id,
                async_track_point_in_time(self.coordinator.hass, _fire, moment),
            )

    def _arm_verify_timer(self, alarm: Alarm) -> None:
        delay = int(
            self.coordinator.config.get(
                CONF_ALARM_VERIFY_SECONDS, DEFAULT_ALARM_VERIFY_SECONDS
            )
        )

        async def _fire(_now: Any) -> None:
            await self._async_verify_dismiss(alarm)

        self._add_timer(
            alarm.id, async_call_later(self.coordinator.hass, delay, _fire)
        )

    def _verification_wanted(self) -> bool:
        return bool(
            self.coordinator.config.get(
                CONF_ALARM_VERIFY_DISMISS, DEFAULT_ALARM_VERIFY_DISMISS
            )
        )

    # -- Firing ------------------------------------------------------------

    async def _async_pre_alarm(self, alarm: Alarm, kind: str) -> None:
        """Run one stage of the sunrise phase."""
        if not alarm.enabled or self.is_blocked(alarm):
            return
        _LOGGER.debug("Alarm %s pre-phase: %s", alarm.id, kind)
        try:
            if kind == "lights":
                room = await self.coordinator.async_get_alarm_room()
                await self.coordinator.alarm_output.async_lights(room)
            else:
                await self.coordinator.alarm_output.async_covers()
        except Exception:
            _LOGGER.exception("Alarm %s pre-phase %s failed", alarm.id, kind)
        self.coordinator.hass.bus.async_fire(
            EVENT_ALARM_PRE, {ATTR_ID: alarm.id, "stage": kind}
        )

    async def _async_verify_dismiss(self, alarm: Alarm) -> None:
        """Decide whether that dismiss meant getting up."""
        if alarm.status != ALARM_STATUS_VERIFYING:
            return
        if self.coordinator.in_bed:
            _LOGGER.debug("Alarm %s: still in bed, resuming", alarm.id)
            alarm.status = ALARM_STATUS_RINGING
            self._persist(alarm)
            await self._async_ring(alarm)
            return
        await self._async_finish(alarm)

    async def _async_ring(self, alarm: Alarm) -> None:
        """Ring once and schedule the next ring until dismissed."""
        if not alarm.enabled:
            return

        if alarm.skip_next:
            alarm.skip_next = False
            _LOGGER.debug("Alarm %s skipped on request", alarm.id)
            self._reschedule(alarm)
            self._notify_change()
            return

        if reason := self.is_blocked(alarm):
            _LOGGER.debug("Alarm %s skipped: %s", alarm.id, reason)
            self.coordinator.hass.bus.async_fire(
                EVENT_ALARM_SKIPPED, {ATTR_ID: alarm.id, "reason": reason}
            )
            self.coordinator.add_history(
                "alarm_skipped", alarm.label or alarm.describe(), reason=reason
            )
            self._reschedule(alarm)
            self._notify_change()
            return

        if alarm.is_expired:
            await self.async_cancel(alarm.id)
            return

        max_rings = int(alarm.profile["max_rings"])
        if alarm.rings >= max_rings:
            _LOGGER.debug("Alarm %s gave up after %s rings", alarm.id, alarm.rings)
            await self._async_finish(alarm)
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
                    "urgency": alarm.urgency,
                },
            )
            self.coordinator.add_history(
                "alarm_triggered", alarm.label or alarm.message
            )

        try:
            played = await self.coordinator.alarm_output.async_ring(
                alarm, alarm.rings
            )
            if not played:
                _LOGGER.warning(
                    "Alarm %s has no speaker — configure an alarm room or "
                    "speaker in the options",
                    alarm.id,
                )
                await self.coordinator.async_alarm_push(alarm.message)
        except Exception:
            # One failed ring must not end the alarm — the next is armed
            # below and may well succeed.
            _LOGGER.exception("Alarm %s could not ring", alarm.id)

        # Someone may have dismissed or snoozed while we were playing.
        if alarm.status != ALARM_STATUS_RINGING:
            return
        alarm.next_trigger = dt_util.utcnow() + timedelta(
            seconds=int(alarm.profile["interval"])
        )
        self._cancel_timers(alarm.id)
        self._arm_ring_timer(alarm)
        self._persist(alarm)
        self._notify_change()

    def _persist(self, alarm: Alarm) -> None:
        self.coordinator.store.alarms[alarm.id] = alarm.to_dict()
        self.coordinator.store.async_schedule_save()

    @callback
    def _notify_change(self) -> None:
        async_dispatcher_send(
            self.coordinator.hass, signal_alarm(self.coordinator.entry.entry_id)
        )
