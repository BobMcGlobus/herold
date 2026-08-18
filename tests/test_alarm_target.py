"""Where an alarm rings: bed sensor, sleeping area and fallbacks."""

from types import SimpleNamespace

import pytest

from custom_components.herold.const import (
    CONF_ALARM_BED_SENSOR,
    CONF_ALARM_MEDIA_PLAYER,
    CONF_ALARM_ROOM,
    CONF_ALARM_SAT_ENTITY,
)
from custom_components.herold.coordinator import HeroldCoordinator
from custom_components.herold.models import Room

BEDROOM = Room(
    name="Bedroom",
    occupancy_entities=["binary_sensor.bedroom"],
    sat_entity="assist_satellite.bedroom",
    media_player_entity="media_player.bedroom",
)
KITCHEN = Room(
    name="Kitchen",
    occupancy_entities=["binary_sensor.kitchen"],
    sat_entity="assist_satellite.kitchen",
)


def _coordinator(hass, config, occupied: set[str] | None = None):
    """A coordinator with only the bits the alarm target logic touches."""
    entry = SimpleNamespace(entry_id="test", data={}, options={})
    coordinator = HeroldCoordinator(hass, entry)
    coordinator.config = config
    coordinator.rooms = [BEDROOM, KITCHEN]
    for entity_id in occupied or ():
        hass.states.async_set(entity_id, "on")
    return coordinator


async def test_bed_sensor_wins_over_occupancy(hass) -> None:
    """Lying in bed beats motion picked up elsewhere in the flat."""
    hass.states.async_set("binary_sensor.bed", "on")
    coordinator = _coordinator(
        hass,
        {CONF_ALARM_BED_SENSOR: "binary_sensor.bed", CONF_ALARM_ROOM: "Bedroom"},
        occupied={"binary_sensor.kitchen"},
    )
    assert coordinator.in_bed is True
    room = await coordinator.async_get_alarm_room()
    assert room is not None
    assert room.name == "Bedroom"


async def test_out_of_bed_follows_the_active_room(hass) -> None:
    """Already up and in the kitchen — wake there, not in the bedroom."""
    hass.states.async_set("binary_sensor.bed", "off")
    coordinator = _coordinator(
        hass,
        {CONF_ALARM_BED_SENSOR: "binary_sensor.bed", CONF_ALARM_ROOM: "Bedroom"},
        occupied={"binary_sensor.kitchen"},
    )
    assert coordinator.in_bed is False
    room = await coordinator.async_get_alarm_room()
    assert room is not None
    assert room.name == "Kitchen"


async def test_no_occupancy_falls_back_to_the_sleeping_area(hass) -> None:
    """The original bug: nothing occupied at 6:30 must not mean silence."""
    coordinator = _coordinator(hass, {CONF_ALARM_ROOM: "Bedroom"})
    room = await coordinator.async_get_alarm_room()
    assert room is not None
    assert room.name == "Bedroom"


async def test_without_configuration_there_is_no_room(hass) -> None:
    coordinator = _coordinator(hass, {})
    assert await coordinator.async_get_alarm_room() is None


async def test_unknown_room_name_is_ignored(hass) -> None:
    coordinator = _coordinator(hass, {CONF_ALARM_ROOM: "Gone"})
    assert await coordinator.async_get_alarm_room() is None


async def test_target_description(hass) -> None:
    hass.states.async_set("binary_sensor.bed", "on")
    coordinator = _coordinator(
        hass,
        {CONF_ALARM_BED_SENSOR: "binary_sensor.bed", CONF_ALARM_ROOM: "Bedroom"},
    )
    assert coordinator.describe_alarm_target() == "Bedroom"

    explicit = _coordinator(
        hass, {CONF_ALARM_SAT_ENTITY: "assist_satellite.clock"}
    )
    assert explicit.describe_alarm_target() == "assist_satellite.clock"

    nothing = _coordinator(hass, {})
    assert "kein Lautsprecher" in nothing.describe_alarm_target()


async def test_explicit_speaker_needs_no_room(hass) -> None:
    coordinator = _coordinator(
        hass, {CONF_ALARM_MEDIA_PLAYER: "media_player.clock_radio"}
    )
    assert coordinator.describe_alarm_target() == "media_player.clock_radio"


@pytest.mark.parametrize("value", ["on", "On", "ON"])
async def test_bed_sensor_state_is_case_insensitive(hass, value: str) -> None:
    hass.states.async_set("binary_sensor.bed", value.lower())
    coordinator = _coordinator(hass, {CONF_ALARM_BED_SENSOR: "binary_sensor.bed"})
    assert coordinator.in_bed is True
