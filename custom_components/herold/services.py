"""Service handlers for the Herold integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    ATTR_ABOVE,
    ATTR_ANNOUNCE,
    ATTR_ANSWER,
    ATTR_BELOW,
    ATTR_CALLBACK_EVENT,
    ATTR_CHOICES,
    ATTR_DAYS,
    ATTR_DEFAULT_ANSWER,
    ATTR_ENABLED,
    ATTR_ENTITY_ID,
    ATTR_ESCALATION,
    ATTR_FROM_STATE,
    ATTR_ID,
    ATTR_IGNORE_RATE_LIMIT,
    ATTR_INSTRUCTION,
    ATTR_KEY,
    ATTR_LABEL,
    ATTR_MESSAGE,
    ATTR_MINUTES,
    ATTR_MODE,
    ATTR_PRIORITY,
    ATTR_QUESTION,
    ATTR_REASON,
    ATTR_RECIPIENT,
    ATTR_ROUTINE,
    ATTR_SCHEDULED_FOR,
    ATTR_SOUND,
    ATTR_SOUND_MODE,
    ATTR_SOURCE,
    ATTR_TAG,
    ATTR_TARGET_PLAYER,
    ATTR_TASK_CONTEXT,
    ATTR_TEMPLATE,
    ATTR_TEMPLATE_VARS,
    ATTR_TIME,
    ATTR_TIMEOUT_MINUTES,
    ATTR_TITLE,
    ATTR_TO_STATE,
    ATTR_TTL_HOURS,
    ATTR_TTL_MINUTES,
    ATTR_UNTIL,
    ATTR_UNTIL_HOME,
    ATTR_URGENCY,
    ATTR_VALID_UNTIL,
    ATTR_VOICE_SNOOZE,
    ATTR_VOICE_TIMEOUT_SECONDS,
    ATTR_WHEN,
    ATTR_WORKDAY_ONLY,
    CONF_RECIPIENT,
    DEFAULT_PRIORITY,
    DEFAULT_QUERY_TIMEOUT_MINUTES,
    DEFAULT_WATCH_TTL_HOURS,
    DOMAIN,
    LEGACY_DEFAULT_CALLBACK,
    MAX_WATCH_TTL_HOURS,
    PRIORITY_INTERNAL,
    QUERY_MODE_CHOICE,
    QUERY_MODES,
    SERVICE_ACKNOWLEDGE,
    SERVICE_ALARM_CANCEL,
    SERVICE_ALARM_DISMISS,
    SERVICE_ALARM_SET,
    SERVICE_ALARM_SKIP_NEXT,
    SERVICE_ALARM_SNOOZE,
    SERVICE_ALARM_UPDATE,
    SERVICE_CANCEL,
    SERVICE_DND_OFF,
    SERVICE_DND_ON,
    SERVICE_QUERY,
    SERVICE_REMIND_SELF,
    SERVICE_SCHEDULE,
    SERVICE_SEND,
    SERVICE_WATCH,
    SOUND_MODES,
    URGENCY_LEVELS,
    WEEKDAYS,
)
from .entity_resolver import normalize_trigger
from .models import Alarm, Notification, Query, Schedule, Watch
from .scheduler import parse_when
from .templates import resolve_template
from .watcher import ttl_to_expiry

if TYPE_CHECKING:
    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)

_PRIORITY = vol.All(vol.Coerce(int), vol.Range(min=0, max=4))

SEND_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_PRIORITY): _PRIORITY,
        vol.Optional(ATTR_RECIPIENT): cv.entity_id,
        vol.Optional(ATTR_TARGET_PLAYER): cv.entity_id,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_TAG): cv.string,
        vol.Optional(ATTR_TTL_MINUTES): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=1440)
        ),
        vol.Optional(ATTR_CALLBACK_EVENT): cv.string,
        vol.Optional(ATTR_TEMPLATE): cv.string,
        vol.Optional(ATTR_TEMPLATE_VARS): dict,
        vol.Optional(ATTR_IGNORE_RATE_LIMIT, default=False): cv.boolean,
    }
)

ESCALATION_RULE_SCHEMA = vol.Schema(
    {
        vol.Required("after_minutes"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
        vol.Required("raise_to_priority"): vol.All(
            vol.Coerce(int), vol.Range(min=2, max=4)
        ),
    }
)

QUERY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_QUESTION): cv.string,
        vol.Optional(ATTR_MODE, default="yesno"): vol.In(QUERY_MODES),
        vol.Optional(ATTR_CHOICES): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_PRIORITY, default=DEFAULT_PRIORITY): _PRIORITY,
        vol.Optional(
            ATTR_CALLBACK_EVENT, default=LEGACY_DEFAULT_CALLBACK
        ): cv.string,
        vol.Optional(
            ATTR_TIMEOUT_MINUTES, default=DEFAULT_QUERY_TIMEOUT_MINUTES
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
        vol.Optional(ATTR_VOICE_TIMEOUT_SECONDS): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=3600)
        ),
        vol.Optional(ATTR_DEFAULT_ANSWER): cv.string,
        vol.Optional(ATTR_ESCALATION): vol.All(
            cv.ensure_list, [ESCALATION_RULE_SCHEMA]
        ),
        vol.Optional(ATTR_RECIPIENT): cv.entity_id,
        vol.Optional(ATTR_TARGET_PLAYER): cv.entity_id,
    }
)

WATCH_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TO_STATE): cv.string,
        vol.Optional(ATTR_FROM_STATE): cv.string,
        vol.Optional(ATTR_ABOVE): vol.Coerce(float),
        vol.Optional(ATTR_BELOW): vol.Coerce(float),
        vol.Optional(ATTR_PRIORITY, default=DEFAULT_PRIORITY): _PRIORITY,
        vol.Optional(
            ATTR_TTL_HOURS, default=DEFAULT_WATCH_TTL_HOURS
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_WATCH_TTL_HOURS)),
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_TASK_CONTEXT): cv.string,
    }
)

_ALARM_FIELDS = {
    vol.Optional(ATTR_DAYS): vol.All(cv.ensure_list, [vol.In(WEEKDAYS)]),
    vol.Optional(ATTR_LABEL): cv.string,
    vol.Optional(ATTR_MESSAGE): cv.string,
    vol.Optional(ATTR_URGENCY): vol.In(URGENCY_LEVELS),
    vol.Optional(ATTR_SOUND_MODE): vol.In(SOUND_MODES),
    vol.Optional(ATTR_SOUND): cv.string,
    vol.Optional(ATTR_ANNOUNCE): cv.boolean,
    vol.Optional(ATTR_VOICE_SNOOZE): cv.boolean,
    vol.Optional(ATTR_ROUTINE): vol.Any("", cv.entity_id),
    vol.Optional(ATTR_WORKDAY_ONLY): cv.boolean,
    vol.Optional(ATTR_VALID_UNTIL): cv.string,
    vol.Optional(ATTR_ENABLED): cv.boolean,
}

ALARM_SET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TIME): cv.string,
        vol.Optional(ATTR_KEY): cv.string,
        **_ALARM_FIELDS,
    }
)

ALARM_UPDATE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ID): cv.string,
        vol.Optional(ATTR_TIME): cv.string,
        **_ALARM_FIELDS,
    }
)

ALARM_ID_SCHEMA = vol.Schema({vol.Required(ATTR_ID): cv.string})

ALARM_SNOOZE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ID): cv.string,
        vol.Optional(ATTR_MINUTES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=120)
        ),
    }
)

ALARM_DISMISS_SCHEMA = vol.Schema({vol.Optional(ATTR_ID): cv.string})

DND_ON_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_UNTIL): cv.string,
        vol.Optional(ATTR_UNTIL_HOME, default=False): cv.boolean,
    }
)

DND_OFF_SCHEMA = vol.Schema({})

ACKNOWLEDGE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ID): cv.string,
        vol.Required(ATTR_ANSWER): cv.string,
        vol.Optional(ATTR_SOURCE, default="service"): cv.string,
    }
)

CANCEL_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ID): cv.string,
        vol.Optional(ATTR_REASON): cv.string,
    }
)

SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SCHEDULED_FOR): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_PRIORITY, default=DEFAULT_PRIORITY): _PRIORITY,
        vol.Optional(ATTR_RECIPIENT): cv.entity_id,
        vol.Optional(ATTR_TARGET_PLAYER): cv.entity_id,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_TAG): cv.string,
        vol.Optional(ATTR_TASK_CONTEXT): cv.string,
    }
)

REMIND_SELF_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_WHEN): cv.string,
        vol.Required(ATTR_INSTRUCTION): cv.string,
        vol.Optional(ATTR_TASK_CONTEXT): cv.string,
    }
)


def _get_coordinator(hass: HomeAssistant) -> HeroldCoordinator:
    """Return the coordinator of the (single) loaded config entry."""
    entries: dict[str, HeroldCoordinator] = hass.data.get(DOMAIN) or {}
    if not entries:
        raise HomeAssistantError("Herold is not set up")
    return next(iter(entries.values()))


async def _async_handle_send(call: ServiceCall) -> None:
    """Handle herold.send (fire-and-forget)."""
    coordinator = _get_coordinator(call.hass)

    # Template fields provide defaults; explicit call fields win.
    fields: dict = {}
    if template_name := call.data.get(ATTR_TEMPLATE):
        fields = resolve_template(
            call.hass,
            coordinator.config,
            template_name,
            call.data.get(ATTR_TEMPLATE_VARS),
        )
    for key in (ATTR_MESSAGE, ATTR_PRIORITY, ATTR_TITLE, ATTR_TAG):
        if key in call.data:
            fields[key] = call.data[key]
    if not fields.get(ATTR_MESSAGE):
        raise HomeAssistantError(
            "Either message or a template providing one is required"
        )

    notification = Notification(
        message=fields[ATTR_MESSAGE],
        priority=fields.get(ATTR_PRIORITY, DEFAULT_PRIORITY),
        recipient=call.data.get(
            ATTR_RECIPIENT, coordinator.config.get(CONF_RECIPIENT)
        ),
        target_player=call.data.get(ATTR_TARGET_PLAYER),
        callback_event=call.data.get(ATTR_CALLBACK_EVENT),
        tag=fields.get(ATTR_TAG),
        ttl_minutes=call.data.get(ATTR_TTL_MINUTES),
        title=fields.get(ATTR_TITLE),
        context={"ignore_rate_limit": call.data[ATTR_IGNORE_RATE_LIMIT]},
    )
    _LOGGER.debug("Service send: notification %s", notification.id)
    await coordinator.async_send(notification)


async def _async_handle_query(call: ServiceCall) -> None:
    """Handle herold.query (a notification expecting an answer)."""
    coordinator = _get_coordinator(call.hass)
    mode = call.data[ATTR_MODE]
    choices = call.data.get(ATTR_CHOICES)
    if mode == QUERY_MODE_CHOICE and not choices:
        raise HomeAssistantError("mode 'choice' requires the choices field")
    query = Query(
        question=call.data[ATTR_QUESTION],
        mode=mode,
        choices=choices,
        priority=call.data[ATTR_PRIORITY],
        callback_event=call.data[ATTR_CALLBACK_EVENT],
        timeout_minutes=call.data[ATTR_TIMEOUT_MINUTES],
        voice_timeout_seconds=call.data.get(ATTR_VOICE_TIMEOUT_SECONDS),
        default_answer=call.data.get(ATTR_DEFAULT_ANSWER),
        escalation=call.data.get(ATTR_ESCALATION),
        recipient=call.data.get(
            ATTR_RECIPIENT, coordinator.config.get(CONF_RECIPIENT)
        ),
        target_player=call.data.get(ATTR_TARGET_PLAYER),
    )
    _LOGGER.debug("Service query: query %s (%s)", query.id, mode)
    await coordinator.async_ask(query)


async def _async_handle_acknowledge(call: ServiceCall) -> None:
    """Handle herold.acknowledge (answer a pending query)."""
    coordinator = _get_coordinator(call.hass)
    await coordinator.query_manager.async_answer(
        call.data[ATTR_ID], call.data[ATTR_ANSWER], call.data[ATTR_SOURCE]
    )


async def _async_handle_cancel(call: ServiceCall) -> None:
    """Handle herold.cancel (drop a pending query or schedule)."""
    coordinator = _get_coordinator(call.hass)
    item_id = call.data[ATTR_ID]
    query = coordinator.query_manager.queries.get(item_id)
    if query is not None and query.is_pending:
        await coordinator.query_manager.async_cancel(
            item_id, call.data.get(ATTR_REASON)
        )
        return
    if await coordinator.scheduler.async_cancel(item_id):
        return
    if await coordinator.watcher.async_cancel(item_id):
        return
    raise HomeAssistantError(
        f"No pending query, schedule or watch with id {item_id}"
    )


async def _async_handle_schedule(call: ServiceCall) -> None:
    """Handle herold.schedule (deferred notification)."""
    coordinator = _get_coordinator(call.hass)
    scheduled_for = parse_when(call.data[ATTR_SCHEDULED_FOR])
    payload = {
        "message": call.data[ATTR_MESSAGE],
        "priority": call.data[ATTR_PRIORITY],
        "recipient": call.data.get(
            ATTR_RECIPIENT, coordinator.config.get(CONF_RECIPIENT)
        ),
        "target_player": call.data.get(ATTR_TARGET_PLAYER),
        "title": call.data.get(ATTR_TITLE),
        "tag": call.data.get(ATTR_TAG),
    }
    if task_context := call.data.get(ATTR_TASK_CONTEXT):
        payload["context"] = {"task_context": task_context}
    schedule = Schedule(scheduled_for=scheduled_for, payload=payload)
    _LOGGER.debug("Service schedule: %s at %s", schedule.id, scheduled_for)
    await coordinator.scheduler.async_add(schedule)


async def _async_handle_remind_self(call: ServiceCall) -> None:
    """Handle herold.remind_self (P0 convenience wrapper for schedule)."""
    coordinator = _get_coordinator(call.hass)
    scheduled_for = parse_when(call.data[ATTR_WHEN])
    payload: dict = {
        "message": call.data[ATTR_INSTRUCTION],
        "priority": PRIORITY_INTERNAL,
    }
    if task_context := call.data.get(ATTR_TASK_CONTEXT):
        payload["context"] = {"task_context": task_context}
    schedule = Schedule(scheduled_for=scheduled_for, payload=payload)
    _LOGGER.debug("Service remind_self: %s at %s", schedule.id, scheduled_for)
    await coordinator.scheduler.async_add(schedule)


async def _async_handle_watch(call: ServiceCall) -> None:
    """Handle herold.watch (state-triggered reminder)."""
    coordinator = _get_coordinator(call.hass)
    payload: dict = {
        "message": call.data[ATTR_MESSAGE],
        "priority": call.data[ATTR_PRIORITY],
        "title": call.data.get(ATTR_TITLE),
    }
    if task_context := call.data.get(ATTR_TASK_CONTEXT):
        payload["context"] = {"task_context": task_context}
    entity_id = call.data[ATTR_ENTITY_ID]
    # "on" means "left the off state" for domains that never report "on".
    to_state, from_state = normalize_trigger(
        entity_id, call.data.get(ATTR_TO_STATE), call.data.get(ATTR_FROM_STATE)
    )
    watch = Watch(
        entity_id=entity_id,
        payload=payload,
        to_state=to_state,
        from_state=from_state,
        above=call.data.get(ATTR_ABOVE),
        below=call.data.get(ATTR_BELOW),
        expires_at=ttl_to_expiry(call.data[ATTR_TTL_HOURS]),
    )
    _LOGGER.debug("Service watch: %s on %s", watch.id, watch.entity_id)
    await coordinator.watcher.async_add(watch)


def _alarm_changes(data: dict) -> dict:
    """Collect the alarm fields present in a service call."""
    changes: dict = {}
    for key in (
        ATTR_TIME,
        ATTR_LABEL,
        ATTR_MESSAGE,
        ATTR_URGENCY,
        ATTR_SOUND_MODE,
        ATTR_SOUND,
        ATTR_ANNOUNCE,
        ATTR_VOICE_SNOOZE,
        ATTR_ROUTINE,
        ATTR_WORKDAY_ONLY,
        ATTR_ENABLED,
    ):
        if key in data:
            changes[key] = data[key]
    if ATTR_DAYS in data:
        changes[ATTR_DAYS] = list(data[ATTR_DAYS] or [])
    if ATTR_VALID_UNTIL in data:
        raw = data[ATTR_VALID_UNTIL]
        changes[ATTR_VALID_UNTIL] = parse_when(raw) if raw else ""
    return changes


async def _async_handle_alarm_set(call: ServiceCall) -> None:
    """Handle herold.alarm_set."""
    coordinator = _get_coordinator(call.hass)
    changes = _alarm_changes(call.data)
    changes.pop(ATTR_TIME, None)
    # "" means "clear" when updating; on a new alarm it just means the field
    # was left blank, so let the dataclass defaults stand.
    changes = {name: value for name, value in changes.items() if value != ""}
    alarm = Alarm(
        time=call.data[ATTR_TIME],
        key=call.data.get(ATTR_KEY),
        **changes,
    )
    await coordinator.alarms.async_add(alarm)


async def _async_handle_alarm_update(call: ServiceCall) -> None:
    """Handle herold.alarm_update — the card's editor uses this."""
    coordinator = _get_coordinator(call.hass)
    await coordinator.alarms.async_update(
        call.data[ATTR_ID], _alarm_changes(call.data)
    )


async def _async_handle_alarm_skip_next(call: ServiceCall) -> None:
    """Handle herold.alarm_skip_next."""
    coordinator = _get_coordinator(call.hass)
    await coordinator.alarms.async_skip_next(call.data[ATTR_ID])


async def _async_handle_alarm_cancel(call: ServiceCall) -> None:
    """Handle herold.alarm_cancel."""
    coordinator = _get_coordinator(call.hass)
    if not await coordinator.alarms.async_cancel(call.data[ATTR_ID]):
        raise HomeAssistantError(f"Unknown alarm id: {call.data[ATTR_ID]}")


async def _async_handle_alarm_snooze(call: ServiceCall) -> None:
    """Handle herold.alarm_snooze."""
    coordinator = _get_coordinator(call.hass)
    await coordinator.alarms.async_snooze(
        call.data.get(ATTR_ID), call.data.get(ATTR_MINUTES)
    )


async def _async_handle_alarm_dismiss(call: ServiceCall) -> None:
    """Handle herold.alarm_dismiss."""
    coordinator = _get_coordinator(call.hass)
    await coordinator.alarms.async_dismiss(call.data.get(ATTR_ID))


async def _async_handle_dnd_on(call: ServiceCall) -> None:
    """Handle herold.dnd_on (optionally as a session with an end condition)."""
    coordinator = _get_coordinator(call.hass)
    until_raw = call.data.get(ATTR_UNTIL)
    until_home = call.data[ATTR_UNTIL_HOME]
    if until_raw is None and not until_home:
        coordinator.set_master_dnd(True)
        return
    until = parse_when(until_raw) if until_raw else None
    _LOGGER.debug("DND session: until=%s until_home=%s", until, until_home)
    await coordinator.async_dnd_session(until, until_home)


async def _async_handle_dnd_off(call: ServiceCall) -> None:
    """Handle herold.dnd_off."""
    coordinator = _get_coordinator(call.hass)
    coordinator.set_master_dnd(False)


_SERVICES = (
    (SERVICE_SEND, _async_handle_send, SEND_SCHEMA),
    (SERVICE_QUERY, _async_handle_query, QUERY_SCHEMA),
    (SERVICE_ACKNOWLEDGE, _async_handle_acknowledge, ACKNOWLEDGE_SCHEMA),
    (SERVICE_CANCEL, _async_handle_cancel, CANCEL_SCHEMA),
    (SERVICE_SCHEDULE, _async_handle_schedule, SCHEDULE_SCHEMA),
    (SERVICE_REMIND_SELF, _async_handle_remind_self, REMIND_SELF_SCHEMA),
    (SERVICE_WATCH, _async_handle_watch, WATCH_SCHEMA),
    (SERVICE_ALARM_SET, _async_handle_alarm_set, ALARM_SET_SCHEMA),
    (SERVICE_ALARM_UPDATE, _async_handle_alarm_update, ALARM_UPDATE_SCHEMA),
    (SERVICE_ALARM_SKIP_NEXT, _async_handle_alarm_skip_next, ALARM_ID_SCHEMA),
    (SERVICE_ALARM_CANCEL, _async_handle_alarm_cancel, ALARM_ID_SCHEMA),
    (SERVICE_ALARM_SNOOZE, _async_handle_alarm_snooze, ALARM_SNOOZE_SCHEMA),
    (SERVICE_ALARM_DISMISS, _async_handle_alarm_dismiss, ALARM_DISMISS_SCHEMA),
    (SERVICE_DND_ON, _async_handle_dnd_on, DND_ON_SCHEMA),
    (SERVICE_DND_OFF, _async_handle_dnd_off, DND_OFF_SCHEMA),
)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the herold services (idempotent)."""
    for name, handler, schema in _SERVICES:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove the herold services."""
    for name, _handler, _schema in _SERVICES:
        hass.services.async_remove(DOMAIN, name)
