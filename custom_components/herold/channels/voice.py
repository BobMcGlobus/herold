"""Voice delivery channel: assist satellites with media player TTS fallback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
from ..quiet_hours import level_for
from .base import BaseChannel, ChannelUnavailable

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification, Query, Room

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class VoiceTarget:
    """Everything one announcement needs, resolved once per delivery."""

    sat_entity: str | None
    media_player_entity: str | None
    flash_entities: list[str]
    room: Room | None

    def volume_for(self, level: str) -> tuple[str | None, float | None]:
        """Return (player to adjust, volume) for the given level."""
        if self.room is None:
            return (None, None)
        # A satellite plays through its own media player entity, so the room's
        # media player is the volume target in both cases when configured.
        entity_id = self.media_player_entity or self.room.media_player_entity
        if entity_id is None:
            return (None, None)
        return (entity_id, self.room.volume_for(level))


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
        target = await self._resolve(notification.target_player, coordinator)
        await self._speak_out(
            coordinator,
            target,
            notification.message,
            notification.priority,
            query=None,
        )

    async def deliver_query(
        self, query: Query, coordinator: HeroldCoordinator
    ) -> None:
        """Start a conversation on a satellite, or speak the question.

        In media-player-only rooms the question is spoken via TTS (original
        script behavior) — the answer then has to come through another
        channel (Telegram buttons), which the dispatcher accounts for.
        """
        target = await self._resolve(query.target_player, coordinator)
        await self._speak_out(
            coordinator, target, query.question, query.priority, query=query
        )

    async def _speak_out(
        self,
        coordinator: HeroldCoordinator,
        target: VoiceTarget,
        text: str,
        priority: int,
        query: Query | None,
    ) -> None:
        """Run the flash hook and the actual voice output at the right volume."""
        if priority == PRIORITY_ALARM:
            await self._flash(coordinator, target.flash_entities)

        level = level_for(priority, coordinator.config)
        player, volume = target.volume_for(level)

        async with coordinator.volume.announce_at(player, volume):
            if target.sat_entity:
                await self._alarm_preannounce(
                    coordinator, target.sat_entity, priority
                )
                if query is not None:
                    await self._start_conversation(
                        coordinator, target.sat_entity, query
                    )
                else:
                    await coordinator.hass.services.async_call(
                        "assist_satellite",
                        "announce",
                        {"entity_id": target.sat_entity, "message": text},
                        blocking=True,
                    )
            elif target.media_player_entity:
                # Media-player-only room (e.g. bathroom with a Sonos Roam)
                await self._speak(
                    coordinator, target.media_player_entity, text
                )
            else:
                raise ChannelUnavailable(
                    "Active room has no usable output entity"
                )

    async def _resolve(
        self, target_player: str | None, coordinator: HeroldCoordinator
    ) -> VoiceTarget:
        """Pick the output entities for this delivery."""
        room = await coordinator.async_get_active_room()
        flash_entities = room.flash_entities if room else []

        if target_player:
            # Explicit target overrides room detection (original script
            # behavior); the active room still provides the P4 flash target.
            if target_player.startswith("assist_satellite."):
                return VoiceTarget(target_player, None, flash_entities, room)
            return VoiceTarget(None, target_player, flash_entities, room)
        if room is None:
            # Raise instead of silently skipping so the delivery result
            # records the miss (visible in the last_delivery sensor errors).
            raise ChannelUnavailable("No occupied voice-capable room")
        return VoiceTarget(
            room.sat_entity, room.media_player_entity, flash_entities, room
        )

    async def _start_conversation(
        self, coordinator: HeroldCoordinator, sat_entity: str, query: Query
    ) -> None:
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
