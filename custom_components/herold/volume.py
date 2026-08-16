"""Temporary volume override for announcements.

Two things make this trickier than "set, speak, restore":

* Herold does not know when a media player finished speaking, so the
  restore waits for the player to leave the playing state (polled, with a
  timeout) instead of sleeping a fixed amount.
* Announcements can overlap. A per-entity counter makes sure the original
  volume is captured once and only restored after the last overlapping
  announcement finished — otherwise the first one's restore would undo the
  second one's volume.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.media_player import (
    ATTR_MEDIA_VOLUME_LEVEL,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.exceptions import HomeAssistantError

from .const import (
    VOLUME_RESTORE_POLL_SECONDS,
    VOLUME_RESTORE_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_BUSY_STATES = (MediaPlayerState.PLAYING, MediaPlayerState.BUFFERING)


class VolumeController:
    """Applies and restores announcement volumes per media player."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._original: dict[str, float] = {}
        self._depth: dict[str, int] = {}

    @asynccontextmanager
    async def announce_at(
        self, entity_id: str | None, volume: float | None
    ) -> AsyncIterator[None]:
        """Set the volume for the duration of an announcement."""
        applied = await self._async_apply(entity_id, volume)
        try:
            yield
        finally:
            if applied and entity_id:
                await self._async_release(entity_id)

    async def _async_apply(
        self, entity_id: str | None, volume: float | None
    ) -> bool:
        if not entity_id or volume is None:
            return False
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        features = state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0
        if not features & MediaPlayerEntityFeature.VOLUME_SET:
            _LOGGER.debug("%s does not support volume_set; skipping", entity_id)
            return False

        depth = self._depth.get(entity_id, 0)
        if depth == 0:
            current = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL)
            if current is not None:
                self._original[entity_id] = float(current)
        self._depth[entity_id] = depth + 1

        await self._async_set_volume(entity_id, volume)
        return True

    async def _async_release(self, entity_id: str) -> None:
        depth = self._depth.get(entity_id, 1) - 1
        if depth > 0:
            # Another announcement is still running on this player.
            self._depth[entity_id] = depth
            return
        self._depth.pop(entity_id, None)
        original = self._original.pop(entity_id, None)
        if original is None:
            return
        await self._async_wait_until_idle(entity_id)
        await self._async_set_volume(entity_id, original)

    async def _async_set_volume(self, entity_id: str, volume: float) -> None:
        data: dict[str, Any] = {
            "entity_id": entity_id,
            "volume_level": round(max(0.0, min(volume, 1.0)), 3),
        }
        try:
            await self.hass.services.async_call(
                "media_player", "volume_set", data, blocking=True
            )
        except HomeAssistantError as err:
            _LOGGER.debug("Setting volume on %s failed: %s", entity_id, err)

    async def _async_wait_until_idle(self, entity_id: str) -> None:
        """Wait until the player stopped playing (bounded by a timeout)."""
        waited = 0.0
        while waited < VOLUME_RESTORE_TIMEOUT_SECONDS:
            state = self.hass.states.get(entity_id)
            if state is None or state.state not in _BUSY_STATES:
                return
            await asyncio.sleep(VOLUME_RESTORE_POLL_SECONDS)
            waited += VOLUME_RESTORE_POLL_SECONDS
        _LOGGER.debug(
            "%s still busy after %ss; restoring volume anyway",
            entity_id,
            VOLUME_RESTORE_TIMEOUT_SECONDS,
        )
