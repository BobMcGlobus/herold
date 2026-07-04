"""Query lifecycle: create → deliver → answer/expire, with persistence.

Answers can arrive through several sources:

* Telegram inline buttons (``telegram_callback`` events) — legacy
  ``/AI_YES``-style callbacks for yesno, ``/HRLD_<id>_<index>`` for choices
* Telegram free text (``telegram_text`` events) for open queries
* The ``herold.acknowledge`` service (UI, automations, later LLM tools)
* Timeout with a configured ``default_answer``

On answer, Herold fires ``herold_answered`` with a structured payload plus —
for yesno queries — the legacy event name (``AI_YES``/``AI_NO`` or
``<custom>_YES``/``<custom>_NO``) for existing automations.

Herold deliberately does NOT call ``telegram_bot.answer_callback_query``:
existing legacy automations answer the callback themselves, and a second
answer for the same callback id would make their action run fail.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .channels.base import ChannelUnavailable
from .channels.telegram import choice_callback_data
from .const import (
    ANSWER_NO,
    ANSWER_YES,
    ATTR_ANSWER,
    ATTR_ID,
    ATTR_SOURCE,
    CHANNEL_TELEGRAM,
    CHANNEL_VOICE,
    CONF_TELEGRAM_CHAT_ID,
    EVENT_ANSWERED,
    EVENT_DELIVERED,
    EVENT_EXPIRED,
    QUERY_MODE_CHOICE,
    QUERY_MODE_OPEN,
    QUERY_MODE_YESNO,
    QUERY_STATUS_ANSWERED,
    QUERY_STATUS_CANCELLED,
    QUERY_STATUS_EXPIRED,
    TELEGRAM_CHOICE_PREFIX,
    signal_delivery,
    signal_query,
)
from .dispatcher import DispatchContext, select_query_channels, should_deliver
from .legacy_compat import get_legacy_event_names
from .models import DeliveryResult, Query

if TYPE_CHECKING:
    from collections.abc import Callable

    from .coordinator import HeroldCoordinator

_LOGGER = logging.getLogger(__name__)

_YES_WORDS = {"ja", "yes", "true", "1", "ok", "klar"}
_NO_WORDS = {"nein", "no", "false", "0"}


def normalize_yesno(answer: str) -> str | None:
    """Map a free-form yes/no answer to the canonical German form."""
    lowered = answer.strip().lower()
    if lowered in _YES_WORDS:
        return ANSWER_YES
    if lowered in _NO_WORDS:
        return ANSWER_NO
    return None


class QueryManager:
    """Owns all pending queries, their timers and answer sources."""

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator
        self.queries: dict[str, Query] = {}
        self._timers: dict[str, Callable[[], None]] = {}
        self._unsubs: list[Callable[[], None]] = []

    async def async_setup(self) -> None:
        """Restore pending queries from the store and attach listeners."""
        hass = self.coordinator.hass
        # list(): expiring a query below mutates store.queries via _persist
        for raw in list(self.coordinator.store.queries.values()):
            query = Query.from_dict(raw)
            self.queries[query.id] = query
            if not query.is_pending:
                continue
            if query.timeout_at <= dt_util.utcnow():
                await self._async_timeout(query)
            else:
                self._arm_timer(query)

        self._unsubs.append(
            hass.bus.async_listen("telegram_callback", self._async_telegram_callback)
        )
        self._unsubs.append(
            hass.bus.async_listen("telegram_text", self._async_telegram_text)
        )

    async def async_shutdown(self) -> None:
        """Cancel timers and detach listeners."""
        for cancel in self._timers.values():
            cancel()
        self._timers.clear()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @property
    def pending(self) -> list[Query]:
        """Return all pending queries, oldest first."""
        return sorted(
            (query for query in self.queries.values() if query.is_pending),
            key=lambda query: query.created_at,
        )

    @property
    def last_query(self) -> Query | None:
        """Return the most recently created query, regardless of status."""
        if not self.queries:
            return None
        return max(self.queries.values(), key=lambda query: query.created_at)

    async def async_ask(self, query: Query) -> DeliveryResult:
        """Run the dispatch pipeline for a query and start its timeout."""
        coordinator = self.coordinator
        ctx = DispatchContext(
            coordinator=coordinator,
            is_home=coordinator.is_home,
            is_dnd=coordinator.is_dnd_active(),
            internet_available=coordinator.internet_available,
        )
        result = DeliveryResult(notification_id=query.id)

        deliver, reason = should_deliver(query, ctx)
        if not deliver:
            _LOGGER.debug("Dropping query %s: %s", query.id, reason)
            return result

        active_room = await coordinator.async_get_active_room()
        for channel in select_query_channels(query, ctx):
            try:
                await channel.deliver_query(query, coordinator)
            except ChannelUnavailable as err:
                result.errors[channel.name] = str(err)
                _LOGGER.debug(
                    "Channel %s unavailable for query %s: %s",
                    channel.name,
                    query.id,
                    err,
                )
            except HomeAssistantError as err:
                result.errors[channel.name] = str(err)
                _LOGGER.warning(
                    "Query delivery via %s failed for %s: %s",
                    channel.name,
                    query.id,
                    err,
                )
            else:
                result.channels_used.append(channel.name)
                query.channels_delivered.append(channel.name)
                room_name = (
                    active_room.name
                    if channel.name == CHANNEL_VOICE and active_room
                    else None
                )
                if room_name:
                    result.room_used = room_name
                coordinator.hass.bus.async_fire(
                    EVENT_DELIVERED,
                    {
                        "id": query.id,
                        "channel": channel.name,
                        "room": room_name,
                        "priority": query.priority,
                    },
                )

        self.queries[query.id] = query
        self._arm_timer(query)
        self._persist(query)
        coordinator.note_delivery(result, query.priority)
        async_dispatcher_send(
            coordinator.hass, signal_delivery(coordinator.entry.entry_id)
        )
        self._notify_change()
        return result

    async def async_answer(
        self, query_id: str, answer: str, source: str
    ) -> Query:
        """Resolve a pending query with an answer."""
        query = self._get_pending(query_id)

        if query.mode == QUERY_MODE_YESNO:
            normalized = normalize_yesno(answer)
            if normalized is None:
                raise HomeAssistantError(
                    f"Query {query_id} expects yes/no, got: {answer!r}"
                )
            answer = normalized
        elif query.mode == QUERY_MODE_CHOICE:
            answer = self._match_choice(query, answer)

        query.status = QUERY_STATUS_ANSWERED
        query.answer = answer
        query.answered_at = dt_util.utcnow()
        query.answered_via = source
        self._cancel_timer(query.id)
        self._persist(query)

        hass = self.coordinator.hass
        hass.bus.async_fire(
            EVENT_ANSWERED,
            {
                ATTR_ID: query.id,
                ATTR_ANSWER: answer,
                "source_channel": source,
                "mode": query.mode,
                "callback_event": query.callback_event,
            },
        )
        if query.mode == QUERY_MODE_YESNO:
            # Legacy event names for existing automations (bit-exact with
            # the original script: AI_CONFIRM → AI_YES/AI_NO).
            yes_event, no_event = get_legacy_event_names(query.callback_event)
            legacy_event = yes_event if answer == ANSWER_YES else no_event
            hass.bus.async_fire(
                legacy_event,
                {ATTR_ID: query.id, ATTR_ANSWER: answer, ATTR_SOURCE: source},
            )

        _LOGGER.debug(
            "Query %s answered %r via %s", query.id, answer, source
        )
        self._notify_change()
        return query

    async def async_cancel(self, query_id: str, reason: str | None = None) -> None:
        """Cancel a pending query without firing answer events."""
        query = self._get_pending(query_id)
        query.status = QUERY_STATUS_CANCELLED
        self._cancel_timer(query.id)
        self._persist(query)
        _LOGGER.debug("Query %s cancelled: %s", query.id, reason or "no reason")
        self._notify_change()

    def _get_pending(self, query_id: str) -> Query:
        query = self.queries.get(query_id)
        if query is None:
            raise HomeAssistantError(f"Unknown query id: {query_id}")
        if not query.is_pending:
            raise HomeAssistantError(
                f"Query {query_id} is not pending (status: {query.status})"
            )
        return query

    def _match_choice(self, query: Query, answer: str) -> str:
        for choice in query.choices or []:
            if choice.strip().lower() == answer.strip().lower():
                return choice
        raise HomeAssistantError(
            f"Answer {answer!r} is not one of the choices for query {query.id}: "
            f"{query.choices}"
        )

    # -- Timeout handling --------------------------------------------------

    def _arm_timer(self, query: Query) -> None:
        delay = (query.timeout_at - dt_util.utcnow()).total_seconds()

        async def _fire(_now: Any) -> None:
            self._timers.pop(query.id, None)
            await self._async_timeout(query)

        self._timers[query.id] = async_call_later(
            self.coordinator.hass, max(delay, 0), _fire
        )

    def _cancel_timer(self, query_id: str) -> None:
        cancel = self._timers.pop(query_id, None)
        if cancel:
            cancel()

    async def _async_timeout(self, query: Query) -> None:
        if not query.is_pending:
            return
        if query.default_answer is not None:
            try:
                await self.async_answer(query.id, query.default_answer, "timeout")
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "Default answer for query %s invalid: %s", query.id, err
                )
            else:
                return
        query.status = QUERY_STATUS_EXPIRED
        self._persist(query)
        self.coordinator.hass.bus.async_fire(
            EVENT_EXPIRED, {ATTR_ID: query.id, "reason": "timeout"}
        )
        _LOGGER.debug("Query %s expired", query.id)
        self._notify_change()

    # -- Telegram answer sources -------------------------------------------

    @callback
    def _event_chat_matches(self, event: Event) -> bool:
        configured = self.coordinator.config.get(CONF_TELEGRAM_CHAT_ID)
        if not configured:
            return False
        return str(event.data.get("chat_id")) == str(configured)

    async def _async_telegram_callback(self, event: Event) -> None:
        """Resolve queries from inline button presses."""
        if not self._event_chat_matches(event):
            return
        data = str(event.data.get("data") or "")

        if data.startswith(f"{TELEGRAM_CHOICE_PREFIX}_"):
            await self._handle_choice_callback(data)
            return

        for query in self.pending:
            if query.mode != QUERY_MODE_YESNO:
                continue
            if CHANNEL_TELEGRAM not in query.channels_delivered:
                continue
            yes_event, no_event = get_legacy_event_names(query.callback_event)
            if data == f"/{yes_event}":
                answer = ANSWER_YES
            elif data == f"/{no_event}":
                answer = ANSWER_NO
            else:
                continue
            # Multiple pending queries can share the legacy callback data
            # (AI_CONFIRM default); prefer the one whose question matches
            # the button's message text, else take the oldest.
            message_text = str(
                (event.data.get("message") or {}).get("text") or ""
            )
            matched = self._match_by_message(message_text) or query
            await self.async_answer(matched.id, answer, CHANNEL_TELEGRAM)
            return

    def _match_by_message(self, message_text: str) -> Query | None:
        if not message_text:
            return None
        question = message_text.removeprefix("🟠 ")
        for query in self.pending:
            if (
                query.mode == QUERY_MODE_YESNO
                and CHANNEL_TELEGRAM in query.channels_delivered
                and query.question == question
            ):
                return query
        return None

    async def _handle_choice_callback(self, data: str) -> None:
        for query in self.pending:
            if query.mode != QUERY_MODE_CHOICE or not query.choices:
                continue
            for index, choice in enumerate(query.choices):
                if data == choice_callback_data(query.id, index):
                    await self.async_answer(query.id, choice, CHANNEL_TELEGRAM)
                    return
        _LOGGER.debug("Choice callback %s matched no pending query", data)

    async def _async_telegram_text(self, event: Event) -> None:
        """Resolve the oldest open query from a free-text Telegram reply."""
        if not self._event_chat_matches(event):
            return
        text = str(event.data.get("text") or "").strip()
        if not text:
            return
        for query in self.pending:
            if (
                query.mode == QUERY_MODE_OPEN
                and CHANNEL_TELEGRAM in query.channels_delivered
            ):
                await self.async_answer(query.id, text, CHANNEL_TELEGRAM)
                return

    # -- Persistence & signals ----------------------------------------------

    def _persist(self, query: Query) -> None:
        store = self.coordinator.store
        if query.is_pending:
            store.queries[query.id] = query.to_dict()
        else:
            # Resolved queries stay in memory for the sensors but leave
            # the store — pending state is the only thing worth a reboot.
            store.queries.pop(query.id, None)
        store.async_schedule_save()

    def _notify_change(self) -> None:
        async_dispatcher_send(
            self.coordinator.hass,
            signal_query(self.coordinator.entry.entry_id),
        )
