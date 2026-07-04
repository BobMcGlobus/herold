"""Multi-occupancy conflict resolution and last-known-room fallback."""

from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.herold.models import Room
from custom_components.herold.room_router import select_room

from .common import make_coordinator


def _sat_room(name: str, weight: int = 0) -> Room:
    return Room(
        name=name,
        occupancy_entities=[f"binary_sensor.{name}"],
        sat_entity=f"assist_satellite.{name}",
        priority_weight=weight,
    )


def test_single_occupied_room_wins() -> None:
    rooms = [_sat_room("a"), _sat_room("b")]
    coordinator = make_coordinator(on_entities={"binary_sensor.b"}, rooms=rooms)
    assert select_room(coordinator).name == "b"


def test_priority_weight_beats_recency() -> None:
    rooms = [_sat_room("a", weight=0), _sat_room("b", weight=10)]
    coordinator = make_coordinator(
        on_entities={"binary_sensor.a", "binary_sensor.b"}, rooms=rooms
    )
    coordinator.store.room_last_activation = {
        "a": dt_util.utcnow(),
        "b": dt_util.utcnow() - timedelta(minutes=30),
    }
    assert select_room(coordinator).name == "b"


def test_equal_weights_most_recent_activation_wins() -> None:
    rooms = [_sat_room("a"), _sat_room("b")]
    coordinator = make_coordinator(
        on_entities={"binary_sensor.a", "binary_sensor.b"}, rooms=rooms
    )
    coordinator.store.room_last_activation = {
        "a": dt_util.utcnow() - timedelta(minutes=5),
        "b": dt_util.utcnow(),
    }
    assert select_room(coordinator).name == "b"


def test_last_known_room_fallback_within_ttl() -> None:
    rooms = [_sat_room("a")]
    coordinator = make_coordinator(rooms=rooms)  # nothing occupied
    coordinator.store.last_known_room = "a"
    coordinator.store.last_room_activity = dt_util.utcnow() - timedelta(minutes=5)
    assert select_room(coordinator).name == "a"


def test_last_known_room_expires_after_ttl() -> None:
    rooms = [_sat_room("a")]
    coordinator = make_coordinator(rooms=rooms)
    coordinator.store.last_known_room = "a"
    coordinator.store.last_room_activity = dt_util.utcnow() - timedelta(minutes=20)
    assert select_room(coordinator) is None


def test_require_sat_filters_media_only_rooms() -> None:
    media_room = Room(
        name="bad",
        occupancy_entities=["binary_sensor.bad"],
        media_player_entity="media_player.sonos_roam",
    )
    coordinator = make_coordinator(
        on_entities={"binary_sensor.bad"}, rooms=[media_room]
    )
    assert select_room(coordinator) is not None
    assert select_room(coordinator, require_sat=True) is None
