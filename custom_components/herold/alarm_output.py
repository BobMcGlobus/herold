"""Everything an alarm does to the room: sound, light, blinds, routine.

A spoken sentence is not a wake-up signal — it has no attack and no
frequency peaks, which is why alarms used to be sleepable-through. Alarms
therefore play an actual tone through a media player and only speak the
message afterwards, if asked to.

That also decides the output preference: a satellite can announce text but
cannot play media, so the speaker wins unless the alarm explicitly wants a
conversational snooze.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import (
    CARD_STATIC_URL,
    CONF_ALARM_COVER_ENTITIES,
    CONF_ALARM_COVER_POSITION,
    CONF_ALARM_MEDIA_PLAYER,
    CONF_ALARM_ROUTINE,
    CONF_ALARM_SAT_ENTITY,
    CONF_ALARM_VOLUME_MAX,
    CONF_ALARM_VOLUME_MIN,
    CONF_PRIMARY_TTS,
    DEFAULT_ALARM_COVER_POSITION,
    DEFAULT_ALARM_VOLUME_MAX,
    DEFAULT_ALARM_VOLUME_MIN,
    DEFAULT_BUILTIN_SOUND,
    SOUND_MODE_ANNOUNCE_ONLY,
    SOUND_MODE_MEDIA,
    SOUND_MODE_MUSIC_ASSISTANT,
    SOUND_URL_PATH,
)

if TYPE_CHECKING:
    from .coordinator import HeroldCoordinator
    from .models import Alarm, Room

_LOGGER = logging.getLogger(__name__)


class AlarmOutput:
    """Drives speakers, lights and blinds for the alarm clock."""

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator

    # -- Targets -----------------------------------------------------------

    async def async_targets(self, alarm: Alarm) -> tuple[str | None, str | None]:
        """Return (media_player, satellite) to use for this alarm.

        The speaker is preferred: it can play a tone, the satellite cannot.
        A satellite only wins when the alarm wants to be snoozed by voice,
        because that needs a conversation.
        """
        room = await self.coordinator.async_get_alarm_room()
        config = self.coordinator.config
        player = config.get(CONF_ALARM_MEDIA_PLAYER) or (
            room.media_player_entity if room else None
        )
        satellite = config.get(CONF_ALARM_SAT_ENTITY) or (
            room.sat_entity if room else None
        )

        if alarm.voice_snooze and satellite:
            return (None, satellite)
        return (player, satellite)

    def volume_for_ring(self, alarm: Alarm, ring: int) -> float:
        """Volume for this ring, between the configured floor and ceiling.

        Absolute rather than a fraction of the room's "loud" level: a
        speaker left at 5 % overnight must not swallow the alarm.
        """
        config = self.coordinator.config
        floor = float(config.get(CONF_ALARM_VOLUME_MIN, DEFAULT_ALARM_VOLUME_MIN))
        ceiling = float(config.get(CONF_ALARM_VOLUME_MAX, DEFAULT_ALARM_VOLUME_MAX))
        floor, ceiling = min(floor, ceiling), max(floor, ceiling)
        ramp: tuple[float, ...] = alarm.profile["ramp"]
        factor = ramp[min(max(ring - 1, 0), len(ramp) - 1)]
        return round(floor + (ceiling - floor) * factor, 3)

    # -- Ringing -----------------------------------------------------------

    async def async_ring(self, alarm: Alarm, ring: int) -> bool:
        """Play one ring. Returns False if there was nothing to play on."""
        player, satellite = await self.async_targets(alarm)
        if player is None and satellite is None:
            return False

        if player is None:
            # Satellite only — spoken text is all it can do.
            await self._async_announce(satellite, alarm.message)
            return True

        volume = self.volume_for_ring(alarm, ring)
        async with self.coordinator.volume.announce_at(player, volume):
            if alarm.sound_mode != SOUND_MODE_ANNOUNCE_ONLY:
                await self._async_play_sound(alarm, player)
            if alarm.announce or alarm.sound_mode == SOUND_MODE_ANNOUNCE_ONLY:
                await self._async_speak(player, satellite, alarm.message)
        return True

    async def _async_play_sound(self, alarm: Alarm, player: str) -> None:
        """Play the configured wake-up sound on the speaker."""
        if alarm.sound_mode == SOUND_MODE_MUSIC_ASSISTANT:
            await self._async_play_music_assistant(alarm, player)
            return

        if alarm.sound_mode == SOUND_MODE_MEDIA and alarm.sound:
            media_id: str | None = alarm.sound
        else:
            media_id = self.builtin_sound_url(alarm.sound or DEFAULT_BUILTIN_SOUND)
        if media_id is None:
            _LOGGER.warning("No playable alarm sound, skipping the tone")
            return

        await self.coordinator.hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": player,
                "media_content_id": media_id,
                "media_content_type": "music",
            },
            blocking=True,
        )

    async def _async_play_music_assistant(self, alarm: Alarm, player: str) -> None:
        """Hand the wake-up media over to Music Assistant."""
        if not alarm.sound:
            _LOGGER.warning("Music Assistant alarm without a media id")
            return
        if "music_assistant" not in self.coordinator.hass.config.components:
            raise HomeAssistantError(
                "Music Assistant is not set up, cannot play the alarm media"
            )
        await self.coordinator.hass.services.async_call(
            "music_assistant",
            "play_media",
            {"entity_id": player, "media_id": alarm.sound},
            blocking=True,
        )

    def builtin_sound_url(self, name: str) -> str | None:
        """Absolute URL of a built-in tone, as media players need one."""
        path = f"{CARD_STATIC_URL}/{SOUND_URL_PATH}/{name}.wav"
        try:
            return f"{get_url(self.coordinator.hass)}{path}"
        except NoURLAvailableError:
            _LOGGER.debug("No reachable Home Assistant URL for %s", path)
            return None

    async def _async_speak(
        self, player: str | None, satellite: str | None, message: str
    ) -> None:
        """Speak the wake message after the tone."""
        if satellite:
            await self._async_announce(satellite, message)
            return
        tts_entity = self.coordinator.config.get(CONF_PRIMARY_TTS)
        if not player or not tts_entity:
            return
        await self.coordinator.hass.services.async_call(
            "tts",
            "speak",
            {
                "entity_id": tts_entity,
                "media_player_entity_id": player,
                "message": message,
            },
            blocking=True,
        )

    async def _async_announce(self, satellite: str | None, message: str) -> None:
        if not satellite:
            return
        await self.coordinator.hass.services.async_call(
            "assist_satellite",
            "announce",
            {"entity_id": satellite, "message": message},
            blocking=True,
        )

    # -- Pre-alarm phase ---------------------------------------------------

    async def async_lights(self, room: Room | None) -> None:
        """Fade the sleeping area's lights up — a sunrise, not a strobe."""
        if room is None:
            return
        for entity_id in room.flash_entities:
            domain = "scene" if entity_id.startswith("scene.") else "light"
            data: dict[str, Any] = {"entity_id": entity_id}
            if domain == "light":
                data.update({"brightness_pct": 60, "transition": 60})
            await self._async_try(domain, "turn_on", data)

    async def async_covers(self) -> None:
        """Open the configured blinds to the configured position."""
        config = self.coordinator.config
        covers: list[str] = config.get(CONF_ALARM_COVER_ENTITIES) or []
        if not covers:
            return
        position = int(
            config.get(CONF_ALARM_COVER_POSITION, DEFAULT_ALARM_COVER_POSITION)
        )
        for entity_id in covers:
            await self._async_try(
                "cover",
                "set_cover_position",
                {"entity_id": entity_id, "position": position},
            )

    async def async_routine(self, alarm: Alarm) -> None:
        """Run the good-morning routine once the user is really up."""
        entity_id = alarm.routine or self.coordinator.config.get(CONF_ALARM_ROUTINE)
        if not entity_id:
            return
        _LOGGER.debug("Running good morning routine %s", entity_id)
        await self._async_try(
            "homeassistant", "turn_on", {"entity_id": entity_id}
        )

    async def _async_try(
        self, domain: str, service: str, data: dict[str, Any]
    ) -> None:
        """Call a service without letting one broken entity stop the alarm."""
        try:
            await self.coordinator.hass.services.async_call(
                domain, service, data, blocking=False
            )
        except HomeAssistantError as err:
            _LOGGER.warning("%s.%s failed for %s: %s", domain, service, data, err)
