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
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import (
    CONF_ENABLE_TOOL_CONFIRMATIONS,
    DEFAULT_ALARM_MESSAGE,
    DEFAULT_ENABLE_TOOL_CONFIRMATIONS,
    DEFAULT_PRIORITY,
    DEFAULT_WATCH_TTL_HOURS,
    DOMAIN,
    MAX_WATCH_TTL_HOURS,
    PRIORITY_INTERNAL,
    TODO_STATUS_OPEN,
    URGENCY_LEVELS,
    URGENCY_NORMAL,
    WEEKDAYS,
)
from .entity_resolver import normalize_trigger, resolve_entity
from .models import Alarm, Schedule, Watch
from .scheduler import parse_when
from .watcher import ttl_to_expiry

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant

    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)

API_PROMPT = (
    "Herold is the household notification system. It tracks pending "
    "notifications (todos), open queries waiting for the user's answer, and "
    "scheduled reminders. Use herold_list_pending proactively when the user "
    "asks what is new or before ending a conversation. Use herold_remind_self "
    "for anything the user wants done later — never the calendar, never any "
    "other scheduling helper. "
    "\n\nIMPORTANT: whenever a Herold tool returns a 'confirmation' field, "
    "say that sentence to the user (you may rephrase slightly, but keep the "
    "time and the fact that it is stored). The user must always know whether "
    "something was really registered. If a tool returns success=false, tell "
    "the user plainly that it did NOT work and why."
    "\n\nHerold also manages the alarm clocks (herold_set_alarm, "
    "herold_list_alarms, herold_cancel_alarm). When an alarm is ringing the "
    "user can say 'aus'/'stopp' or 'snooze' — those are handled by Herold "
    "itself, do not call a tool for them."
)

_WEEKDAYS = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)


# The model answers in the user's language, and "Dienstag"[:3] is "die",
# not "tue" — map the German day names explicitly.
_DAY_ALIASES = {
    "montag": "mon", "mo": "mon", "monday": "mon",
    "dienstag": "tue", "di": "tue", "tuesday": "tue",
    "mittwoch": "wed", "mi": "wed", "wednesday": "wed",
    "donnerstag": "thu", "do": "thu", "thursday": "thu",
    "freitag": "fri", "fr": "fri", "friday": "fri",
    "samstag": "sat", "sonnabend": "sat", "sa": "sat", "saturday": "sat",
    "sonntag": "sun", "so": "sun", "sunday": "sun",
}


def canonical_day(value: str) -> str | None:
    """Map a weekday name in any accepted spelling to mon..sun."""
    cleaned = value.strip().lower()
    if cleaned in WEEKDAYS:
        return cleaned
    return _DAY_ALIASES.get(cleaned)


def describe_when(moment: datetime, hass: HomeAssistant) -> str:
    """Render a UTC moment as a German phrase ('morgen um 08:00 Uhr')."""
    local = dt_util.as_local(moment)
    now = dt_util.now()
    clock = local.strftime("%H:%M")
    delta_days = (local.date() - now.date()).days
    if delta_days == 0:
        return f"heute um {clock} Uhr"
    if delta_days == 1:
        return f"morgen um {clock} Uhr"
    if 2 <= delta_days < 7:
        return f"am {_WEEKDAYS[local.weekday()]} um {clock} Uhr"
    return f"am {local.strftime('%d.%m.')} um {clock} Uhr"


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
                RemindWhenTool(self.coordinator),
                CancelTool(self.coordinator),
                ListAlarmsTool(self.coordinator),
                SetAlarmTool(self.coordinator),
                CancelAlarmTool(self.coordinator),
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
            return {
                "success": False,
                "error": str(err),
                "confirmation": f"Das hat nicht geklappt: {err}",
            }
        except Exception:
            # A bug inside a tool must not abort the whole conversation —
            # without this the pipeline dies with "intent-failed" and the
            # user gets no answer at all.
            _LOGGER.exception("Herold tool %s raised unexpectedly", self.name)
            return {
                "success": False,
                "error": (
                    "internal Herold error — details are in the Home "
                    "Assistant log"
                ),
                "confirmation": (
                    "Da ist in Herold intern etwas schiefgelaufen. Die "
                    "Einzelheiten stehen im Home-Assistant-Log."
                ),
            }

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def _confirm(self, result: dict[str, Any], sentence: str) -> dict[str, Any]:
        """Attach a ready-to-speak confirmation unless disabled in options."""
        if self.coordinator.config.get(
            CONF_ENABLE_TOOL_CONFIRMATIONS, DEFAULT_ENABLE_TOOL_CONFIRMATIONS
        ):
            result["confirmation"] = sentence
        return result


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
        "{id, question, mode, choices}, scheduled {id, when, message} and "
        "watches {id, condition, message} — the latter are reminders waiting "
        "for a device state change."
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
                "when": describe_when(schedule.scheduled_for, coordinator.hass),
                "message": schedule.payload.get("message"),
            }
            for schedule in coordinator.scheduler.pending
        ]
        watches = [
            {
                "id": watch.id,
                "condition": watch.describe(),
                "message": watch.payload.get("message"),
            }
            for watch in coordinator.watcher.active
        ]
        return {
            "todos": todos,
            "queries": queries,
            "scheduled": scheduled,
            "watches": watches,
        }


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
        return self._confirm(
            {"success": True, "id": uid}, "Erledigt, ich hake das ab."
        )


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
        return self._confirm(
            {"success": True, "id": query.id, "answer": query.answer},
            f"Ich habe deine Antwort «{query.answer}» weitergegeben.",
        )


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
        "when accepts '+30m', '+1h30m', '18:00' or an ISO datetime. "
        "\n\nPass 'context' with a short summary of WHY this was scheduled "
        "(what the user said, what it is about) — you will receive it again "
        "when the reminder fires, which is often the difference between "
        "executing it correctly and guessing. "
        "\n\nWhen it triggers, a fresh conversation receives the instruction "
        "prefixed with [HEROLD_INTERNAL]; execute it silently. "
        "ALWAYS read the returned 'confirmation' back to the user so they "
        "know it was really stored."
    )
    parameters = vol.Schema(
        {
            vol.Required("when"): str,
            vol.Required("instruction"): str,
            vol.Optional("context"): str,
        }
    )

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        scheduled_for = parse_when(kwargs["when"])
        payload: dict[str, Any] = {
            "message": kwargs["instruction"],
            "priority": PRIORITY_INTERNAL,
        }
        if task_context := kwargs.get("context"):
            payload["context"] = {"task_context": task_context}
        schedule = Schedule(scheduled_for=scheduled_for, payload=payload)
        await self.coordinator.scheduler.async_add(schedule)
        phrase = describe_when(scheduled_for, self.coordinator.hass)
        return self._confirm(
            {
                "success": True,
                "id": schedule.id,
                "scheduled_for": scheduled_for.isoformat(),
            },
            f"Ist gespeichert — ich kümmere mich {phrase} darum.",
        )


class RemindWhenTool(HeroldTool):
    """Arm a one-shot reminder tied to a state change."""

    name = "herold_remind_when"
    description = (
        "Arm a one-shot reminder that fires the next time a device or sensor "
        "changes state — the counterpart to herold_remind_self for things "
        "without a fixed time. Use it for 'wenn ich das nächste Mal die "
        "Haustür öffne', 'sobald die Waschmaschine fertig ist', 'wenn ich "
        "nach Hause komme', 'wenn es unter 5 Grad wird'. "
        "\n\nParameters: entity (the device to observe — an exact entity id "
        "if you know it, otherwise just the name the user said, e.g. "
        "'Klimaanlage Arbeitszimmer'; it is matched against the exposed "
        "entities and their aliases), message (what to announce when it "
        "happens), optionally to_state (e.g. 'on', 'open', 'home'), "
        "above/below for numeric sensors, priority (default 2) and ttl_hours "
        "(default 72, 0 = never expires). "
        "\n\nUse to_state='on' for 'turns on' and 'off' for 'turns off' "
        "whatever the domain is — Herold translates that into the states the "
        "device actually reports (a climate entity reports 'cool'/'heat', "
        "not 'on'). "
        "\n\nIf the entity cannot be matched, the error lists concrete "
        "entity ids — call again with one of them instead of guessing, or "
        "ask the user which device is meant. The result contains the "
        "resolved friendly name in 'confirmation'; read it back so a wrong "
        "match is caught. The watch fires once and then removes itself."
    )
    parameters = vol.Schema(
        {
            vol.Required("entity"): str,
            vol.Required("message"): str,
            vol.Optional("to_state"): str,
            vol.Optional("from_state"): str,
            vol.Optional("above"): vol.Coerce(float),
            vol.Optional("below"): vol.Coerce(float),
            vol.Optional("priority"): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=4)
            ),
            vol.Optional("ttl_hours"): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=MAX_WATCH_TTL_HOURS)
            ),
        }
    )

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        coordinator = self.coordinator
        # Accept "entity_id" too — models reach for it out of habit.
        reference = kwargs.get("entity") or kwargs.get("entity_id") or ""
        entity_id, friendly_name = resolve_entity(coordinator.hass, reference)
        to_state, from_state = normalize_trigger(
            entity_id, kwargs.get("to_state"), kwargs.get("from_state")
        )
        watch = Watch(
            entity_id=entity_id,
            payload={
                "message": kwargs["message"],
                "priority": kwargs.get("priority", DEFAULT_PRIORITY),
            },
            to_state=to_state,
            from_state=from_state,
            above=kwargs.get("above"),
            below=kwargs.get("below"),
            expires_at=ttl_to_expiry(
                kwargs.get("ttl_hours", DEFAULT_WATCH_TTL_HOURS)
            ),
            friendly_name=friendly_name,
        )
        await coordinator.watcher.async_add(watch)
        return self._confirm(
            {
                "success": True,
                "id": watch.id,
                "entity_id": entity_id,
                "condition": watch.describe(),
            },
            f"Ist notiert — ich melde mich, {watch.describe()}.",
        )


class CancelTool(HeroldTool):
    """Cancel a scheduled reminder or a pending query."""

    name = "herold_cancel"
    description = (
        "Cancel a scheduled reminder, a state watch or a pending query by its "
        "id. Use when the user revokes something they asked for earlier: "
        "'vergiss die Erinnerung', 'brauche ich doch nicht mehr', 'streich "
        "den Termin'. Get the id from herold_list_pending first — if several "
        "entries could be meant, ask the user which one. Read the returned "
        "'confirmation' back so the user knows it is really gone."
    )
    parameters = vol.Schema({vol.Required("id"): str})

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        item_id = kwargs["id"]
        coordinator = self.coordinator
        query = coordinator.query_manager.queries.get(item_id)
        if query is not None and query.is_pending:
            await coordinator.query_manager.async_cancel(item_id, "cancelled by LLM")
        elif not await coordinator.scheduler.async_cancel(
            item_id
        ) and not await coordinator.watcher.async_cancel(item_id):
            raise HomeAssistantError(
                f"No pending reminder, watch or query with id {item_id}"
            )
        return self._confirm(
            {"success": True, "id": item_id}, "Erledigt, das ist gestrichen."
        )


class ListAlarmsTool(HeroldTool):
    """List the configured alarm clocks."""

    name = "herold_list_alarms"
    description = (
        "List all alarm clocks with their id, time, repeat days and status. "
        "Call this when the user asks 'wann klingelt mein Wecker', 'welche "
        "Wecker habe ich', 'ist ein Wecker gestellt', or before changing an "
        "alarm so you know which one is meant."
    )
    parameters = vol.Schema({})

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "alarms": [
                {
                    "id": alarm.id,
                    "time": alarm.time,
                    "schedule": alarm.describe(),
                    "label": alarm.label,
                    "status": alarm.status,
                    "enabled": alarm.enabled,
                    "urgency": alarm.urgency,
                    "workday_only": alarm.workday_only,
                }
                for alarm in self.coordinator.alarms.all_alarms
            ]
        }


class SetAlarmTool(HeroldTool):
    """Create an alarm clock."""

    name = "herold_set_alarm"
    description = (
        "Set an alarm clock. Use for 'stell mir einen Wecker für 7 Uhr', "
        "'weck mich morgen um halb acht', 'jeden Werktag um 6:30 wecken'. "
        "\n\nParameters: time as 'HH:MM' in 24h format; days as a list of "
        "'mon','tue','wed','thu','fri','sat','sun' for a repeating alarm "
        "(omit for a one-shot alarm tomorrow or later today); optional label "
        "('Arbeit') and message (what Herold says when it rings). "
        "\n\nRead the returned 'confirmation' back to the user."
    )
    parameters = vol.Schema(
        {
            vol.Required("time"): str,
            vol.Optional("days"): [str],
            vol.Optional("label"): str,
            vol.Optional("message"): str,
            vol.Optional("urgency"): vol.In(URGENCY_LEVELS),
            vol.Optional("workday_only"): bool,
        }
    )

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        requested = kwargs.get("days") or []
        days = [day for raw in requested if (day := canonical_day(raw))]
        if len(days) != len(requested):
            unknown = [raw for raw in requested if not canonical_day(raw)]
            raise HomeAssistantError(
                f"Invalid weekday(s): {unknown} — use mon, tue, wed, thu, "
                "fri, sat or sun"
            )
        alarm = Alarm(
            time=kwargs["time"],
            days=days,
            label=kwargs.get("label"),
            message=kwargs.get("message") or DEFAULT_ALARM_MESSAGE,
            urgency=kwargs.get("urgency", URGENCY_NORMAL),
            workday_only=bool(kwargs.get("workday_only", False)),
        )
        await self.coordinator.alarms.async_add(alarm)
        return self._confirm(
            {
                "success": True,
                "id": alarm.id,
                "schedule": alarm.describe(),
            },
            f"Wecker gestellt: {alarm.describe()}.",
        )


class CancelAlarmTool(HeroldTool):
    """Delete an alarm clock."""

    name = "herold_cancel_alarm"
    description = (
        "Delete an alarm clock by its id ('lösch den Wecker', 'ich brauche "
        "morgen keinen Wecker'). Get the id from herold_list_alarms first; "
        "if more than one could be meant, ask which one. To silence an alarm "
        "that is ringing right now, this is the wrong tool — the user should "
        "say 'aus' or 'snooze' and you should not call anything."
    )
    parameters = vol.Schema({vol.Required("id"): str})

    async def _run(self, **kwargs: Any) -> dict[str, Any]:
        if not await self.coordinator.alarms.async_cancel(kwargs["id"]):
            raise HomeAssistantError(f"Unknown alarm id: {kwargs['id']}")
        return self._confirm(
            {"success": True, "id": kwargs["id"]}, "Der Wecker ist gelöscht."
        )
