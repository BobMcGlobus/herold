"""Service handlers for the Herold integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    ATTR_CALLBACK_EVENT,
    ATTR_MESSAGE,
    ATTR_PRIORITY,
    ATTR_RECIPIENT,
    ATTR_TAG,
    ATTR_TARGET_PLAYER,
    ATTR_TITLE,
    ATTR_TTL_MINUTES,
    CONF_RECIPIENT,
    DEFAULT_PRIORITY,
    DOMAIN,
    SERVICE_SEND,
)
from .models import Notification

if TYPE_CHECKING:
    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)

SEND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_PRIORITY, default=DEFAULT_PRIORITY): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=4)
        ),
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


def _get_coordinator(hass: HomeAssistant) -> HeroldCoordinator:
    """Return the coordinator of the (single) loaded config entry."""
    entries: dict[str, HeroldCoordinator] = hass.data.get(DOMAIN) or {}
    if not entries:
        raise HomeAssistantError("Herold is not set up")
    return next(iter(entries.values()))


async def _async_handle_send(call: ServiceCall) -> None:
    """Handle herold.send (fire-and-forget in Phase 1)."""
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


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the herold services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND):
        return
    hass.services.async_register(
        DOMAIN, SERVICE_SEND, _async_handle_send, schema=SEND_SCHEMA
    )


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove the herold services."""
    hass.services.async_remove(DOMAIN, SERVICE_SEND)
