"""Per-priority rate limiting and aggregation (HEROLD_PLAN.md section 13).

* P4: no limit — alarms always go through.
* P3: 60 s cooldown per tag (or message text when untagged) — deduplicates
  identical high-priority notifications.
* P2: max 3 per 5 minutes; overflow is buffered and flushed as one
  aggregated notification when the window frees up.
* P0/P1: not handled here (P0 has its own anti-runaway, P1 is unlimited).

Bypass with ``ignore_rate_limit: true`` on the service call. Queries never
pass through the limiter.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from homeassistant.helpers.event import async_call_later

from .const import (
    PRIORITY_IMPORTANT,
    PRIORITY_NORMAL,
    RATE_LIMIT_P2_MAX_PER_WINDOW,
    RATE_LIMIT_P2_WINDOW_SECONDS,
    RATE_LIMIT_P3_COOLDOWN_SECONDS,
)
from .models import Notification

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window limits with P2 aggregation."""

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator
        self._p3_last: dict[str, float] = {}
        self._p2_times: list[float] = []
        self._p2_buffer: list[Notification] = []
        self._flush_cancel: Callable[[], None] | None = None

    def check(self, notification: Notification) -> tuple[bool, str | None]:
        """Return (allowed, reason). Buffers P2 overflow for aggregation."""
        if notification.context.get("ignore_rate_limit"):
            return (True, None)

        priority = notification.priority
        now = time.monotonic()

        if priority == PRIORITY_IMPORTANT:
            key = notification.tag or notification.message
            last = self._p3_last.get(key)
            if (
                last is not None
                and now - last < RATE_LIMIT_P3_COOLDOWN_SECONDS
            ):
                return (
                    False,
                    f"P3 cooldown ({RATE_LIMIT_P3_COOLDOWN_SECONDS}s) "
                    f"for tag/message {key!r}",
                )
            self._p3_last[key] = now
            return (True, None)

        if priority == PRIORITY_NORMAL:
            self._p2_times = [
                stamp
                for stamp in self._p2_times
                if now - stamp < RATE_LIMIT_P2_WINDOW_SECONDS
            ]
            if len(self._p2_times) < RATE_LIMIT_P2_MAX_PER_WINDOW:
                self._p2_times.append(now)
                return (True, None)
            self._buffer(notification, now)
            return (
                False,
                "P2 rate limit reached; buffered for aggregated delivery",
            )

        return (True, None)

    def _buffer(self, notification: Notification, now: float) -> None:
        self._p2_buffer.append(notification)
        if self._flush_cancel is not None:
            return
        delay = max(
            self._p2_times[0] + RATE_LIMIT_P2_WINDOW_SECONDS - now, 1
        )
        _LOGGER.debug(
            "P2 aggregation buffer armed; flushing in %.0f s", delay
        )
        self._flush_cancel = async_call_later(
            self.coordinator.hass, delay, self._async_flush
        )

    async def _async_flush(self, _now: datetime) -> None:
        """Send buffered P2 notifications as one aggregated message."""
        self._flush_cancel = None
        buffered = self._p2_buffer
        self._p2_buffer = []
        if not buffered:
            return
        if len(buffered) == 1:
            combined = buffered[0]
            combined.context["ignore_rate_limit"] = True
        else:
            messages = "; ".join(item.message for item in buffered)
            combined = Notification(
                message=f"{len(buffered)} Meldungen: {messages}",
                priority=PRIORITY_NORMAL,
                context={"ignore_rate_limit": True},
            )
        _LOGGER.debug(
            "Flushing %d aggregated P2 notification(s)", len(buffered)
        )
        await self.coordinator.async_send(combined)

    def shutdown(self) -> None:
        """Cancel the pending flush timer."""
        if self._flush_cancel is not None:
            self._flush_cancel()
            self._flush_cancel = None
