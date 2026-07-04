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
    QUERY_MODE_CHOICE,
)
from .base import BaseChannel, ChannelUnavailable

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification, Query

_LOGGER = logging.getLogger(__name__)


class VoiceChannel(BaseChannel):
    """Deliver notifications and queries audibly in the active room."""

    name = CHANNEL_VOICE

    def __init__(self, offline_capable: bool = False) -> None:
        # True when enable_offline_fallback is set AND a fallback TTS entity
        # is configured (computed by the coordinator at setup time).
        self.offline_capable = offline_capable

    async def deliver(
        self, notification: Notification, coordinator: HeroldCoordinator
    ) -> None:
        """Announce via satellite or speak via TTS on a media player."""
        outputs = await self._resolve_outputs(
            notification.target_player, coordinator
        )
        if outputs is None:
            # Raise instead of silently skipping so the delivery result
            # records the miss (visible in the last_delivery sensor errors).
            raise ChannelUnavailable("No occupied voice-capable room")
        sat_entity, media_player_entity, flash_entities = outputs

        if notification.priority == PRIORITY_ALARM:
            await self._flash(coordinator, flash_entities)

        if sat_entity:
            await self._alarm_preannounce(
                coordinator, sat_entity, notification.priority
            )
            await coordinator.hass.services.async_call(
                "assist_satellite",
                "announce",
                {"entity_id": sat_entity, "message": notification.message},
                blocking=True,
            )
        elif media_player_entity:
            # Media-player-only room (e.g. bathroom with a Sonos Roam)
            await self._speak(
                coordinator, media_player_entity, notification.message
            )
        else:
            raise ChannelUnavailable("Active room has no usable output entity")

    async def deliver_query(
        self, query: Query, coordinator: HeroldCoordinator
    ) -> None:
        """Start a conversation on a satellite, or speak the question.

        In media-player-only rooms the question is spoken via TTS (original
        script behavior) — the answer then has to come through another
        channel (Telegram buttons), which the dispatcher accounts for.
        """
        outputs = await self._resolve_outputs(query.target_player, coordinator)
        if outputs is None:
            raise ChannelUnavailable("No occupied voice-capable room")
        sat_entity, media_player_entity, flash_entities = outputs

        if query.priority == PRIORITY_ALARM:
            await self._flash(coordinator, flash_entities)

        if sat_entity:
            await self._alarm_preannounce(coordinator, sat_entity, query.priority)
            data = {"entity_id": sat_entity, "start_message": query.question}
            if query.mode == QUERY_MODE_CHOICE and query.choices:
                data["extra_system_prompt"] = (
                    "The user was just asked a question with predefined "
                    f"answer options: {', '.join(query.choices)}. Map their "
                    "spoken reply to one of these options."
                )
            await coordinator.hass.services.async_call(
                "assist_satellite", "start_conversation", data, blocking=True
            )
        elif media_player_entity:
            await self._speak(coordinator, media_player_entity, query.question)
        else:
            raise ChannelUnavailable("Active room has no usable output entity")

    async def _resolve_outputs(
        self, target_player: str | None, coordinator: HeroldCoordinator
    ) -> tuple[str | None, str | None, list[str]] | None:
        """Return (sat, media_player, flash_entities) or None if no target."""
        room = await coordinator.async_get_active_room()
        flash_entities = room.flash_entities if room else []

        if target_player:
            # Explicit target overrides room detection (original script
            # behavior); the active room still provides the P4 flash target.
            if target_player.startswith("assist_satellite."):
                return (target_player, None, flash_entities)
            return (None, target_player, flash_entities)
        if room is None:
            return None
        return (room.sat_entity, room.media_player_entity, flash_entities)

    async def _flash(
        self, coordinator: HeroldCoordinator, flash_entities: list[str]
    ) -> None:
        """P4 visual alarm: flash lights red, activate scenes as-is."""
        for entity_id in flash_entities:
            if entity_id.startswith("scene."):
                await coordinator.hass.services.async_call(
                    "scene", "turn_on", {"entity_id": entity_id}, blocking=True
                )
            else:
                await coordinator.hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": entity_id,
                        "flash": "short",
                        "brightness": 255,
                        "rgb_color": [255, 0, 0],
                    },
                    blocking=True,
                )

    async def _alarm_preannounce(
        self, coordinator: HeroldCoordinator, sat_entity: str, priority: int
    ) -> None:
        """P4 warning announcement before the actual message."""
        if priority != PRIORITY_ALARM:
            return
        await coordinator.hass.services.async_call(
            "assist_satellite",
            "announce",
            {"entity_id": sat_entity, "message": ALARM_VOICE_PREFIX},
            blocking=True,
        )
        await asyncio.sleep(ALARM_ANNOUNCE_DELAY_SECONDS)

    async def _speak(
        self, coordinator: HeroldCoordinator, media_player_entity: str, text: str
    ) -> None:
        """Speak text on a media player using the TTS chain."""
        tts_entity = self._choose_tts_entity(coordinator)
        await coordinator.hass.services.async_call(
            "tts",
            "speak",
            {
                "entity_id": tts_entity,
                "media_player_entity_id": media_player_entity,
                "message": text,
            },
            blocking=True,
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
