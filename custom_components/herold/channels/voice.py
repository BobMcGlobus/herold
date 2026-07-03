"""Voice delivery channel: assist satellites with media player TTS fallback."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..const import (
    ALARM_ANNOUNCE_DELAY_SECONDS,
    ALARM_VOICE_PREFIX,
    CHANNEL_VOICE,
    CONF_ENABLE_OFFLINE_FALLBACK,
    CONF_FALLBACK_TTS,
    CONF_PRIMARY_TTS,
    PRIORITY_ALARM,
)
from .base import BaseChannel, ChannelUnavailable

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification

_LOGGER = logging.getLogger(__name__)


class VoiceChannel(BaseChannel):
    """Deliver notifications audibly in the currently occupied room."""

    name = CHANNEL_VOICE

    def __init__(self, offline_capable: bool = False) -> None:
        # True when enable_offline_fallback is set AND a fallback TTS entity
        # is configured (computed by the coordinator at setup time).
        self.offline_capable = offline_capable

    async def deliver(
        self, notification: Notification, coordinator: HeroldCoordinator
    ) -> None:
        """Announce via satellite or speak via TTS on a media player."""
        hass = coordinator.hass
        room = await coordinator.async_get_active_room()

        sat_entity: str | None = None
        media_player_entity: str | None = None
        light_entity = room.light_entity if room else None

        if notification.target_player:
            # Explicit target overrides room detection (original script behavior).
            if notification.target_player.startswith("assist_satellite."):
                sat_entity = notification.target_player
            else:
                media_player_entity = notification.target_player
        elif room is not None:
            sat_entity = room.sat_entity
            media_player_entity = room.media_player_entity
        else:
            _LOGGER.debug(
                "Voice delivery skipped for %s: no occupied voice-capable room",
                notification.id,
            )
            return

        # P4 light flash BEFORE the voice output
        if notification.priority == PRIORITY_ALARM and light_entity:
            await hass.services.async_call(
                "light",
                "turn_on",
                {
                    "entity_id": light_entity,
                    "flash": "short",
                    "brightness": 255,
                    "rgb_color": [255, 0, 0],
                },
                blocking=True,
            )

        if sat_entity:
            if notification.priority == PRIORITY_ALARM:
                await hass.services.async_call(
                    "assist_satellite",
                    "announce",
                    {"entity_id": sat_entity, "message": ALARM_VOICE_PREFIX},
                    blocking=True,
                )
                await asyncio.sleep(ALARM_ANNOUNCE_DELAY_SECONDS)
            await hass.services.async_call(
                "assist_satellite",
                "announce",
                {"entity_id": sat_entity, "message": notification.message},
                blocking=True,
            )
        elif media_player_entity:
            # Media-player-only room (e.g. bathroom with a Sonos Roam)
            tts_entity = self._choose_tts_entity(coordinator)
            await hass.services.async_call(
                "tts",
                "speak",
                {
                    "entity_id": tts_entity,
                    "media_player_entity_id": media_player_entity,
                    "message": notification.message,
                },
                blocking=True,
            )
        else:
            _LOGGER.debug(
                "Voice delivery skipped for %s: no usable output entity",
                notification.id,
            )

    def _choose_tts_entity(self, coordinator: HeroldCoordinator) -> str:
        """Pick a TTS entity: primary online, fallback offline, else fail."""
        config = coordinator.config
        primary = config.get(CONF_PRIMARY_TTS)
        if coordinator.internet_available and primary:
            return primary
        fallback = config.get(CONF_FALLBACK_TTS)
        if config.get(CONF_ENABLE_OFFLINE_FALLBACK) and fallback:
            return fallback
        raise ChannelUnavailable(
            "No usable TTS entity: offline and no offline fallback configured"
        )
