"""Persistence for the Herold integration (queries, room activity)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_VERSION

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SAVE_DELAY_SECONDS = 10


class HeroldStore:
    """Wraps helpers.storage.Store with typed access and delayed saves."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.queries: dict[str, dict[str, Any]] = {}
        self.schedules: dict[str, dict[str, Any]] = {}
        self.todo_items: list[dict[str, Any]] = []
        self.dnd_session: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []
        self.last_known_room: str | None = None
        self.last_room_activity: datetime | None = None
        self.room_last_activation: dict[str, datetime] = {}

    async def async_load(self) -> None:
        """Load persisted state from disk."""
        data = await self._store.async_load() or {}
        self.queries = data.get("queries") or {}
        self.schedules = data.get("schedules") or {}
        self.todo_items = data.get("todo_items") or []
        self.dnd_session = data.get("dnd_session")
        self.history = data.get("history") or []
        self.last_known_room = data.get("last_known_room")
        raw_activity = data.get("last_room_activity")
        self.last_room_activity = (
            dt_util.parse_datetime(raw_activity) if raw_activity else None
        )
        self.room_last_activation = {
            name: parsed
            for name, raw in (data.get("room_last_activation") or {}).items()
            if (parsed := dt_util.parse_datetime(raw)) is not None
        }

    @callback
    def async_schedule_save(self) -> None:
        """Schedule a delayed write to disk."""
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY_SECONDS)

    async def async_flush(self) -> None:
        """Write immediately (used on unload)."""
        await self._store.async_save(self._data_to_save())

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "schedules": self.schedules,
            "todo_items": self.todo_items,
            "dnd_session": self.dnd_session,
            "history": self.history,
            "last_known_room": self.last_known_room,
            "last_room_activity": (
                self.last_room_activity.isoformat()
                if self.last_room_activity
                else None
            ),
            "room_last_activation": {
                name: value.isoformat()
                for name, value in self.room_last_activation.items()
            },
        }
