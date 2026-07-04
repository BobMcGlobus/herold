"""Push delivery channel via mobile_app notify services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..const import (
    CHANNEL_PUSH,
    CONF_MOBILE_APP_DEVICES,
    PRIORITY_ALARM,
    PRIORITY_IMPORTANT,
)
from .base import BaseChannel, ChannelUnavailable

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification, Query

_LOGGER = logging.getLogger(__name__)


class PushChannel(BaseChannel):
    """Deliver notifications to configured mobile app devices."""

    name = CHANNEL_PUSH
    offline_capable = False  # needs APN/FCM; offline queue comes in Phase 2

    async def deliver(
        self, notification: Notification, coordinator: HeroldCoordinator
    ) -> None:
        """Send a push notification to every configured device."""
        await self._send(
            coordinator,
            notification.message,
            notification.priority,
            notification.title,
            notification.id,
        )

    async def deliver_query(
        self, query: Query, coordinator: HeroldCoordinator
    ) -> None:
        """Push the question text; answering happens via other channels."""
        await self._send(
            coordinator, query.question, query.priority, None, query.id
        )

    async def _send(
        self,
        coordinator: HeroldCoordinator,
        message: str,
        priority: int,
        title: str | None,
        item_id: str,
    ) -> None:
        devices: list[str] = coordinator.config.get(CONF_MOBILE_APP_DEVICES) or []
        if not devices:
            raise ChannelUnavailable("No mobile app devices configured")

        data: dict[str, Any] = {
            "message": message,
            "title": self._title(priority, title),
        }
        if priority == PRIORITY_ALARM:
            data["data"] = {
                "push": {"sound": {"name": "default", "critical": 1, "volume": 1}}
            }
        elif priority == PRIORITY_IMPORTANT:
            data["data"] = {"push": {"sound": {"name": "default", "volume": 0.8}}}

        for device in devices:
            # Config stores notify entity ids (notify.mobile_app_*); the legacy
            # notify service of the same name accepts the rich push payload.
            service = device.split(".", 1)[1] if "." in device else device
            await coordinator.hass.services.async_call(
                "notify", service, data, blocking=True
            )
            _LOGGER.debug("Push for %s sent via notify.%s", item_id, service)

    @staticmethod
    def _title(priority: int, title: str | None) -> str:
        """Explicit title wins; otherwise derive from priority."""
        if title:
            return title
        if priority == PRIORITY_ALARM:
            return "🚨 KRITISCHER ALARM"
        if priority == PRIORITY_IMPORTANT:
            return "⚠️ Wichtige Mitteilung"
        return "ℹ️ Mitteilung"
