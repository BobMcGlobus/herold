"""Data models for the Herold integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from homeassistant.const import STATE_ON
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_PRIORITY,
    DEFAULT_PRIORITY_WEIGHT,
    DEFAULT_QUERY_TIMEOUT_MINUTES,
    LEGACY_CONF_LIGHT_ENTITY,
    LEGACY_DEFAULT_CALLBACK,
    QUERY_MODE_YESNO,
    QUERY_STATUS_PENDING,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _new_id() -> str:
    return uuid4().hex[:8]


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    return dt_util.parse_datetime(str(value))


@dataclass(kw_only=True)
class Notification:
    """A single fire-and-forget notification travelling through the dispatcher."""

    message: str
    id: str = field(default_factory=_new_id)
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
        """Serialize for the persistence store."""
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
        return cls(
            id=data["id"],
            message=data["message"],
            priority=data.get("priority", DEFAULT_PRIORITY),
            mode=data.get("mode", "info"),
            recipient=data.get("recipient"),
            target_player=data.get("target_player"),
            callback_event=data.get("callback_event"),
            created_at=_parse_datetime(data.get("created_at")) or dt_util.utcnow(),
            tag=data.get("tag"),
            ttl_minutes=data.get("ttl_minutes"),
            title=data.get("title"),
            context=data.get("context") or {},
        )


@dataclass(kw_only=True)
class Query:
    """A notification that expects an answer (first-class object since Phase 2)."""

    question: str
    id: str = field(default_factory=_new_id)
    mode: str = QUERY_MODE_YESNO
    choices: list[str] | None = None
    priority: int = DEFAULT_PRIORITY
    callback_event: str = LEGACY_DEFAULT_CALLBACK
    recipient: str | None = None
    target_player: str | None = None
    timeout_minutes: int = DEFAULT_QUERY_TIMEOUT_MINUTES
    voice_timeout_seconds: int | None = None
    default_answer: str | None = None
    escalation: list[dict[str, int]] | None = None
    escalated: bool = False
    created_at: datetime = field(default_factory=dt_util.utcnow)
    channels_delivered: list[str] = field(default_factory=list)
    status: str = QUERY_STATUS_PENDING
    answer: str | None = None
    answered_at: datetime | None = None
    answered_via: str | None = None

    @property
    def timeout_at(self) -> datetime:
        """Return the point in time this query expires."""
        return self.created_at + timedelta(minutes=self.timeout_minutes)

    @property
    def is_pending(self) -> bool:
        """Return True while the query waits for an answer."""
        return self.status == QUERY_STATUS_PENDING

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the persistence store."""
        return {
            "id": self.id,
            "question": self.question,
            "mode": self.mode,
            "choices": self.choices,
            "priority": self.priority,
            "callback_event": self.callback_event,
            "recipient": self.recipient,
            "target_player": self.target_player,
            "timeout_minutes": self.timeout_minutes,
            "voice_timeout_seconds": self.voice_timeout_seconds,
            "default_answer": self.default_answer,
            "escalation": self.escalation,
            "escalated": self.escalated,
            "created_at": self.created_at.isoformat(),
            "channels_delivered": self.channels_delivered,
            "status": self.status,
            "answer": self.answer,
            "answered_at": (
                self.answered_at.isoformat() if self.answered_at else None
            ),
            "answered_via": self.answered_via,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Query:
        """Deserialize from a persistence store payload."""
        return cls(
            id=data["id"],
            question=data["question"],
            mode=data.get("mode", QUERY_MODE_YESNO),
            choices=data.get("choices"),
            priority=data.get("priority", DEFAULT_PRIORITY),
            callback_event=data.get("callback_event", LEGACY_DEFAULT_CALLBACK),
            recipient=data.get("recipient"),
            target_player=data.get("target_player"),
            timeout_minutes=data.get(
                "timeout_minutes", DEFAULT_QUERY_TIMEOUT_MINUTES
            ),
            voice_timeout_seconds=data.get("voice_timeout_seconds"),
            default_answer=data.get("default_answer"),
            escalation=data.get("escalation"),
            escalated=data.get("escalated", False),
            created_at=_parse_datetime(data.get("created_at")) or dt_util.utcnow(),
            channels_delivered=list(data.get("channels_delivered") or []),
            status=data.get("status", QUERY_STATUS_PENDING),
            answer=data.get("answer"),
            answered_at=_parse_datetime(data.get("answered_at")),
            answered_via=data.get("answered_via"),
        )


@dataclass(kw_only=True)
class InternalResult:
    """Outcome of a P0 instruction executed by a conversation agent."""

    notification_id: str
    instruction: str
    agent_id: str
    status: str
    speech: str | None = None
    detail: str | None = None
    verified: bool = False
    timestamp: datetime = field(default_factory=dt_util.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for sensor attributes."""
        return {
            "notification_id": self.notification_id,
            "instruction": self.instruction,
            "agent_id": self.agent_id,
            "status": self.status,
            "speech": self.speech,
            "detail": self.detail,
            "verified": self.verified,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(kw_only=True)
class Schedule:
    """A deferred notification (herold.schedule / herold.remind_self)."""

    scheduled_for: datetime
    payload: dict[str, Any]
    id: str = field(default_factory=_new_id)
    created_at: datetime = field(default_factory=dt_util.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the persistence store."""
        return {
            "id": self.id,
            "scheduled_for": self.scheduled_for.isoformat(),
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Schedule:
        """Deserialize from a persistence store payload."""
        return cls(
            id=data["id"],
            scheduled_for=_parse_datetime(data["scheduled_for"])
            or dt_util.utcnow(),
            payload=data.get("payload") or {},
            created_at=_parse_datetime(data.get("created_at")) or dt_util.utcnow(),
        )


@dataclass(kw_only=True)
class Watch:
    """A notification waiting for a state change instead of a point in time."""

    entity_id: str
    payload: dict[str, Any]
    id: str = field(default_factory=_new_id)
    to_state: str | None = None
    from_state: str | None = None
    above: float | None = None
    below: float | None = None
    once: bool = True
    created_at: datetime = field(default_factory=dt_util.utcnow)
    expires_at: datetime | None = None
    friendly_name: str | None = None

    @property
    def is_numeric(self) -> bool:
        """Return True if this watch compares numeric thresholds."""
        return self.above is not None or self.below is not None

    def matches(self, old_state: str | None, new_state: str) -> bool:
        """Return True if a state transition satisfies this watch."""
        if self.from_state is not None and old_state != self.from_state:
            return False
        if self.is_numeric:
            try:
                value = float(new_state)
                previous = float(old_state) if old_state is not None else None
            except (TypeError, ValueError):
                return False
            # Only fire on the crossing itself, not on every update while
            # the value stays past the threshold.
            crossed_up = self.above is None or (
                value > self.above
                and (previous is None or previous <= self.above)
            )
            crossed_down = self.below is None or (
                value < self.below
                and (previous is None or previous >= self.below)
            )
            return crossed_up and crossed_down
        if self.to_state is not None:
            # Only fire on an actual transition into the target state.
            return new_state == self.to_state and old_state != self.to_state
        return old_state != new_state

    def describe(self) -> str:
        """Return a German phrase describing the trigger condition."""
        name = self.friendly_name or self.entity_id
        if self.above is not None and self.below is not None:
            return f"wenn {name} zwischen {self.below} und {self.above} liegt"
        if self.above is not None:
            return f"wenn {name} über {self.above} steigt"
        if self.below is not None:
            return f"wenn {name} unter {self.below} fällt"
        if self.to_state is not None:
            return f"wenn {name} auf «{self.to_state}» wechselt"
        return f"wenn sich {name} ändert"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the persistence store."""
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "payload": self.payload,
            "to_state": self.to_state,
            "from_state": self.from_state,
            "above": self.above,
            "below": self.below,
            "once": self.once,
            "created_at": self.created_at.isoformat(),
            "expires_at": (
                self.expires_at.isoformat() if self.expires_at else None
            ),
            "friendly_name": self.friendly_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Watch:
        """Deserialize from a persistence store payload."""
        return cls(
            id=data["id"],
            entity_id=data["entity_id"],
            payload=data.get("payload") or {},
            to_state=data.get("to_state"),
            from_state=data.get("from_state"),
            above=data.get("above"),
            below=data.get("below"),
            once=data.get("once", True),
            created_at=_parse_datetime(data.get("created_at")) or dt_util.utcnow(),
            expires_at=_parse_datetime(data.get("expires_at")),
            friendly_name=data.get("friendly_name"),
        )


@dataclass(kw_only=True)
class Room:
    """A configured room with occupancy detection and voice outputs."""

    name: str
    occupancy_entities: list[str] = field(default_factory=list)
    sat_entity: str | None = None
    media_player_entity: str | None = None
    flash_entities: list[str] = field(default_factory=list)
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
            "flash_entities": self.flash_entities,
            "priority_weight": self.priority_weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Room:
        """Deserialize; tolerates the pre-migration light_entity key."""
        flash_entities = list(data.get("flash_entities") or [])
        legacy_light = data.get(LEGACY_CONF_LIGHT_ENTITY)
        if legacy_light and legacy_light not in flash_entities:
            flash_entities.append(legacy_light)
        return cls(
            name=data["name"],
            occupancy_entities=list(data.get("occupancy_entities") or []),
            sat_entity=data.get("sat_entity"),
            media_player_entity=data.get("media_player_entity"),
            flash_entities=flash_entities,
            priority_weight=data.get("priority_weight", DEFAULT_PRIORITY_WEIGHT),
        )


@dataclass(kw_only=True)
class DeliveryResult:
    """Outcome of a single dispatch run."""

    notification_id: str
    channels_used: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    room_used: str | None = None
    reason: str | None = None  # why nothing was delivered (drop/rate limit)
    timestamp: datetime = field(default_factory=dt_util.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the persistence store."""
        return {
            "notification_id": self.notification_id,
            "channels_used": self.channels_used,
            "errors": self.errors,
            "room_used": self.room_used,
            "reason": self.reason,
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
