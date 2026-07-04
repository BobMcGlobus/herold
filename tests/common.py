"""Shared test helpers: lightweight coordinator/hass fakes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from homeassistant.const import STATE_ON

from custom_components.herold.channels import (
    InternalChannel,
    PushChannel,
    TelegramChannel,
    TodoChannel,
    VoiceChannel,
)
from custom_components.herold.const import (
    CHANNEL_INTERNAL,
    CHANNEL_PUSH,
    CHANNEL_TELEGRAM,
    CHANNEL_TODO,
    CHANNEL_VOICE,
)
from custom_components.herold.dispatcher import DispatchContext


class FakeStates:
    """Minimal hass.states stand-in for Room.is_occupied checks."""

    def __init__(self, on_entities: set[str]) -> None:
        self._on = set(on_entities)

    def is_state(self, entity_id: str, state: str) -> bool:
        """Return True when the entity is 'on' and 'on' was asked for."""
        return state == STATE_ON and entity_id in self._on


def make_coordinator(
    on_entities: set[str] | None = None,
    rooms: list | None = None,
    config: dict[str, Any] | None = None,
    voice_offline_capable: bool = False,
) -> SimpleNamespace:
    """Build a duck-typed coordinator good enough for dispatcher/router."""
    channels = {
        CHANNEL_VOICE: VoiceChannel(offline_capable=voice_offline_capable),
        CHANNEL_PUSH: PushChannel(),
        CHANNEL_TELEGRAM: TelegramChannel(),
        CHANNEL_INTERNAL: InternalChannel(),
        CHANNEL_TODO: TodoChannel(),
    }
    store = SimpleNamespace(
        room_last_activation={},
        last_known_room=None,
        last_room_activity=None,
    )
    return SimpleNamespace(
        hass=SimpleNamespace(states=FakeStates(on_entities or set())),
        rooms=list(rooms or []),
        config=config or {},
        channels=channels,
        store=store,
    )


def ctx_for(
    coordinator: SimpleNamespace,
    is_home: bool = True,
    is_dnd: bool = False,
    internet: bool = True,
) -> DispatchContext:
    """Build a dispatch context for the fake coordinator."""
    return DispatchContext(
        coordinator=coordinator,
        is_home=is_home,
        is_dnd=is_dnd,
        internet_available=internet,
    )
