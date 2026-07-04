"""parse_when: the '+1h30m' / '18:00' / ISO time grammar."""

from datetime import timedelta

from freezegun import freeze_time
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest

from custom_components.herold.scheduler import parse_when


@freeze_time("2026-07-04 12:00:00+00:00")
def test_relative_durations() -> None:
    now = dt_util.utcnow()
    assert parse_when("+30m") == now + timedelta(minutes=30)
    assert parse_when("+1h30m") == now + timedelta(minutes=90)
    assert parse_when("+2d") == now + timedelta(days=2)
    assert parse_when("+45s") == now + timedelta(seconds=45)


@freeze_time("2026-07-04 12:00:00+00:00")
def test_plain_time_today_or_tomorrow() -> None:
    later_today = parse_when("18:00")
    assert later_today > dt_util.utcnow()
    assert later_today.date() == dt_util.now().date()

    tomorrow = parse_when("08:00")
    assert tomorrow.date() == (dt_util.now() + timedelta(days=1)).date()


@freeze_time("2026-07-04 12:00:00+00:00")
def test_iso_datetime() -> None:
    parsed = parse_when("2026-12-24T18:00:00+00:00")
    assert parsed.isoformat() == "2026-12-24T18:00:00+00:00"


@pytest.mark.parametrize("value", ["", "gibberish", "+", "+x", "+0m"])
def test_invalid_values_raise(value: str) -> None:
    with pytest.raises(HomeAssistantError):
        parse_when(value)
