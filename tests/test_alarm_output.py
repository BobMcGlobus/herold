"""Wake-up media: uploaded files, Music Assistant, and the test run."""

from datetime import timedelta
from types import SimpleNamespace

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.herold.alarm_output import AlarmOutput
from custom_components.herold.const import (
    CONF_ALARM_COVER_ENTITIES,
    CONF_ALARM_MEDIA_PLAYER,
    CONF_ALARM_SAT_ENTITY,
    TEST_SCOPE_LIGHT,
    TEST_SCOPE_SOUND,
    TEST_SNAPSHOT_SCENE,
)
from custom_components.herold.models import Alarm, Room
from custom_components.herold.volume import VolumeController

BEDROOM = Room(
    name="Bedroom",
    occupancy_entities=["binary_sensor.bedroom"],
    media_player_entity="media_player.bedroom",
    flash_entities=["light.bedside"],
)


@pytest.fixture
def calls(hass) -> list[tuple[str, str, dict]]:
    """Record every service call the output makes."""
    recorded: list[tuple[str, str, dict]] = []

    def _record(domain: str, service: str) -> None:
        async def _handler(call):
            recorded.append((domain, service, dict(call.data)))

        hass.services.async_register(domain, service, _handler)

    for domain, service in (
        ("media_player", "play_media"),
        ("media_player", "volume_set"),
        ("music_assistant", "play_media"),
        ("scene", "create"),
        ("scene", "turn_on"),
        ("light", "turn_on"),
        ("cover", "set_cover_position"),
    ):
        _record(domain, service)
    return recorded


async def _finish_restore(hass, seconds: int = 5) -> None:
    """Let the scheduled snapshot restore run; otherwise it lingers."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


@pytest.fixture
def output(hass) -> AlarmOutput:
    """An AlarmOutput on a coordinator stub with a bedroom speaker."""
    # Built-in tones are served over HTTP, so the output needs a base URL.
    hass.config.internal_url = "http://homeassistant.local:8123"
    coordinator = SimpleNamespace(
        hass=hass,
        config={},
        volume=VolumeController(hass),
        describe_alarm_target=lambda alarm=None: "Bedroom",
    )

    async def _room(alarm=None):
        return BEDROOM

    coordinator.async_get_alarm_room = _room
    return AlarmOutput(coordinator)


# -- Where it rings --------------------------------------------------------


async def test_pinned_target_beats_the_room_router(
    hass, output: AlarmOutput
) -> None:
    """The room router will happily pick a TV; a pinned target must win."""
    alarm = Alarm(time="07:00", target="media_player.bedside")
    assert await output.async_targets(alarm) == ("media_player.bedside", None)


async def test_a_pinned_satellite_is_not_treated_as_a_speaker(
    hass, output: AlarmOutput
) -> None:
    alarm = Alarm(time="07:00", target="assist_satellite.desk")
    assert await output.async_targets(alarm) == (None, "assist_satellite.desk")


async def test_follow_me_ignores_the_sleeping_setup(
    hass, output: AlarmOutput
) -> None:
    """A nap on the couch must not inherit the bedroom overrides."""
    output.coordinator.config = {
        CONF_ALARM_MEDIA_PLAYER: "media_player.bedside",
        CONF_ALARM_SAT_ENTITY: "assist_satellite.bedside",
    }
    player, satellite = await output.async_targets(
        Alarm(time="07:00", follow_me=True)
    )
    assert player == "media_player.bedroom"  # the active room's own speaker
    assert satellite is None


async def test_a_normal_alarm_still_uses_the_configured_speaker(
    hass, output: AlarmOutput
) -> None:
    output.coordinator.config = {CONF_ALARM_MEDIA_PLAYER: "media_player.bedside"}
    player, _satellite = await output.async_targets(Alarm(time="07:00"))
    assert player == "media_player.bedside"


async def test_the_test_run_reports_the_entity_it_used(
    hass, output: AlarmOutput, calls
) -> None:
    """"It played on the Apple TV" is the answer a test has to give."""
    result = await output.async_test(None, target="media_player.livingroom_tv")
    await hass.async_block_till_done()
    assert result["media_player"] == "media_player.livingroom_tv"
    assert result["satellite"] is None


async def test_a_refusing_player_does_not_fail_the_test_silently(
    hass, output: AlarmOutput
) -> None:
    """A red toast is not a diagnosis; the result has to say what to do."""

    async def _refuse(call):
        raise HomeAssistantError("Failed to stream media to the Apple TV")

    hass.services.async_register("media_player", "play_media", _refuse)
    hass.states.async_set(
        "media_player.livingroom", "idle", {"device_class": "tv"}
    )
    result = await output.async_test(None, target="media_player.livingroom")
    assert result["sound"] is False
    assert "Apple TV" in result["error"]
    assert "Fernseher" in result["hint"]


async def test_a_refusing_player_falls_back_to_speech_when_ringing(
    hass, output: AlarmOutput, caplog
) -> None:
    """Fifteen silent rings is the worst possible failure mode."""
    spoken: list[dict] = []

    async def _refuse(call):
        raise HomeAssistantError("Failed to stream media")

    async def _announce(call):
        spoken.append(dict(call.data))

    hass.services.async_register("media_player", "play_media", _refuse)
    hass.services.async_register("assist_satellite", "announce", _announce)

    alarm = Alarm(time="07:00", target="media_player.livingroom")
    output.coordinator.config = {CONF_ALARM_SAT_ENTITY: "assist_satellite.bed"}
    # A pinned player with no satellite of its own still reaches the
    # configured one through _async_speak.
    played = await output.async_ring(alarm, 1)
    assert played is True
    assert "falling back to speech" in caplog.text


def test_only_televisions_are_flagged(hass) -> None:
    from custom_components.herold.alarm_output import is_display

    hass.states.async_set("media_player.tv", "off", {"device_class": "tv"})
    hass.states.async_set("media_player.sonos", "idle", {"device_class": "speaker"})
    hass.states.async_set("media_player.plain", "idle", {})
    assert is_display(hass, "media_player.tv") is True
    assert is_display(hass, "media_player.sonos") is False
    assert is_display(hass, "media_player.plain") is False
    assert is_display(hass, "media_player.gone") is False
    assert is_display(hass, None) is False


# -- Uploaded files --------------------------------------------------------


async def test_plain_urls_are_passed_through(hass, output: AlarmOutput) -> None:
    """Nothing to resolve — a URL is already playable."""
    url = "https://example.invalid/wake.mp3"
    assert await output._async_resolve_media(url, "media_player.bedroom") == url


async def test_unresolvable_upload_does_not_raise(
    hass, output: AlarmOutput, caplog
) -> None:
    """A deleted file must not take the whole ring down with it."""
    resolved = await output._async_resolve_media(
        "media-source://media_source/local/gone.mp3", "media_player.bedroom"
    )
    assert resolved is None
    assert "cannot be resolved" in caplog.text


# -- Music Assistant -------------------------------------------------------


async def test_music_assistant_gets_type_and_replaces_the_queue(
    hass, output: AlarmOutput, calls
) -> None:
    """Naming the type stops MA guessing; replace stops last night's queue."""
    hass.config.components.add("music_assistant")
    alarm = Alarm(
        time="07:00",
        sound_mode="music_assistant",
        sound="library://playlist/12",
        sound_media_type="playlist",
    )
    await output._async_play_music_assistant(alarm, "media_player.bedroom")
    await hass.async_block_till_done()

    _domain, _service, data = calls[-1]
    assert data["media_id"] == "library://playlist/12"
    assert data["media_type"] == "playlist"
    assert data["enqueue"] == "replace"


async def test_music_assistant_without_a_type_omits_it(
    hass, output: AlarmOutput, calls
) -> None:
    hass.config.components.add("music_assistant")
    alarm = Alarm(
        time="07:00", sound_mode="music_assistant", sound="Morning Coffee"
    )
    await output._async_play_music_assistant(alarm, "media_player.bedroom")
    await hass.async_block_till_done()
    assert "media_type" not in calls[-1][2]


async def test_search_needs_music_assistant(hass, output: AlarmOutput) -> None:
    from homeassistant.exceptions import HomeAssistantError

    with pytest.raises(HomeAssistantError, match="not set up"):
        await output.async_search_media("morning")


def test_search_results_are_flattened_and_labelled() -> None:
    """One flat, pickable list — the card cannot show five buckets."""
    response = {
        "playlists": [{"uri": "library://playlist/1", "name": "Morning"}],
        "tracks": [
            {
                "uri": "library://track/9",
                "name": "Here Comes The Sun",
                "media_type": "track",
                "artists": [{"name": "The Beatles"}],
            },
            {"name": "no uri, dropped"},
        ],
    }
    results = AlarmOutput._flatten_search(response, 10)
    assert [item["uri"] for item in results] == [
        "library://playlist/1",
        "library://track/9",
    ]
    # The bucket names the type when the item does not.
    assert results[0]["media_type"] == "playlist"
    assert results[1]["artist"] == "The Beatles"


def test_search_respects_the_limit() -> None:
    response = {"tracks": [{"uri": f"x/{i}", "name": str(i)} for i in range(20)]}
    assert len(AlarmOutput._flatten_search(response, 5)) == 5


# -- The test run ----------------------------------------------------------


async def test_sound_test_plays_on_the_real_target(
    hass, output: AlarmOutput, calls
) -> None:
    result = await output.async_test(None, scope=TEST_SCOPE_SOUND)
    await hass.async_block_till_done()
    assert result["sound"] is True
    assert result["target"] == "Bedroom"
    played = [call for call in calls if call[1] == "play_media"]
    assert played and played[0][2]["entity_id"] == "media_player.bedroom"


async def test_sound_test_reports_when_there_is_no_output(hass) -> None:
    """The most useful answer a test can give: nothing is configured."""
    coordinator = SimpleNamespace(
        hass=hass,
        config={},
        volume=VolumeController(hass),
        describe_alarm_target=lambda alarm=None: "kein Lautsprecher konfiguriert",
    )

    async def _room(alarm=None):
        return None

    coordinator.async_get_alarm_room = _room
    result = await AlarmOutput(coordinator).async_test(None)
    assert result["sound"] is False


async def test_light_test_snapshots_before_it_touches_anything(
    hass, output: AlarmOutput, calls
) -> None:
    """Testing at 22:00 must not leave the bedroom lit."""
    result = await output.async_test(None, scope=TEST_SCOPE_LIGHT, seconds=1)
    await hass.async_block_till_done()
    assert result["entities"] == ["light.bedside"]
    assert result["restore_in"] == 1

    ordered = [(domain, service) for domain, service, _ in calls]
    assert ordered.index(("scene", "create")) < ordered.index(("light", "turn_on"))
    snapshot = next(call for call in calls if call[1] == "create")
    assert snapshot[2]["snapshot_entities"] == ["light.bedside"]
    await _finish_restore(hass)


async def test_light_test_restores_the_snapshot(
    hass, output: AlarmOutput, calls
) -> None:
    await output.async_test(None, scope=TEST_SCOPE_LIGHT, seconds=2)
    await hass.async_block_till_done()
    assert not [call for call in calls if call[1] == "turn_on" and call[0] == "scene"]

    await _finish_restore(hass)
    restored = [call for call in calls if call[0] == "scene" and call[1] == "turn_on"]
    assert restored and restored[0][2]["entity_id"] == TEST_SNAPSHOT_SCENE


async def test_cover_test_without_covers_warns_instead_of_acting(
    hass, output: AlarmOutput, calls, caplog
) -> None:
    result = await output.async_test(None, scope="cover")
    await hass.async_block_till_done()
    assert result["entities"] == []
    assert "Nothing configured to test" in caplog.text
    assert not calls


async def test_cover_test_uses_the_configured_blinds(
    hass, output: AlarmOutput, calls
) -> None:
    output.coordinator.config = {CONF_ALARM_COVER_ENTITIES: ["cover.bedroom"]}
    result = await output.async_test(None, scope="cover", seconds=1)
    await hass.async_block_till_done()
    assert result["entities"] == ["cover.bedroom"]
    assert any(call[1] == "set_cover_position" for call in calls)
    await _finish_restore(hass)


async def test_explicit_volume_wins_over_the_floor(
    hass, output: AlarmOutput, calls
) -> None:
    """A test at 3 % is how you check a speaker without waking the house."""
    output.coordinator.config = {CONF_ALARM_MEDIA_PLAYER: "media_player.bedroom"}
    hass.states.async_set(
        "media_player.bedroom",
        "idle",
        {"supported_features": 4, "volume_level": 0.8},
    )
    await output.async_test(None, scope=TEST_SCOPE_SOUND, volume=0.03)
    await hass.async_block_till_done()
    volumes = [call for call in calls if call[1] == "volume_set"]
    assert volumes and volumes[0][2]["volume_level"] == 0.03


def test_service_response_mode_is_declared() -> None:
    """alarm_test and alarm_search_media both answer the caller."""
    from custom_components.herold.services import _RESPONSE_SERVICES

    assert {name for name, _handler, _schema in _RESPONSE_SERVICES} == {
        "alarm_test",
        "alarm_search_media",
    }
    assert SupportsResponse.OPTIONAL is not None
