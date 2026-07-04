"""Answer normalization for yesno queries."""

import pytest

from custom_components.herold.const import ANSWER_NO, ANSWER_YES
from custom_components.herold.query_manager import normalize_yesno


@pytest.mark.parametrize("raw", ["Ja", "ja", "JA", "yes", "klar", "ok", "1"])
def test_positive_answers(raw: str) -> None:
    assert normalize_yesno(raw) == ANSWER_YES


@pytest.mark.parametrize("raw", ["Nein", "nein", "no", "0", "false"])
def test_negative_answers(raw: str) -> None:
    assert normalize_yesno(raw) == ANSWER_NO


@pytest.mark.parametrize("raw", ["vielleicht", "später", ""])
def test_unrecognized_answers(raw: str) -> None:
    assert normalize_yesno(raw) is None
