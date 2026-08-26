"""The ring loop: songs, silence on dismiss, getting up, voice snooze."""

from types import SimpleNamespace

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.herold.alarm import AlarmManager
from custom_components.herold.alarm_output import AlarmOutput
from custom_components.herold.const import (
    ALARM_STATUS_RINGING,
    ALARM_STATUS_SNOOZED,
    CONF_ALARM_BED_SENSOR,
    CONF_ALARM_MEDIA_PLAYER,
    CONF_ALARM_SAT_ENTITY,
    CONF_ALARM_UP_SECONDS,
    SOUND_MODE_MEDIA,
    VOICE_ANSWER_DISMISS,
    VOICE_ANSWER_SNOOZE,
)
from custom_components.herold.models import Alarm
from custom_components.herold.volume import VolumeController

PLAYER = "media_player.bedroom"
SATELLITE = "assist_satellite.bedroom"


@pytest.fixture
def calls(hass) -> list[tuple[str, str, dict]]:
    """Record the service calls the alarm makes."""
    recorded: list[tuple[str, str, dict]] = []

    def _record(domain: str, service: str) -> None:
        async def _handler(call):
            recorded.append((domain, service, dict(call.data)))

        hass.services.async_register(domain, service, _handler)

    for domain, service in (
        ("media_player", "play_media"),
        ("media_player", "volume_set"),
        ("media_player", "media_stop"),
        ("assist_satellite", "announce"),
        ("homeassistant", "turn_on"),
    ):
        _record(domain, service)
    return recorded


@pytest.fixture
async def manager(hass):
    """An alarm manager wired to a coordinator stub with one speaker."""
    hass.config.internal_url = "http://homeassistant.local:8123"
    hass.states.async_set(
        PLAYER, "idle", {"supported_features": 4, "volume_level": 0.2}
    )
    notified: list[int] = []
    coordinator = SimpleNamespace(
        hass=hass,
        entry=SimpleNamespace(entry_id="test"),
        config={CONF_ALARM_MEDIA_PLAYER: PLAYER},
        store=SimpleNamespace(alarms={}, async_schedule_save=lambda: None),
        volume=VolumeController(hass),
        in_bed=False,
        describe_alarm_target=lambda alarm=None: "Bedroom",
        add_history=lambda *args, **kwargs: None,
        notified=notified,
    )

    async def _room(alarm=None):
        return None

    coordinator.async_get_alarm_room = _room
    coordinator.alarm_output = AlarmOutput(coordinator)
    instance = AlarmManager(coordinator)
    # Count notifications instead of dispatching to entities that do not
    # exist in this stub.
    instance._notify_change = lambda: notified.append(1)
    yield instance
    await instance.async_shutdown()


def _add(manager: AlarmManager, **fields) -> Alarm:
    alarm = Alarm(time="07:00", **fields)
    manager.alarms[alarm.id] = alarm
    return alarm


# -- The card has to hear about it immediately -----------------------------


async def test_the_ring_is_announced_before_the_sound_plays(
    hass, manager: AlarmManager, calls
) -> None:
    """play_media blocks until the player starts; the card must not wait."""
    order: list[str] = []

    async def _slow_play(call):
        order.append("played")

    hass.services.async_register("media_player", "play_media", _slow_play)
    manager._notify_change = lambda: order.append("notified")

    alarm = _add(manager)
    await manager._async_ring(alarm)
    await hass.async_block_till_done()
    assert order.index("notified") < order.index("played")


async def test_a_dismiss_during_playback_still_repaints(
    hass, manager: AlarmManager
) -> None:
    """Dismissing mid-ring used to return without telling anyone."""
    alarm = _add(manager)

    async def _dismiss_midway(call):
        alarm.status = "done"

    hass.services.async_register("media_player", "play_media", _dismiss_midway)
    manager.coordinator.notified.clear()
    await manager._async_ring(alarm)
    await hass.async_block_till_done()
    assert len(manager.coordinator.notified) >= 2


# -- Songs must not be restarted every 45 seconds --------------------------


async def test_a_song_is_started_once_not_on_every_ring(
    hass, manager: AlarmManager, calls
) -> None:
    """Re-issuing play_media mid-track restarts it or skips to the next."""
    alarm = _add(
        manager, sound_mode=SOUND_MODE_MEDIA, sound="https://x/song.mp3"
    )
    await manager.coordinator.alarm_output.async_ring(alarm, 1)
    hass.states.async_set(
        PLAYER, "playing", {"supported_features": 4, "volume_level": 0.4}
    )
    await manager.coordinator.alarm_output.async_ring(alarm, 2)
    await hass.async_block_till_done()

    plays = [call for call in calls if call[1] == "play_media"]
    assert len(plays) == 1


async def test_later_rings_still_turn_a_song_up(
    hass, manager: AlarmManager, calls
) -> None:
    """The ramp is the only thing an ongoing song should get."""
    manager.coordinator.config |= {"alarm_volume_min": 0.3, "alarm_volume_max": 0.9}
    alarm = _add(
        manager, sound_mode=SOUND_MODE_MEDIA, sound="https://x/song.mp3"
    )
    await manager.coordinator.alarm_output.async_ring(alarm, 1)
    hass.states.async_set(
        PLAYER, "playing", {"supported_features": 4, "volume_level": 0.3}
    )
    await manager.coordinator.alarm_output.async_ring(alarm, 4)
    await hass.async_block_till_done()

    volumes = [call[2]["volume_level"] for call in calls if call[1] == "volume_set"]
    assert len(volumes) >= 2
    assert volumes[-1] > volumes[0]


async def test_a_song_keeps_its_volume_between_rings(
    hass, manager: AlarmManager, calls
) -> None:
    """announce_at restores as soon as the player idles — mid-song."""
    alarm = _add(
        manager, sound_mode=SOUND_MODE_MEDIA, sound="https://x/song.mp3"
    )
    await manager.coordinator.alarm_output.async_ring(alarm, 1)
    await hass.async_block_till_done()
    # 0.2 was the level before the alarm; it must not come back on its own.
    volumes = [call[2]["volume_level"] for call in calls if call[1] == "volume_set"]
    assert 0.2 not in volumes


# -- Stopping actually stops ------------------------------------------------


async def test_dismissing_stops_the_music(
    hass, manager: AlarmManager, calls
) -> None:
    alarm = _add(
        manager, sound_mode=SOUND_MODE_MEDIA, sound="https://x/song.mp3", days=["mon"]
    )
    await manager.coordinator.alarm_output.async_ring(alarm, 1)
    hass.states.async_set(PLAYER, "playing", {"supported_features": 4})
    await manager.async_dismiss(alarm.id)
    await hass.async_block_till_done()
    assert any(call[1] == "media_stop" for call in calls)


async def test_snoozing_stops_the_music(
    hass, manager: AlarmManager, calls
) -> None:
    alarm = _add(
        manager, sound_mode=SOUND_MODE_MEDIA, sound="https://x/song.mp3"
    )
    alarm.status = ALARM_STATUS_RINGING
    await manager.coordinator.alarm_output.async_ring(alarm, 1)
    hass.states.async_set(PLAYER, "playing", {"supported_features": 4})
    await manager.async_snooze(alarm.id)
    await hass.async_block_till_done()
    assert any(call[1] == "media_stop" for call in calls)


async def test_stopping_gives_the_volume_back(
    hass, manager: AlarmManager, calls
) -> None:
    alarm = _add(
        manager, sound_mode=SOUND_MODE_MEDIA, sound="https://x/song.mp3", days=["mon"]
    )
    await manager.coordinator.alarm_output.async_ring(alarm, 1)
    hass.states.async_set(PLAYER, "playing", {"supported_features": 4})
    await manager.async_dismiss(alarm.id)
    await hass.async_block_till_done()
    volumes = [call[2]["volume_level"] for call in calls if call[1] == "volume_set"]
    assert volumes[-1] == 0.2


# -- Snooze countdown -------------------------------------------------------


async def test_a_snooze_records_how_long_it_lasts(
    hass, manager: AlarmManager
) -> None:
    """Without this the card can only say "snoozed", not how much longer."""
    alarm = _add(manager)
    alarm.status = ALARM_STATUS_RINGING
    await manager.async_snooze(alarm.id, minutes=7)
    assert alarm.snooze_seconds == 420
    assert alarm.status == ALARM_STATUS_SNOOZED


# -- Getting up -------------------------------------------------------------


async def test_leaving_the_bed_dismisses_a_ringing_alarm(
    hass, manager: AlarmManager
) -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    manager.coordinator.config |= {CONF_ALARM_UP_SECONDS: 5}
    alarm = _add(manager, days=["mon"])
    alarm.status = ALARM_STATUS_RINGING
    manager.async_note_out_of_bed()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    assert alarm.status != ALARM_STATUS_RINGING


async def test_getting_back_into_bed_cancels_the_dismiss(
    hass, manager: AlarmManager
) -> None:
    """Rolling over drops an occupancy sensor; that must not end the alarm."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    manager.coordinator.config |= {CONF_ALARM_UP_SECONDS: 5}
    alarm = _add(manager, days=["mon"])
    alarm.status = ALARM_STATUS_RINGING
    manager.async_note_out_of_bed()
    manager.coordinator.in_bed = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    assert alarm.status == ALARM_STATUS_RINGING


async def test_an_empty_bed_with_nothing_ringing_does_nothing(
    hass, manager: AlarmManager
) -> None:
    """Getting up at 3 a.m. must not cancel tomorrow's alarm."""
    alarm = _add(manager, days=["mon"])
    manager.async_note_out_of_bed()
    assert manager._up_check is None
    assert alarm.id in manager.alarms


async def test_the_bed_sensor_is_watched(hass) -> None:
    """The listener is the whole feature; without it nothing else matters."""
    from custom_components.herold.coordinator import HeroldCoordinator

    entry = SimpleNamespace(entry_id="test", data={}, options={})
    coordinator = HeroldCoordinator(hass, entry)
    coordinator.config = {CONF_ALARM_BED_SENSOR: "binary_sensor.bed"}
    seen: list[str] = []
    coordinator.alarms = SimpleNamespace(
        async_note_out_of_bed=lambda: seen.append("checked")
    )
    hass.states.async_set("binary_sensor.bed", "on")
    coordinator._async_bed_changed(
        SimpleNamespace(data={"new_state": hass.states.get("binary_sensor.bed")})
    )
    assert seen == []
    hass.states.async_set("binary_sensor.bed", "off")
    coordinator._async_bed_changed(
        SimpleNamespace(data={"new_state": hass.states.get("binary_sensor.bed")})
    )
    assert seen == ["checked"]


# -- Voice snooze -----------------------------------------------------------


async def test_voice_snooze_asks_a_question(hass, manager: AlarmManager) -> None:
    """Announcing and then listening for nothing is not a voice snooze."""
    asked: list[dict] = []

    async def _ask(call):
        asked.append(dict(call.data))
        return {"id": VOICE_ANSWER_SNOOZE, "sentence": "schlummern"}

    hass.services.async_register(
        "assist_satellite", "ask_question", _ask, supports_response="only"
    )
    manager.coordinator.config |= {CONF_ALARM_SAT_ENTITY: SATELLITE}
    alarm = _add(manager, voice_snooze=True)
    answer = await manager.coordinator.alarm_output.async_ask_snooze(alarm)
    assert answer == VOICE_ANSWER_SNOOZE
    assert asked[0]["entity_id"] == SATELLITE
    ids = {item["id"] for item in asked[0]["answers"]}
    assert ids == {VOICE_ANSWER_SNOOZE, VOICE_ANSWER_DISMISS}


async def test_a_spoken_snooze_actually_snoozes(
    hass, manager: AlarmManager
) -> None:
    async def _ask(call):
        return {"id": VOICE_ANSWER_SNOOZE}

    hass.services.async_register(
        "assist_satellite", "ask_question", _ask, supports_response="only"
    )
    manager.coordinator.config |= {CONF_ALARM_SAT_ENTITY: SATELLITE}
    alarm = _add(manager, voice_snooze=True)
    alarm.status = ALARM_STATUS_RINGING
    assert await manager._async_voice_decision(alarm) is True
    assert alarm.status == ALARM_STATUS_SNOOZED


async def test_a_spoken_dismiss_ends_the_alarm(
    hass, manager: AlarmManager
) -> None:
    async def _ask(call):
        return {"id": VOICE_ANSWER_DISMISS}

    hass.services.async_register(
        "assist_satellite", "ask_question", _ask, supports_response="only"
    )
    manager.coordinator.config |= {CONF_ALARM_SAT_ENTITY: SATELLITE}
    alarm = _add(manager, voice_snooze=True, days=["mon"])
    alarm.status = ALARM_STATUS_RINGING
    assert await manager._async_voice_decision(alarm) is True
    assert alarm.status != ALARM_STATUS_RINGING


async def test_voice_snooze_without_the_service_is_survivable(
    hass, manager: AlarmManager, caplog
) -> None:
    """Older Home Assistants have no ask_question; say so, do not crash."""
    manager.coordinator.config |= {CONF_ALARM_SAT_ENTITY: SATELLITE}
    alarm = _add(manager, voice_snooze=True)
    assert await manager.coordinator.alarm_output.async_ask_snooze(alarm) is None
    assert "ask_question" in caplog.text


async def test_a_refused_spoken_snooze_keeps_ringing(
    hass, manager: AlarmManager
) -> None:
    """Budget spent: the alarm must not fall silent because you asked."""

    async def _ask(call):
        return {"id": VOICE_ANSWER_SNOOZE}

    hass.services.async_register(
        "assist_satellite", "ask_question", _ask, supports_response="only"
    )
    manager.coordinator.config |= {CONF_ALARM_SAT_ENTITY: SATELLITE}
    alarm = _add(manager, voice_snooze=True, urgency="insistent")
    alarm.status = ALARM_STATUS_RINGING
    alarm.snoozes = 1  # insistent grants exactly one
    with pytest.raises(HomeAssistantError):
        await manager.async_snooze(alarm.id)
    assert await manager._async_voice_decision(alarm) is False
    assert alarm.status == ALARM_STATUS_RINGING
