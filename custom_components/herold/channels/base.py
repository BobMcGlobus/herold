"""Base class for Herold delivery channels."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification, Query


class ChannelUnavailable(HomeAssistantError):
    """Raised when a channel cannot deliver in the current environment."""


class BaseChannel(ABC):
    """A delivery channel (voice, push, telegram, ...)."""

    name: ClassVar[str]
    offline_capable: bool = False

    @abstractmethod
    async def deliver(
        self, notification: Notification, coordinator: HeroldCoordinator
    ) -> None:
        """Deliver the notification. Raise ChannelUnavailable on hard failure."""

    async def deliver_query(
        self, query: Query, coordinator: HeroldCoordinator
    ) -> None:
        """Deliver a query (a notification expecting an answer)."""
        raise ChannelUnavailable(f"Channel {self.name} cannot deliver queries")

    async def is_available(self, coordinator: HeroldCoordinator) -> bool:
        """Return True if the channel can currently be used."""
        return True
