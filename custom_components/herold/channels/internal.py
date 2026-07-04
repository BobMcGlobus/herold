"""Internal channel: P0 self-callbacks executed by a conversation agent.

The notification message is an instruction for the LLM, delivered via
``conversation.process`` with the ``[HEROLD_INTERNAL]`` prefix so the agent's
prompt template can recognize it as a silent self-reminder. If the primary
agent fails (e.g. cloud agent while offline), the configured fallback agent
(typically a local Ollama) takes over.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.exceptions import HomeAssistantError

from ..const import (
    CHANNEL_INTERNAL,
    CONF_P0_AGENT_ID,
    CONF_P0_FALLBACK_AGENT_ID,
    EVENT_INTERNAL_TRIGGERED,
    HEROLD_INTERNAL_PREFIX,
)
from .base import BaseChannel, ChannelUnavailable

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification

_LOGGER = logging.getLogger(__name__)


class InternalChannel(BaseChannel):
    """Execute P0 instructions through a conversation agent."""

    name = CHANNEL_INTERNAL
    offline_capable = False  # True only with a local fallback agent, checked live

    async def deliver(
        self, notification: Notification, coordinator: HeroldCoordinator
    ) -> None:
        """Run the instruction through the configured agent."""
        agent_id = coordinator.config.get(CONF_P0_AGENT_ID)
        if not agent_id:
            raise ChannelUnavailable(
                "No P0 conversation agent configured (options → LLM)"
            )
        if not coordinator.p0_allowed():
            raise ChannelUnavailable(
                "P0 rate limit reached (anti-runaway); instruction dropped"
            )

        text = f"{HEROLD_INTERNAL_PREFIX} {notification.message}"
        conversation_id = f"herold_internal_{notification.id}"
        used_agent = agent_id
        try:
            await self._process(coordinator, agent_id, text, conversation_id)
        except HomeAssistantError as err:
            fallback = coordinator.config.get(CONF_P0_FALLBACK_AGENT_ID)
            if not fallback:
                raise
            _LOGGER.warning(
                "P0 agent %s failed (%s); retrying with fallback %s",
                agent_id,
                err,
                fallback,
            )
            await self._process(coordinator, fallback, text, conversation_id)
            used_agent = fallback

        coordinator.hass.bus.async_fire(
            EVENT_INTERNAL_TRIGGERED,
            {
                "id": notification.id,
                "instruction": notification.message,
                "agent_id": used_agent,
            },
        )

    async def _process(
        self,
        coordinator: HeroldCoordinator,
        agent_id: str,
        text: str,
        conversation_id: str,
    ) -> None:
        await coordinator.hass.services.async_call(
            "conversation",
            "process",
            {
                "agent_id": agent_id,
                "text": text,
                "conversation_id": conversation_id,
            },
            blocking=True,
        )
