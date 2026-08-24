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

from dataclasses import replace
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components import media_source
from homeassistant.components.media_player import async_process_play_media_url
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
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
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_TEST_SECONDS,
    MAX_SEARCH_LIMIT,
    SOUND_MODE_ANNOUNCE_ONLY,
    SOUND_MODE_MEDIA,
    SOUND_MODE_MUSIC_ASSISTANT,
    SOUND_URL_PATH,
    TEST_SCOPE_ALL,
    TEST_SCOPE_COVER,
    TEST_SCOPE_LIGHT,
    TEST_SCOPE_SOUND,
    TEST_SNAPSHOT_SCENE,
)
from .models import Alarm

if TYPE_CHECKING:
    from datetime import datetime

    from .coordinator import HeroldCoordinator
    from .models import Room

_LOGGER = logging.getLogger(__name__)


def split_output(entity_id: str) -> tuple[str | None, str | None]:
    """Sort a pinned target into the (media_player, satellite) pair."""
    if entity_id.startswith("assist_satellite."):
        return (None, entity_id)
    return (entity_id, None)


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

        An alarm may pin its own target. That is not a nicety: the room
        router will happily hand an alarm to whatever media player the
        active room owns, and an Apple TV is a poor thing to be woken by.
        """
        if alarm.target:
            return split_output(alarm.target)

        room = await self.coordinator.async_get_alarm_room(alarm)
        config = self.coordinator.config
        # Configured overrides are the sleeping setup; an alarm that is
        # explicitly not about sleeping must not inherit them.
        player = (None if alarm.follow_me else config.get(CONF_ALARM_MEDIA_PLAYER)) or (
            room.media_player_entity if room else None
        )
        satellite = (
            None if alarm.follow_me else config.get(CONF_ALARM_SAT_ENTITY)
        ) or (room.sat_entity if room else None)

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
            media_id: str | None = await self._async_resolve_media(
                alarm.sound, player
            )
        else:
            media_id = self.builtin_sound_url(alarm.sound or DEFAULT_BUILTIN_SOUND)
        if media_id is None:
            _LOGGER.warning("No playable alarm sound, skipping the tone")
            return

        try:
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
        except HomeAssistantError as err:
            # The bare player error ("failed to init decoder") says nothing
            # about which speaker refused it, which is the whole question.
            raise HomeAssistantError(
                f"{player} could not play the alarm sound ({media_id}): {err}"
            ) from err

    async def _async_resolve_media(
        self, media_id: str, player: str
    ) -> str | None:
        """Turn an uploaded file's media-source id into a playable URL.

        Files dropped onto the card land in the local media source, whose
        ids only some players understand. Resolving here means every player
        gets a plain URL.
        """
        if not media_source.is_media_source_id(media_id):
            return media_id
        hass = self.coordinator.hass
        try:
            resolved = await media_source.async_resolve_media(
                hass, media_id, player
            )
        except (media_source.Unresolvable, HomeAssistantError) as err:
            _LOGGER.error("Alarm sound %s cannot be resolved: %s", media_id, err)
            return None
        return async_process_play_media_url(hass, resolved.url)

    # -- Music Assistant ---------------------------------------------------

    def _music_assistant_entry(self) -> str | None:
        """The Music Assistant config entry, which its services require."""
        entries = self.coordinator.hass.config_entries.async_entries(
            "music_assistant"
        )
        loaded = [
            entry for entry in entries if entry.state is ConfigEntryState.LOADED
        ]
        return (loaded or entries)[0].entry_id if entries else None

    async def _async_play_music_assistant(self, alarm: Alarm, player: str) -> None:
        """Hand the wake-up media over to Music Assistant."""
        if not alarm.sound:
            _LOGGER.warning("Music Assistant alarm without a media id")
            return
        if "music_assistant" not in self.coordinator.hass.config.components:
            raise HomeAssistantError(
                "Music Assistant is not set up, cannot play the alarm media"
            )
        data: dict[str, Any] = {
            "entity_id": player,
            "media_id": alarm.sound,
            # Never append to whatever was queued last night.
            "enqueue": "replace",
        }
        if alarm.sound_media_type:
            data["media_type"] = alarm.sound_media_type
        await self.coordinator.hass.services.async_call(
            "music_assistant", "play_media", data, blocking=True
        )

    async def async_search_media(
        self, query: str, media_type: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Search Music Assistant so the card can offer real choices.

        Typing a name into a text field and hoping is the worst part of
        configuring music as an alarm; this is what replaces it.
        """
        hass = self.coordinator.hass
        if "music_assistant" not in hass.config.components:
            raise HomeAssistantError("Music Assistant is not set up")
        entry_id = self._music_assistant_entry()
        if entry_id is None:
            raise HomeAssistantError("No Music Assistant configuration found")

        count = min(max(int(limit or DEFAULT_SEARCH_LIMIT), 1), MAX_SEARCH_LIMIT)
        data: dict[str, Any] = {
            "config_entry_id": entry_id,
            "name": query,
            "limit": count,
        }
        if media_type:
            data["media_type"] = [media_type]

        response = await hass.services.async_call(
            "music_assistant",
            "search",
            data,
            blocking=True,
            return_response=True,
        )
        return self._flatten_search(response or {}, count)

    @staticmethod
    def _flatten_search(response: dict, limit: int) -> list[dict[str, Any]]:
        """Reduce the per-type result buckets to one flat, pickable list."""
        buckets = (
            ("playlists", "playlist"),
            ("radio", "radio"),
            ("albums", "album"),
            ("tracks", "track"),
            ("artists", "artist"),
        )
        results: list[dict[str, Any]] = []
        for key, media_type in buckets:
            for item in response.get(key) or []:
                if not isinstance(item, dict) or not item.get("uri"):
                    continue
                artists = item.get("artists") or []
                by = ", ".join(
                    artist.get("name", "")
                    for artist in artists
                    if isinstance(artist, dict)
                )
                results.append(
                    {
                        "uri": item["uri"],
                        "name": item.get("name") or item["uri"],
                        "media_type": item.get("media_type") or media_type,
                        "artist": by or None,
                    }
                )
        return results[:limit]

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

    # -- Testing -----------------------------------------------------------

    async def async_test(
        self,
        alarm: Alarm | None,
        scope: str = TEST_SCOPE_SOUND,
        volume: float | None = None,
        seconds: int | None = None,
        target: str | None = None,
    ) -> dict[str, Any]:
        """Run the alarm's effects once, right now, and undo them again.

        Waiting until 06:30 to find out that the speaker is muted or that
        the wrong blind opens is a bad way to learn it. Lights and blinds
        are snapshotted first and put back afterwards.
        """
        probe = alarm or Alarm(time="00:00")
        if target:
            probe = replace(probe, target=target)
        result: dict[str, Any] = {"scope": scope, "sound": False, "target": None}
        duration = max(1, int(seconds or DEFAULT_TEST_SECONDS))

        if scope in (TEST_SCOPE_SOUND, TEST_SCOPE_ALL):
            player, satellite = await self.async_targets(probe)
            result["sound"] = await self._async_test_sound(probe, volume)
            result["target"] = self.coordinator.describe_alarm_target(probe)
            # The entity ids, not just the label: "it played on the Apple TV"
            # is the answer you actually need when a test sounds wrong.
            result["media_player"] = player
            result["satellite"] = satellite

        wants_light = scope in (TEST_SCOPE_LIGHT, TEST_SCOPE_ALL)
        wants_cover = scope in (TEST_SCOPE_COVER, TEST_SCOPE_ALL)
        if wants_light or wants_cover:
            room = await self.coordinator.async_get_alarm_room(probe)
            entities = list(room.flash_entities) if wants_light and room else []
            if wants_cover:
                entities += self.coordinator.config.get(
                    CONF_ALARM_COVER_ENTITIES
                ) or []
            result["entities"] = entities
            if not entities:
                _LOGGER.warning("Nothing configured to test for scope %s", scope)
            else:
                await self._async_snapshot(entities)
                if wants_light:
                    await self.async_lights(room)
                if wants_cover:
                    await self.async_covers()
                self._schedule_restore(duration)
                result["restore_in"] = duration
        return result

    async def _async_test_sound(
        self, alarm: Alarm, volume: float | None
    ) -> bool:
        """Play one ring at the starting volume, or an explicit one."""
        player, satellite = await self.async_targets(alarm)
        if player is None and satellite is None:
            return False
        if player is None:
            await self._async_announce(satellite, alarm.message)
            return True
        level = (
            round(min(max(float(volume), 0.0), 1.0), 3)
            if volume is not None
            else self.volume_for_ring(alarm, 1)
        )
        async with self.coordinator.volume.announce_at(player, level):
            if alarm.sound_mode != SOUND_MODE_ANNOUNCE_ONLY:
                await self._async_play_sound(alarm, player)
            else:
                await self._async_speak(player, satellite, alarm.message)
        return True

    async def _async_snapshot(self, entities: list[str]) -> None:
        """Remember the current state so the test can be undone."""
        await self._async_try(
            "scene",
            "create",
            {
                "scene_id": TEST_SNAPSHOT_SCENE.split(".", 1)[1],
                "snapshot_entities": entities,
            },
        )

    def _schedule_restore(self, seconds: int) -> None:
        """Put the snapshot back once the user has seen the effect."""

        async def _restore(_now: datetime) -> None:
            await self._async_try(
                "scene", "turn_on", {"entity_id": TEST_SNAPSHOT_SCENE}
            )

        async_call_later(self.coordinator.hass, seconds, _restore)

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
