"""Stateless dispatch rules: whether and where a notification is delivered.

The priority rules follow HEROLD_PLAN.md section 3:

* P0 (internal): never user-facing — executed by a conversation agent via
  the internal channel.
* P1 (todo): silent — always lands in the todo inbox (no DND/home gating,
  the inbox is for later review by definition).
* P2 (normal): dropped while DND is active.
* P3 (important) / P4 (alarm): always delivered.

Channel selection also follows the original script: voice when home and a
room is active, push for P3/P4, telegram as the catch-all when the message
would otherwise not reach the user (away, no active room, or high priority).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from .const import (
    CHANNEL_INTERNAL,
    CHANNEL_PUSH,
    CHANNEL_TELEGRAM,
    CHANNEL_TODO,
    CHANNEL_VOICE,
    CONF_TELEGRAM_CHAT_ID,
    PRIORITY_IMPORTANT,
    PRIORITY_INTERNAL,
    PRIORITY_NORMAL,
    PRIORITY_TODO,
)
from .room_router import select_room

if TYPE_CHECKING:
    from .channels.base import BaseChannel
    from .coordinator import HeroldCoordinator
    from .models import Notification, Query

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchContext:
    """Snapshot of the environment a dispatch decision is based on."""

    coordinator: HeroldCoordinator
    is_home: bool
    is_dnd: bool
    internet_available: bool


def should_deliver(
    item: Notification | Query, ctx: DispatchContext
) -> tuple[bool, str]:
    """Decide whether the notification/query passes the priority rules."""
    priority = item.priority
    if priority == PRIORITY_INTERNAL:
        return (True, "priority 0 runs through the internal channel")
    if priority == PRIORITY_TODO:
        return (True, "priority 1 lands silently in the todo inbox")
    if priority == PRIORITY_NORMAL:
        if ctx.is_dnd:
            return (False, "priority 2 blocked by DND")
        return (True, "priority 2 accepted")
    return (True, f"priority {priority} always delivers")


def select_channels(
    notification: Notification, ctx: DispatchContext
) -> list[BaseChannel]:
    """Pick the channels used for a fire-and-forget notification."""
    coordinator = ctx.coordinator

    if notification.priority == PRIORITY_INTERNAL:
        return [coordinator.channels[CHANNEL_INTERNAL]]
    if notification.priority == PRIORITY_TODO:
        return [coordinator.channels[CHANNEL_TODO]]

    voice = coordinator.channels[CHANNEL_VOICE]
    push = coordinator.channels[CHANNEL_PUSH]
    selected: list[BaseChannel] = []

    voice_wanted = ctx.is_home and (
        notification.target_player is not None
        or select_room(coordinator) is not None
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
        # not silently lost. The offline queue will replace this later.
        selected.append(push)

    # Telegram catch-all (original script rule): high priority, away from
    # home, or no voice target reached.
    if (
        _telegram_configured(coordinator)
        and ctx.internet_available
        and (
            notification.priority >= PRIORITY_IMPORTANT
            or not ctx.is_home
            or not voice_selected
        )
    ):
        selected.append(coordinator.channels[CHANNEL_TELEGRAM])

    if push in selected and not ctx.internet_available:
        _LOGGER.debug(
            "Push selected for %s while offline; delivery will likely fail "
            "(offline queue lands in a later phase)",
            notification.id,
        )

    return selected


def select_query_channels(
    query: Query, ctx: DispatchContext
) -> list[BaseChannel]:
    """Pick the channels used for a query (a message expecting an answer)."""
    coordinator = ctx.coordinator
    voice = coordinator.channels[CHANNEL_VOICE]
    push = coordinator.channels[CHANNEL_PUSH]
    selected: list[BaseChannel] = []

    # Voice: satellites can capture the answer via conversation; media-player
    # rooms only speak the question (the answer must come via Telegram).
    answerable_by_voice = False
    voice_wanted = False
    if ctx.is_home:
        if query.target_player is not None:
            voice_wanted = True
            answerable_by_voice = query.target_player.startswith(
                "assist_satellite."
            )
        else:
            room = select_room(coordinator)
            if room is not None:
                voice_wanted = True
                answerable_by_voice = room.supports_query()

    if voice_wanted:
        if ctx.internet_available or voice.offline_capable:
            selected.append(voice)
        else:
            answerable_by_voice = False
            _LOGGER.debug(
                "Voice query skipped for %s: offline and no offline fallback",
                query.id,
            )

    if query.priority >= PRIORITY_IMPORTANT:
        selected.append(push)

    # Telegram carries the answer buttons whenever voice cannot capture the
    # answer, plus for high priority or away — mirrors the original script.
    if (
        _telegram_configured(coordinator)
        and ctx.internet_available
        and (
            query.priority >= PRIORITY_IMPORTANT
            or not ctx.is_home
            or not answerable_by_voice
        )
    ):
        selected.append(coordinator.channels[CHANNEL_TELEGRAM])

    return selected


def _telegram_configured(coordinator: HeroldCoordinator) -> bool:
    return bool(coordinator.config.get(CONF_TELEGRAM_CHAT_ID)) and (
        CHANNEL_TELEGRAM in coordinator.channels
    )
