"""Todo platform: the Herold inbox for P1 notifications."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, TODO_STATUS_DONE, signal_todo
from .entity import HeroldEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import HeroldCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the todo platform."""
    coordinator: HeroldCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HeroldInboxTodoEntity(coordinator)])


class HeroldInboxTodoEntity(HeroldEntity, TodoListEntity):
    """Inbox list backed by the Herold store (P1 notifications land here)."""

    _attr_translation_key = "inbox"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_inbox"

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the inbox items from the store."""
        return [
            TodoItem(
                uid=item["uid"],
                summary=item["summary"],
                status=(
                    TodoItemStatus.COMPLETED
                    if item.get("status") == TODO_STATUS_DONE
                    else TodoItemStatus.NEEDS_ACTION
                ),
                description=item.get("description"),
            )
            for item in self.coordinator.store.todo_items
        ]

    async def async_added_to_hass(self) -> None:
        """Subscribe to inbox updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_todo(self.coordinator.entry.entry_id),
                self._handle_todo_update,
            )
        )

    @callback
    def _handle_todo_update(self) -> None:
        self.async_write_ha_state()

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add an item manually via the UI."""
        self.coordinator.async_add_todo_item(
            uid=item.uid or uuid4().hex[:8],
            summary=item.summary or "",
            description=item.description,
        )

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update an item (summary, status, description)."""
        self.coordinator.async_update_todo_item(
            uid=item.uid,
            summary=item.summary,
            status=item.status.value if item.status else None,
            description=item.description,
        )

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete items."""
        self.coordinator.async_delete_todo_items(uids)
