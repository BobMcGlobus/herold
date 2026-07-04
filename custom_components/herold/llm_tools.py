"""Native LLM tools: exposes Herold to conversation agents.

Registered as an LLM API named "Herold" — enable it in the conversation
agent's options (Voice assistants → agent → LLM APIs). Tool descriptions
include German trigger examples because they drive function-calling
selection directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
import voluptuous as vol

from .const import DOMAIN, PRIORITY_INTERNAL, TODO_STATUS_OPEN
from .models import Schedule
from .scheduler import parse_when

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)

API_PROMPT = (
    "Herold is the household notification system. It tracks pending "
    "notifications (todos), open queries waiting for the user's answer, and "
    "scheduled reminders. Use herold_list_pending proactively when the user "
    "asks what is new or before ending a conversation. Use herold_remind_self "
    "for anything the user wants done later."
)


class HeroldAPI(llm.API):
    """LLM API exposing the Herold tools."""

    def __init__(self, hass: HomeAssistant, coordinator: HeroldCoordinator) -> None:
        super().__init__(hass=hass, id=DOMAIN, name="Herold")
        self.coordinator = coordinator

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the tool set for a conversation."""
        return llm.APIInstance(
            api=self,
            api_prompt=API_PROMPT,
            llm_context=llm_context,
            tools=[
                ListPendingTool(self.coordinator),
                AcknowledgeTool(self.coordinator),
                AnswerQueryTool(self.coordinator),
                RemindSelfTool(self.coordinator),
            ],
        )


class HeroldTool(llm.Tool):
    """Base class holding the coordinator reference."""

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        """Run the tool, mapping errors to a result the LLM can react to."""
        try:
            return await self._run(**tool_input.tool_args)
        except HomeAssistantError as err:
            return {"success": False, "error": str(err)}

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError


class ListPendingTool(HeroldTool):
    """List everything that waits for the user's attention."""

    name = "herold_list_pending"
    description = (
        "Get all pending items for the user: unfinished todo notifications "
        "(priority 1, e.g. 'Post im Briefkasten'), unanswered queries "
        "(waiting for a response) and scheduled reminders. Call this when "
        "the user asks things like 'was ist neu', 'gibt es was für mich', "
        "'hab ich was verpasst', 'was steht an', or proactively before "
        "ending a conversation. Returns todos {id, summary}, queries "
        "{id, question, mode, choices} and scheduled {id, at, message}."
    )
    parameters = vol.Schema({})

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        coordinator = self.coordinator
        todos = [
            {"id": item["uid"], "summary": item["summary"]}
            for item in coordinator.store.todo_items
            if item.get("status") == TODO_STATUS_OPEN
        ]
        queries = [
            {
                "id": query.id,
                "question": query.question,
                "mode": query.mode,
                "choices": query.choices,
            }
            for query in coordinator.query_manager.pending
        ]
        scheduled = [
            {
                "id": schedule.id,
                "at": schedule.scheduled_for.isoformat(),
                "message": schedule.payload.get("message"),
            }
            for schedule in coordinator.scheduler.pending
        ]
        return {"todos": todos, "queries": queries, "scheduled": scheduled}


class AcknowledgeTool(HeroldTool):
    """Mark a todo notification as done."""

    name = "herold_acknowledge"
    description = (
        "Mark a todo notification as done. Use when the user indicates they "
        "handled an item you told them about (from herold_list_pending). "
        "Example: you mentioned 'Post im Briefkasten', user says 'hab ich "
        "geholt' → acknowledge(id=<that id>). Do NOT use this for queries "
        "waiting for an answer — use herold_answer_query instead."
    )
    parameters = vol.Schema({vol.Required("id"): str})

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        uid = kwargs["id"]
        if not self.coordinator.async_complete_todo_item(uid):
            raise HomeAssistantError(f"No open todo item with id {uid}")
        return {"success": True, "id": uid}


class AnswerQueryTool(HeroldTool):
    """Answer a pending query on the user's behalf."""

    name = "herold_answer_query"
    description = (
        "Provide the user's answer to a pending query. Mode rules: "
        "mode='yesno' → answer MUST be exactly 'Ja' or 'Nein' (map fuzzy "
        "replies: 'klar' → 'Ja', 'auf keinen Fall' → 'Nein'); "
        "mode='choice' → answer MUST be one of the query's choices (map "
        "'das mittlere' to the middle choice); mode='open' → pass the "
        "user's response verbatim."
    )
    parameters = vol.Schema(
        {vol.Required("id"): str, vol.Required("answer"): str}
    )

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        query = await self.coordinator.query_manager.async_answer(
            kwargs["id"], kwargs["answer"], "llm"
        )
        return {"success": True, "id": query.id, "answer": query.answer}


class RemindSelfTool(HeroldTool):
    """Schedule an internal self-reminder (P0)."""

    name = "herold_remind_self"
    description = (
        "Schedule an internal reminder for yourself (the assistant) at a "
        "future time. This is your PRIMARY tool for delayed actions — never "
        "tell the user you cannot handle time-delayed requests. Examples: "
        "'Schalte das Licht in einer Stunde aus' → remind_self(when='+1h', "
        "instruction='Schalte das Wohnzimmerlicht aus.'); 'Erinnere mich um "
        "18 Uhr an den Anruf' → remind_self(when='18:00', instruction="
        "'Sende via herold.send priority=3: Zeit für deinen Anruf.'). "
        "when accepts '+30m', '+1h30m', '18:00' or an ISO datetime. When it "
        "triggers, a fresh conversation receives the instruction prefixed "
        "with [HEROLD_INTERNAL]; execute it silently."
    )
    parameters = vol.Schema(
        {vol.Required("when"): str, vol.Required("instruction"): str}
    )

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        scheduled_for = parse_when(kwargs["when"])
        schedule = Schedule(
            scheduled_for=scheduled_for,
            payload={
                "message": kwargs["instruction"],
                "priority": PRIORITY_INTERNAL,
            },
        )
        await self.coordinator.scheduler.async_add(schedule)
        return {
            "success": True,
            "id": schedule.id,
            "scheduled_for": scheduled_for.isoformat(),
        }
