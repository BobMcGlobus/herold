"""Occupancy based room selection with multi-occupancy conflict resolution.

When several rooms are occupied at once, the winner is picked by:

1. ``priority_weight`` (config, higher wins)
2. most recent occupancy activation (tracked by the coordinator)

If no room is occupied, the last known room stays a valid voice target for
LAST_KNOWN_ROOM_TTL_MINUTES (you just left the room — the announcement is
likely still audible / you are likely to return).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import LAST_KNOWN_ROOM_TTL_MINUTES

if TYPE_CHECKING:
    from datetime import datetime

    from .coordinator import HeroldCoordinator
    from .models import Room

_EPOCH = dt_util.utc_from_timestamp(0)


def select_room(
    coordinator: HeroldCoordinator, require_sat: bool = False
) -> Room | None:
    """Return the best voice target room, if any.

    ``require_sat=True`` restricts candidates to rooms that can run a
    conversation (query delivery).
    """

    def capable(room: Room) -> bool:
        return room.supports_query() if require_sat else room.can_deliver_voice()

    candidates = [
        room
        for room in coordinator.rooms
        if capable(room) and room.is_occupied(coordinator.hass)
    ]
    if candidates:
        return max(candidates, key=lambda room: _rank(coordinator, room))

    return _last_known_room_fallback(coordinator, capable)


def _rank(
    coordinator: HeroldCoordinator, room: Room
) -> tuple[int, datetime]:
    activation = coordinator.store.room_last_activation.get(room.name, _EPOCH)
    return (room.priority_weight, activation)


def _last_known_room_fallback(
    coordinator: HeroldCoordinator, capable
) -> Room | None:
    store = coordinator.store
    if not store.last_known_room or store.last_room_activity is None:
        return None
    ttl = timedelta(minutes=LAST_KNOWN_ROOM_TTL_MINUTES)
    if dt_util.utcnow() - store.last_room_activity > ttl:
        return None
    for room in coordinator.rooms:
        if room.name == store.last_known_room and capable(room):
            return room
    return None
