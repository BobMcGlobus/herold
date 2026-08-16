"""Internal channel: P0 self-callbacks executed by a conversation agent.

The notification message is an instruction for the LLM, delivered via
``conversation.process`` with the ``[HEROLD_INTERNAL]`` prefix so the agent's
prompt template can recognize it as a silent self-reminder.

Three levels of assurance, cheapest first:

1. The agent's response is captured (``return_response=True``) and inspected —
   an ``error`` response type or reported target failures are hard evidence
   that the instruction did not run.
2. If the primary agent raises (e.g. cloud agent while offline), the
   configured fallback agent (typically a local Ollama) takes over.
3. Optionally a single self-check turn asks the agent to verify the resulting
   device state and correct it once. The check never recurses — a correction
   is not verified again — so a P0 costs at most two agent turns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from ..const import (
    CHANNEL_INTERNAL,
    CONF_ENABLE_P0_VERIFICATION,
    CONF_P0_AGENT_ID,
    CONF_P0_FALLBACK_AGENT_ID,
    DEFAULT_ENABLE_P0_VERIFICATION,
    EVENT_INTERNAL_TRIGGERED,
    EVENT_INTERNAL_VERIFIED,
    HEROLD_INTERNAL_PREFIX,
    INTERNAL_RESULT_CORRECTED,
    INTERNAL_RESULT_FAILED,
    INTERNAL_RESULT_OK,
    INTERNAL_RESULT_UNVERIFIED,
    VERIFY_TOKEN_CORRECTED,
    VERIFY_TOKEN_FAILED,
    VERIFY_TOKEN_OK,
)
from ..models import InternalResult
from .base import BaseChannel, ChannelUnavailable

if TYPE_CHECKING:
    from ..coordinator import HeroldCoordinator
    from ..models import Notification

_LOGGER = logging.getLogger(__name__)

VERIFY_PROMPT = (
    "{prefix} Self-check: you just executed this instruction: "
    '"{instruction}". Now verify the actual state of the affected devices, '
    "or whether the message really went out. If something is missing, "
    "perform exactly that missing part now. Reply with a single word and "
    "nothing else: {ok} if everything was already correct, {corrected} if "
    "you fixed something, {failed} if it is not possible. Do not address "
    "the user."
)


class InternalChannel(BaseChannel):
    """Execute P0 instructions through a conversation agent."""

    name = CHANNEL_INTERNAL
    offline_capable = False  # True only with a local fallback agent, checked live

    async def deliver(
        self, notification: Notification, coordinator: HeroldCoordinator
    ) -> None:
        """Run the instruction, inspect the outcome and optionally verify it."""
        agent_id = coordinator.config.get(CONF_P0_AGENT_ID)
        if not agent_id:
            raise ChannelUnavailable(
                "No P0 conversation agent configured (options → LLM)"
            )
        if not coordinator.p0_allowed():
            raise ChannelUnavailable(
                "P0 rate limit reached (anti-runaway); instruction dropped"
            )

        task_context = notification.context.get("task_context")
        text = self._build_prompt(notification.message, task_context)
        conversation_id = f"herold_internal_{notification.id}"

        used_agent = agent_id
        try:
            response = await self._process(
                coordinator, agent_id, text, conversation_id
            )
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
            response = await self._process(
                coordinator, fallback, text, conversation_id
            )
            used_agent = fallback

        speech, error_reason = self._inspect(response)
        result = InternalResult(
            notification_id=notification.id,
            instruction=notification.message,
            agent_id=used_agent,
            status=INTERNAL_RESULT_FAILED
            if error_reason
            else INTERNAL_RESULT_UNVERIFIED,
            speech=speech,
            detail=error_reason,
        )

        coordinator.hass.bus.async_fire(
            EVENT_INTERNAL_TRIGGERED,
            {
                "id": notification.id,
                "instruction": notification.message,
                "agent_id": used_agent,
                "speech": speech,
                "error": error_reason,
            },
        )

        if error_reason is None and self._verification_enabled(coordinator):
            await self._verify(
                coordinator, notification, conversation_id, used_agent, result
            )

        coordinator.note_internal(result)
        if result.status == INTERNAL_RESULT_FAILED:
            raise ChannelUnavailable(
                result.detail or "Agent reported that the instruction failed"
            )

    @staticmethod
    def _build_prompt(instruction: str, task_context: str | None) -> str:
        """Prefix the instruction, optionally with the original conversation.

        The scaffolding is English (like every Herold prompt); the
        instruction and context themselves stay in whatever language the
        user and the agent spoke.
        """
        if task_context:
            return (
                f"{HEROLD_INTERNAL_PREFIX} Background from the earlier "
                f"conversation: {task_context}. Instruction: {instruction}"
            )
        return f"{HEROLD_INTERNAL_PREFIX} {instruction}"

    @staticmethod
    def _verification_enabled(coordinator: HeroldCoordinator) -> bool:
        return bool(
            coordinator.config.get(
                CONF_ENABLE_P0_VERIFICATION, DEFAULT_ENABLE_P0_VERIFICATION
            )
        )

    async def _verify(
        self,
        coordinator: HeroldCoordinator,
        notification: Notification,
        conversation_id: str,
        agent_id: str,
        result: InternalResult,
    ) -> None:
        """Run a single self-check turn in the same conversation."""
        prompt = VERIFY_PROMPT.format(
            prefix=HEROLD_INTERNAL_PREFIX,
            instruction=notification.message,
            ok=VERIFY_TOKEN_OK,
            corrected=VERIFY_TOKEN_CORRECTED,
            failed=VERIFY_TOKEN_FAILED,
        )
        try:
            response = await self._process(
                coordinator, agent_id, prompt, conversation_id
            )
        except HomeAssistantError as err:
            _LOGGER.debug(
                "Verification turn for %s failed: %s", notification.id, err
            )
            result.detail = f"Verification unavailable: {err}"
            return

        speech, error_reason = self._inspect(response)
        verdict = self._classify_verdict(speech, error_reason)
        result.status = verdict
        result.verified = True
        if speech:
            result.speech = speech

        coordinator.hass.bus.async_fire(
            EVENT_INTERNAL_VERIFIED,
            {
                "id": notification.id,
                "instruction": notification.message,
                "result": verdict,
                "speech": speech,
            },
        )
        _LOGGER.debug(
            "P0 %s self-check: %s (%r)", notification.id, verdict, speech
        )

    @staticmethod
    def _classify_verdict(speech: str | None, error_reason: str | None) -> str:
        """Map the agent's self-check answer onto a result status."""
        if error_reason:
            return INTERNAL_RESULT_FAILED
        upper = (speech or "").upper()
        if VERIFY_TOKEN_FAILED in upper:
            return INTERNAL_RESULT_FAILED
        if VERIFY_TOKEN_CORRECTED in upper:
            return INTERNAL_RESULT_CORRECTED
        if VERIFY_TOKEN_OK in upper:
            return INTERNAL_RESULT_OK
        # Agent answered something else entirely — no evidence either way.
        return INTERNAL_RESULT_UNVERIFIED

    @staticmethod
    def _inspect(response: Any) -> tuple[str | None, str | None]:
        """Return (speech, error_reason) from a conversation.process result."""
        if not isinstance(response, dict):
            return (None, None)
        payload = response.get("response") or {}
        speech = (
            ((payload.get("speech") or {}).get("plain") or {}).get("speech")
            or None
        )
        if payload.get("response_type") == "error":
            code = (payload.get("data") or {}).get("code", "unknown")
            return (speech, f"Agent error ({code}): {speech or 'no detail'}")
        failed = (payload.get("data") or {}).get("failed") or []
        if failed:
            return (speech, f"Agent could not act on {len(failed)} target(s)")
        return (speech, None)

    async def _process(
        self,
        coordinator: HeroldCoordinator,
        agent_id: str,
        text: str,
        conversation_id: str,
    ) -> Any:
        return await coordinator.hass.services.async_call(
            "conversation",
            "process",
            {
                "agent_id": agent_id,
                "text": text,
                "conversation_id": conversation_id,
            },
            blocking=True,
            return_response=True,
        )
