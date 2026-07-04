"""Model serialization roundtrips and room behavior."""

from types import SimpleNamespace

from custom_components.herold.models import (
    DNDState,
    Notification,
    Query,
    Room,
    Schedule,
)

from .common import FakeStates


def test_notification_roundtrip() -> None:
    notification = Notification(
        message="Test", priority=3, tag="tag", title="Titel", ttl_minutes=30
    )
    assert Notification.from_dict(notification.to_dict()) == notification


def test_query_roundtrip() -> None:
    query = Query(
        question="Licht aus?",
        mode="choice",
        choices=["Ja", "Nein", "Später"],
        priority=3,
        voice_timeout_seconds=45,
        escalation=[{"after_minutes": 5, "raise_to_priority": 3}],
    )
    assert Query.from_dict(query.to_dict()) == query


def test_schedule_roundtrip() -> None:
    schedule = Schedule(
        scheduled_for=Notification(message="x").created_at,
        payload={"message": "später", "priority": 2},
    )
    assert Schedule.from_dict(schedule.to_dict()) == schedule


def test_room_roundtrip_and_legacy_light_entity() -> None:
    room = Room(
        name="Arbeitszimmer",
        occupancy_entities=["binary_sensor.occ"],
        sat_entity="assist_satellite.az",
        flash_entities=["light.schreibtisch"],
    )
    assert Room.from_dict(room.to_dict()) == room

    # Pre-migration configs may still carry light_entity
    legacy = Room.from_dict(
        {
            "name": "Alt",
            "occupancy_entities": ["binary_sensor.occ"],
            "sat_entity": "assist_satellite.alt",
            "light_entity": "light.alt",
        }
    )
    assert legacy.flash_entities == ["light.alt"]


def test_room_occupancy_is_or_linked() -> None:
    room = Room(
        name="Wohnzimmer+Küche",
        occupancy_entities=["binary_sensor.fp2_a", "binary_sensor.fp2_b"],
        sat_entity="assist_satellite.wz",
    )
    hass_one_on = SimpleNamespace(states=FakeStates({"binary_sensor.fp2_b"}))
    hass_all_off = SimpleNamespace(states=FakeStates(set()))
    assert room.is_occupied(hass_one_on) is True
    assert room.is_occupied(hass_all_off) is False


def test_room_capabilities() -> None:
    sat_room = Room(name="a", sat_entity="assist_satellite.a")
    media_room = Room(name="b", media_player_entity="media_player.b")
    empty_room = Room(name="c")
    assert sat_room.can_deliver_voice() and sat_room.supports_query()
    assert media_room.can_deliver_voice() and not media_room.supports_query()
    assert not empty_room.can_deliver_voice()


def test_dnd_state_merge() -> None:
    state = DNDState()
    assert state.effective is False
    state.external_active = True
    assert state.effective is True
    state.external_active = False
    state.master_active = True
    assert state.effective is True
