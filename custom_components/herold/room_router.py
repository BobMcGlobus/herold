"""Occupancy based room selection.

Phase 1 keeps this deliberately simple: the first occupied, voice-capable
room wins. Multi-occupancy conflict resolution (priority_weight,
time_since_activation, last_sat_interaction) lands in Phase 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import HeroldCoordinator
    from .models import Room


async def get_active_room(coordinator: HeroldCoordinator) -> Room | None:
    """Return the first occupied room that can deliver voice, if any."""
    for room in coordinator.rooms:
        if room.is_occupied(coordinator.hass) and room.can_deliver_voice():
            return room
    return None
