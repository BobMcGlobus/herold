"""Data models for the Herold integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from homeassistant.const import STATE_ON
from homeassistant.util import dt as dt_util

from .const import DEFAULT_PRIORITY, DEFAULT_PRIORITY_WEIGHT

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _new_notification_id() -> str:
    return uuid4().hex[:8]


@dataclass(kw_only=True)
class Notification:
    """A single notification travelling through the dispatcher."""

    message: str
    id: str = field(default_factory=_new_notification_id)
    priority: int = DEFAULT_PRIORITY
    mode: Literal["info"] = "info"
    recipient: str | None = None
    target_player: str | None = None
    callback_event: str | None = None
    created_at: datetime = field(default_factory=dt_util.utcnow)
    tag: str | None = None
    ttl_minutes: int | None = None
    title: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for a future persistence store."""
        return {
            "id": self.id,
            "message": self.message,
            "priority": self.priority,
            "mode": self.mode,
            "recipient": self.recipient,
            "target_player": self.target_player,
            "callback_event": self.callback_event,
            "created_at": self.created_at.isoformat(),
            "tag": self.tag,
            "ttl_minutes": self.ttl_minutes,
            "title": self.title,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Notification:
        """Deserialize from a persistence store payload."""
        created_at = dt_util.parse_datetime(data.get("created_at") or "")
        return cls(
            id=data["id"],
            message=data["message"],
            priority=data.get("priority", DEFAULT_PRIORITY),
            mode=data.get("mode", "info"),
            recipient=data.get("recipient"),
            target_player=data.get("target_player"),
            callback_event=data.get("callback_event"),
            created_at=created_at or dt_util.utcnow(),
            tag=data.get("tag"),
            ttl_minutes=data.get("ttl_minutes"),
            title=data.get("title"),
            context=data.get("context") or {},
        )


@dataclass(kw_only=True)
class Room:
    """A configured room with occupancy detection and voice outputs."""

    name: str
    occupancy_entities: list[str] = field(default_factory=list)
    sat_entity: str | None = None
    media_player_entity: str | None = None
    light_entity: str | None = None
    priority_weight: int = DEFAULT_PRIORITY_WEIGHT

    def is_occupied(self, hass: HomeAssistant) -> bool:
        """Return True if any occupancy sensor of the room is on (OR-linked)."""
        return any(
            hass.states.is_state(entity_id, STATE_ON)
            for entity_id in self.occupancy_entities
        )

    def can_deliver_voice(self) -> bool:
        """Return True if the room has any audible output."""
        return self.sat_entity is not None or self.media_player_entity is not None

    def supports_query(self) -> bool:
        """Return True if the room can run a conversation (needs a satellite)."""
        return self.sat_entity is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for config entry storage."""
        return {
            "name": self.name,
            "occupancy_entities": self.occupancy_entities,
            "sat_entity": self.sat_entity,
            "media_player_entity": self.media_player_entity,
            "light_entity": self.light_entity,
            "priority_weight": self.priority_weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Room:
        """Deserialize from config entry storage."""
        return cls(
            name=data["name"],
            occupancy_entities=list(data.get("occupancy_entities") or []),
            sat_entity=data.get("sat_entity"),
            media_player_entity=data.get("media_player_entity"),
            light_entity=data.get("light_entity"),
            priority_weight=data.get("priority_weight", DEFAULT_PRIORITY_WEIGHT),
        )


@dataclass(kw_only=True)
class DeliveryResult:
    """Outcome of a single dispatch run."""

    notification_id: str
    channels_used: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    room_used: str | None = None
    timestamp: datetime = field(default_factory=dt_util.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for a future persistence store."""
        return {
            "notification_id": self.notification_id,
            "channels_used": self.channels_used,
            "errors": self.errors,
            "room_used": self.room_used,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DNDState:
    """Merged do-not-disturb state (internal switch + external entity)."""

    master_active: bool = False
    external_active: bool = False

    @property
    def effective(self) -> bool:
        """Return True if any DND source is active."""
        return self.master_active or self.external_active
