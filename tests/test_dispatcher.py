"""Priority rules and channel selection — ported from the original script."""

import pytest

from custom_components.herold.const import (
    CHANNEL_INTERNAL,
    CHANNEL_PUSH,
    CHANNEL_TELEGRAM,
    CHANNEL_TODO,
    CHANNEL_VOICE,
    CONF_TELEGRAM_CHAT_ID,
)
from custom_components.herold.dispatcher import (
    select_channels,
    select_query_channels,
    should_deliver,
)
from custom_components.herold.models import Notification, Query, Room

from .common import ctx_for, make_coordinator

SAT_ROOM = Room(
    name="Arbeitszimmer",
    occupancy_entities=["binary_sensor.az"],
    sat_entity="assist_satellite.az",
)
MEDIA_ROOM = Room(
    name="Badezimmer",
    occupancy_entities=["binary_sensor.bad"],
    media_player_entity="media_player.sonos_roam",
)


@pytest.mark.parametrize(
    ("priority", "is_home", "is_dnd", "expected"),
    [
        (0, True, True, True),  # internal: always (runs via agent)
        (1, False, True, True),  # todo: always (silent inbox)
        (2, True, False, True),
        (2, True, True, False),  # P2 blocked by DND
        (2, False, True, False),
        (3, True, True, True),  # P3 ignores DND
        (4, False, True, True),  # P4 always
    ],
)
def test_should_deliver_matrix(
    priority: int, is_home: bool, is_dnd: bool, expected: bool
) -> None:
    coordinator = make_coordinator()
    notification = Notification(message="x", priority=priority)
    ok, _reason = should_deliver(
        notification, ctx_for(coordinator, is_home=is_home, is_dnd=is_dnd)
    )
    assert ok is expected


def _channel_names(channels: list) -> list[str]:
    return [channel.name for channel in channels]


def test_p0_routes_to_internal_only() -> None:
    coordinator = make_coordinator()
    notification = Notification(message="mach was", priority=0)
    assert _channel_names(
        select_channels(notification, ctx_for(coordinator))
    ) == [CHANNEL_INTERNAL]


def test_p1_routes_to_todo_only() -> None:
    coordinator = make_coordinator()
    notification = Notification(message="Post holen", priority=1)
    assert _channel_names(
        select_channels(notification, ctx_for(coordinator))
    ) == [CHANNEL_TODO]


def test_p2_home_with_active_room_is_voice_only() -> None:
    coordinator = make_coordinator(
        on_entities={"binary_sensor.az"},
        rooms=[SAT_ROOM],
        config={CONF_TELEGRAM_CHAT_ID: "123"},
    )
    notification = Notification(message="x", priority=2)
    assert _channel_names(
        select_channels(notification, ctx_for(coordinator))
    ) == [CHANNEL_VOICE]


def test_p2_away_goes_push_and_telegram() -> None:
    coordinator = make_coordinator(config={CONF_TELEGRAM_CHAT_ID: "123"})
    notification = Notification(message="x", priority=2)
    assert _channel_names(
        select_channels(notification, ctx_for(coordinator, is_home=False))
    ) == [CHANNEL_PUSH, CHANNEL_TELEGRAM]


def test_p2_offline_without_fallback_uses_push() -> None:
    coordinator = make_coordinator(
        on_entities={"binary_sensor.az"}, rooms=[SAT_ROOM]
    )
    notification = Notification(message="x", priority=2)
    assert _channel_names(
        select_channels(notification, ctx_for(coordinator, internet=False))
    ) == [CHANNEL_PUSH]


def test_p2_offline_with_fallback_keeps_voice() -> None:
    coordinator = make_coordinator(
        on_entities={"binary_sensor.az"},
        rooms=[SAT_ROOM],
        voice_offline_capable=True,
    )
    notification = Notification(message="x", priority=2)
    assert _channel_names(
        select_channels(notification, ctx_for(coordinator, internet=False))
    ) == [CHANNEL_VOICE]


def test_p3_home_uses_all_channels() -> None:
    coordinator = make_coordinator(
        on_entities={"binary_sensor.az"},
        rooms=[SAT_ROOM],
        config={CONF_TELEGRAM_CHAT_ID: "123"},
    )
    notification = Notification(message="x", priority=3)
    assert _channel_names(
        select_channels(notification, ctx_for(coordinator))
    ) == [CHANNEL_VOICE, CHANNEL_PUSH, CHANNEL_TELEGRAM]


def test_query_sat_room_voice_captures_answer() -> None:
    coordinator = make_coordinator(
        on_entities={"binary_sensor.az"},
        rooms=[SAT_ROOM],
        config={CONF_TELEGRAM_CHAT_ID: "123"},
    )
    query = Query(question="Licht aus?", priority=2)
    assert _channel_names(
        select_query_channels(query, ctx_for(coordinator))
    ) == [CHANNEL_VOICE]


def test_query_media_only_room_adds_telegram_buttons() -> None:
    """A Sonos-only room speaks the question but cannot capture the answer."""
    coordinator = make_coordinator(
        on_entities={"binary_sensor.bad"},
        rooms=[MEDIA_ROOM],
        config={CONF_TELEGRAM_CHAT_ID: "123"},
    )
    query = Query(question="Licht aus?", priority=2)
    assert _channel_names(
        select_query_channels(query, ctx_for(coordinator))
    ) == [CHANNEL_VOICE, CHANNEL_TELEGRAM]


def test_query_away_goes_telegram_only_for_p2() -> None:
    coordinator = make_coordinator(config={CONF_TELEGRAM_CHAT_ID: "123"})
    query = Query(question="Licht aus?", priority=2)
    assert _channel_names(
        select_query_channels(query, ctx_for(coordinator, is_home=False))
    ) == [CHANNEL_TELEGRAM]


def test_query_p3_adds_push() -> None:
    coordinator = make_coordinator(
        on_entities={"binary_sensor.az"},
        rooms=[SAT_ROOM],
        config={CONF_TELEGRAM_CHAT_ID: "123"},
    )
    query = Query(question="Licht aus?", priority=3)
    assert _channel_names(
        select_query_channels(query, ctx_for(coordinator))
    ) == [CHANNEL_VOICE, CHANNEL_PUSH, CHANNEL_TELEGRAM]
