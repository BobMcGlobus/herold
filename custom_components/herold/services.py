"""Service handlers for the Herold integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    ATTR_ANSWER,
    ATTR_CALLBACK_EVENT,
    ATTR_CHOICES,
    ATTR_DEFAULT_ANSWER,
    ATTR_ID,
    ATTR_INSTRUCTION,
    ATTR_MESSAGE,
    ATTR_MODE,
    ATTR_PRIORITY,
    ATTR_QUESTION,
    ATTR_REASON,
    ATTR_RECIPIENT,
    ATTR_SCHEDULED_FOR,
    ATTR_SOURCE,
    ATTR_TAG,
    ATTR_TARGET_PLAYER,
    ATTR_TIMEOUT_MINUTES,
    ATTR_TITLE,
    ATTR_TTL_MINUTES,
    ATTR_WHEN,
    CONF_RECIPIENT,
    DEFAULT_PRIORITY,
    DEFAULT_QUERY_TIMEOUT_MINUTES,
    DOMAIN,
    LEGACY_DEFAULT_CALLBACK,
    PRIORITY_INTERNAL,
    QUERY_MODE_CHOICE,
    QUERY_MODES,
    SERVICE_ACKNOWLEDGE,
    SERVICE_CANCEL,
    SERVICE_QUERY,
    SERVICE_REMIND_SELF,
    SERVICE_SCHEDULE,
    SERVICE_SEND,
)
from .models import Notification, Query, Schedule
from .scheduler import parse_when

if TYPE_CHECKING:
    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)

_PRIORITY = vol.All(vol.Coerce(int), vol.Range(min=0, max=4))

SEND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_PRIORITY, default=DEFAULT_PRIORITY): _PRIORITY,
        vol.Optional(ATTR_RECIPIENT): cv.entity_id,
        vol.Optional(ATTR_TARGET_PLAYER): cv.entity_id,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_TAG): cv.string,
        vol.Optional(ATTR_TTL_MINUTES): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=1440)
        ),
        vol.Optional(ATTR_CALLBACK_EVENT): cv.string,
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
        vol.Optional(ATTR_DEFAULT_ANSWER): cv.string,
        vol.Optional(ATTR_RECIPIENT): cv.entity_id,
        vol.Optional(ATTR_TARGET_PLAYER): cv.entity_id,
    }
)

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
    }
)

REMIND_SELF_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_WHEN): cv.string,
        vol.Required(ATTR_INSTRUCTION): cv.string,
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
    notification = Notification(
        message=call.data[ATTR_MESSAGE],
        priority=call.data[ATTR_PRIORITY],
        recipient=call.data.get(
            ATTR_RECIPIENT, coordinator.config.get(CONF_RECIPIENT)
        ),
        target_player=call.data.get(ATTR_TARGET_PLAYER),
        callback_event=call.data.get(ATTR_CALLBACK_EVENT),
        tag=call.data.get(ATTR_TAG),
        ttl_minutes=call.data.get(ATTR_TTL_MINUTES),
        title=call.data.get(ATTR_TITLE),
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
        default_answer=call.data.get(ATTR_DEFAULT_ANSWER),
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
    raise HomeAssistantError(f"No pending query or schedule with id {item_id}")


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
    schedule = Schedule(scheduled_for=scheduled_for, payload=payload)
    _LOGGER.debug("Service schedule: %s at %s", schedule.id, scheduled_for)
    await coordinator.scheduler.async_add(schedule)


async def _async_handle_remind_self(call: ServiceCall) -> None:
    """Handle herold.remind_self (P0 convenience wrapper for schedule)."""
    coordinator = _get_coordinator(call.hass)
    scheduled_for = parse_when(call.data[ATTR_WHEN])
    schedule = Schedule(
        scheduled_for=scheduled_for,
        payload={
            "message": call.data[ATTR_INSTRUCTION],
            "priority": PRIORITY_INTERNAL,
        },
    )
    _LOGGER.debug("Service remind_self: %s at %s", schedule.id, scheduled_for)
    await coordinator.scheduler.async_add(schedule)


_SERVICES = (
    (SERVICE_SEND, _async_handle_send, SEND_SCHEMA),
    (SERVICE_QUERY, _async_handle_query, QUERY_SCHEMA),
    (SERVICE_ACKNOWLEDGE, _async_handle_acknowledge, ACKNOWLEDGE_SCHEMA),
    (SERVICE_CANCEL, _async_handle_cancel, CANCEL_SCHEMA),
    (SERVICE_SCHEDULE, _async_handle_schedule, SCHEDULE_SCHEMA),
    (SERVICE_REMIND_SELF, _async_handle_remind_self, REMIND_SELF_SCHEMA),
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
