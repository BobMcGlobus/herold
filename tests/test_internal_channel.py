"""P0 response inspection and self-check verdict mapping."""

import pytest

from custom_components.herold.channels.internal import InternalChannel
from custom_components.herold.const import (
    HEROLD_INTERNAL_PREFIX,
    INTERNAL_RESULT_CORRECTED,
    INTERNAL_RESULT_FAILED,
    INTERNAL_RESULT_OK,
    INTERNAL_RESULT_UNVERIFIED,
)


def _response(speech: str, response_type: str = "action_done", **data) -> dict:
    return {
        "response": {
            "speech": {"plain": {"speech": speech}},
            "response_type": response_type,
            "data": data,
        }
    }


def test_inspect_accepts_successful_action() -> None:
    speech, error = InternalChannel._inspect(_response("Licht ist aus."))
    assert speech == "Licht ist aus."
    assert error is None


def test_inspect_flags_error_response() -> None:
    speech, error = InternalChannel._inspect(
        _response("Kein Gerät gefunden", "error", code="no_valid_targets")
    )
    assert speech == "Kein Gerät gefunden"
    assert "no_valid_targets" in error


def test_inspect_flags_failed_targets() -> None:
    _speech, error = InternalChannel._inspect(
        _response("Teilweise", failed=[{"name": "Lampe"}])
    )
    assert "1 target" in error


def test_inspect_tolerates_missing_payload() -> None:
    assert InternalChannel._inspect(None) == (None, None)
    assert InternalChannel._inspect({}) == (None, None)


@pytest.mark.parametrize(
    ("speech", "expected"),
    [
        ("OK", INTERNAL_RESULT_OK),
        ("ok", INTERNAL_RESULT_OK),
        ("KORRIGIERT", INTERNAL_RESULT_CORRECTED),
        ("FEHLER", INTERNAL_RESULT_FAILED),
        ("Ich habe keine Ahnung", INTERNAL_RESULT_UNVERIFIED),
        ("", INTERNAL_RESULT_UNVERIFIED),
    ],
)
def test_verdict_mapping(speech: str, expected: str) -> None:
    assert InternalChannel._classify_verdict(speech, None) == expected


def test_verdict_error_beats_speech() -> None:
    assert (
        InternalChannel._classify_verdict("OK", "Agent error")
        == INTERNAL_RESULT_FAILED
    )


def test_prompt_includes_context_when_given() -> None:
    plain = InternalChannel._build_prompt("Licht aus", None)
    assert plain == f"{HEROLD_INTERNAL_PREFIX} Licht aus"

    with_context = InternalChannel._build_prompt("Licht aus", "Jonas geht ins Bett")
    assert with_context.startswith(HEROLD_INTERNAL_PREFIX)
    assert "Jonas geht ins Bett" in with_context
    assert "Licht aus" in with_context
