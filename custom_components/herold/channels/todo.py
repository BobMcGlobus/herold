"""Todo channel: P1 notifications land silently in the Herold inbox."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..const import CHANNEL_TODO
from .base import BaseChannel

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification

_LOGGER = logging.getLogger(__name__)


class TodoChannel(BaseChannel):
    """Add P1 notifications to the todo.herold_inbox list."""

    name = CHANNEL_TODO
    offline_capable = True  # purely local

    async def deliver(
        self, notification: Notification, coordinator: HeroldCoordinator
    ) -> None:
        """Create an inbox item for the notification."""
        coordinator.async_add_todo_item(
            uid=notification.id,
            summary=notification.message,
            description=notification.tag,
        )
        _LOGGER.debug(
            "Todo inbox item created for notification %s", notification.id
        )
