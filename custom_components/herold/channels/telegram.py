"""Telegram delivery channel with legacy-compatible inline buttons.

The button callback data format is pinned to the original script so existing
``telegram_callback`` automations keep working unchanged:

* ``callback_event="AI_CONFIRM"`` → buttons ``✅ Ja bitte:/AI_YES`` and
  ``❌ Nein danke:/AI_NO``
* custom ``callback_event="XYZ"`` → ``✅ Ja:/XYZ_YES`` and ``❌ Nein:/XYZ_NO``

Choice-mode buttons are new in Herold and use the ``/HRLD_<id>_<index>``
callback prefix, which the query manager resolves internally.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..const import (
    CHANNEL_TELEGRAM,
    CONF_PENDING_QUESTION_ENTITY,
    CONF_TELEGRAM_CHAT_ID,
    LEGACY_DEFAULT_CALLBACK,
    QUERY_MODE_CHOICE,
    QUERY_MODE_OPEN,
    QUERY_MODE_YESNO,
    TELEGRAM_CHOICE_PREFIX,
)
from ..legacy_compat import get_legacy_event_names
from .base import BaseChannel, ChannelUnavailable

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification, Query

_LOGGER = logging.getLogger(__name__)


def choice_callback_data(query_id: str, index: int) -> str:
    """Return the callback data for a choice button."""
    return f"{TELEGRAM_CHOICE_PREFIX}_{query_id}_{index}"


class TelegramChannel(BaseChannel):
    """Deliver notifications and queries via telegram_bot."""

    name = CHANNEL_TELEGRAM
    offline_capable = False  # needs the Telegram backend; queue lands later

    async def deliver(
        self, notification: Notification, coordinator: HeroldCoordinator
    ) -> None:
        """Send a plain info message."""
        chat_id = self._chat_id(coordinator)
        await coordinator.hass.services.async_call(
            "telegram_bot",
            "send_message",
            {"message": notification.message, "target": chat_id},
            blocking=True,
        )

    async def deliver_query(
        self, query: Query, coordinator: HeroldCoordinator
    ) -> None:
        """Send a query with inline buttons (yesno/choice) or as open question."""
        chat_id = self._chat_id(coordinator)
        hass = coordinator.hass

        if query.mode == QUERY_MODE_YESNO:
            yes_event, no_event = get_legacy_event_names(query.callback_event)
            if query.callback_event == LEGACY_DEFAULT_CALLBACK:
                keyboard = [f"✅ Ja bitte:/{yes_event}, ❌ Nein danke:/{no_event}"]
            else:
                keyboard = [f"✅ Ja:/{yes_event}, ❌ Nein:/{no_event}"]
            await hass.services.async_call(
                "telegram_bot",
                "send_message",
                {
                    "message": f"🟠 {query.question}",
                    "inline_keyboard": keyboard,
                    "target": chat_id,
                },
                blocking=True,
            )
        elif query.mode == QUERY_MODE_CHOICE:
            keyboard = [
                f"{choice}:{choice_callback_data(query.id, index)}"
                for index, choice in enumerate(query.choices or [])
            ]
            await hass.services.async_call(
                "telegram_bot",
                "send_message",
                {
                    "message": f"🟠 {query.question}",
                    "inline_keyboard": keyboard,
                    "target": chat_id,
                },
                blocking=True,
            )
        elif query.mode == QUERY_MODE_OPEN:
            await self._set_pending_question(coordinator, query.question)
            await hass.services.async_call(
                "telegram_bot",
                "send_message",
                {"message": f"❓ {query.question}", "target": chat_id},
                blocking=True,
            )
        else:
            raise ChannelUnavailable(f"Unknown query mode: {query.mode}")

    async def _set_pending_question(
        self, coordinator: HeroldCoordinator, question: str
    ) -> None:
        """Mirror the open question into the legacy input_text helper.

        Keeps the existing telegram_chat_mit_ai automation working, which
        reads input_text.ai_pending_question to build the answer context.
        """
        entity_id = coordinator.config.get(CONF_PENDING_QUESTION_ENTITY)
        if not entity_id:
            return
        await coordinator.hass.services.async_call(
            "input_text",
            "set_value",
            {"entity_id": entity_id, "value": question[:255]},
            blocking=True,
        )

    def _chat_id(self, coordinator: HeroldCoordinator) -> int:
        raw = coordinator.config.get(CONF_TELEGRAM_CHAT_ID)
        if not raw:
            raise ChannelUnavailable("No Telegram chat id configured")
        return int(raw)
