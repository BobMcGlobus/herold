"""Stateless dispatch rules: whether and where a notification is delivered.

The priority rules are ported 1:1 from the original omnichannel script
(see HEROLD_PLAN.md section 3):

* P0 (internal): never user-facing — Phase 1 skips it with a log entry,
  the real internal channel lands in Phase 3.
* P1 (todo): only when home and not DND — Phase 1 drops it otherwise,
  the todo channel lands in Phase 3.
* P2 (normal): dropped while DND is active.
* P3 (important) / P4 (alarm): always delivered.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from .const import (
    CHANNEL_PUSH,
    CHANNEL_VOICE,
    PRIORITY_IMPORTANT,
    PRIORITY_INTERNAL,
    PRIORITY_NORMAL,
    PRIORITY_TODO,
)

if TYPE_CHECKING:
    from .channels.base import BaseChannel
    from .coordinator import HeroldCoordinator
    from .models import Notification

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchContext:
    """Snapshot of the environment a dispatch decision is based on."""

    coordinator: HeroldCoordinator
    is_home: bool
    is_dnd: bool
    internet_available: bool


def should_deliver(
    notification: Notification, ctx: DispatchContext
) -> tuple[bool, str]:
    """Decide whether the notification passes the priority rules."""
    priority = notification.priority
    if priority == PRIORITY_INTERNAL:
        return (False, "priority 0 (internal) is not implemented in Phase 1")
    if priority == PRIORITY_TODO:
        if not ctx.is_home:
            return (False, "priority 1 requires the recipient to be home")
        if ctx.is_dnd:
            return (False, "priority 1 blocked by DND")
        return (True, "priority 1 accepted")
    if priority == PRIORITY_NORMAL:
        if ctx.is_dnd:
            return (False, "priority 2 blocked by DND")
        return (True, "priority 2 accepted")
    return (True, f"priority {priority} always delivers")


def select_channels(
    notification: Notification, ctx: DispatchContext
) -> list[BaseChannel]:
    """Pick the channels used for this notification."""
    coordinator = ctx.coordinator
    voice = coordinator.channels[CHANNEL_VOICE]
    push = coordinator.channels[CHANNEL_PUSH]
    selected: list[BaseChannel] = []

    voice_wanted = ctx.is_home and (
        notification.target_player is not None
        or _has_active_voice_room(coordinator)
    )
    voice_selected = False
    if voice_wanted:
        if ctx.internet_available or voice.offline_capable:
            selected.append(voice)
            voice_selected = True
        else:
            _LOGGER.debug(
                "Voice skipped for %s: offline and no offline fallback configured",
                notification.id,
            )

    if notification.priority >= PRIORITY_IMPORTANT or (
        notification.priority == PRIORITY_NORMAL and not ctx.is_home
    ):
        selected.append(push)
    elif (
        notification.priority == PRIORITY_NORMAL
        and voice_wanted
        and not voice_selected
    ):
        # Voice was skipped due to offline: attempt push so the message is
        # not silently lost. Phase 2 replaces this with the offline queue.
        selected.append(push)

    if push in selected and not ctx.internet_available:
        _LOGGER.debug(
            "Push selected for %s while offline; delivery will likely fail "
            "(offline queue lands in Phase 2)",
            notification.id,
        )

    return selected


def _has_active_voice_room(coordinator: HeroldCoordinator) -> bool:
    """Return True if any occupied room can deliver voice."""
    return any(
        room.is_occupied(coordinator.hass) and room.can_deliver_voice()
        for room in coordinator.rooms
    )
