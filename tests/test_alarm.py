"""Alarm scheduling maths, descriptions and the ring volume ramp."""

from freezegun import freeze_time
from homeassistant.util import dt as dt_util
import pytest

from custom_components.herold.alarm import AlarmManager
from custom_components.herold.const import ALARM_RAMP
from custom_components.herold.models import Alarm


@pytest.fixture(autouse=True)
async def _utc_timezone(hass):
    """Alarms are configured in local time; pin it to UTC for the maths."""
    await hass.config.async_set_time_zone("UTC")


async def test_one_shot_picks_today_when_still_ahead(hass) -> None:
    with freeze_time("2026-07-06 06:00:00+00:00"):  # Monday
        alarm = Alarm(time="07:00")
        nxt = dt_util.as_local(alarm.next_occurrence())
        assert (nxt.day, nxt.hour) == (6, 7)


async def test_one_shot_rolls_over_to_tomorrow(hass) -> None:
    with freeze_time("2026-07-06 08:00:00+00:00"):
        alarm = Alarm(time="07:00")
        nxt = dt_util.as_local(alarm.next_occurrence())
        assert (nxt.day, nxt.hour) == (7, 7)


async def test_weekday_alarm_skips_to_next_matching_day(hass) -> None:
    # Saturday 2026-07-04 → next weekday alarm is Monday the 6th
    with freeze_time("2026-07-04 08:00:00+00:00"):
        alarm = Alarm(time="06:30", days=["mon", "tue", "wed", "thu", "fri"])
        nxt = dt_util.as_local(alarm.next_occurrence())
        assert nxt.weekday() == 0
        assert (nxt.day, nxt.hour, nxt.minute) == (6, 6, 30)


async def test_single_day_alarm_finds_next_week(hass) -> None:
    with freeze_time("2026-07-06 08:00:00+00:00"):  # Monday, past 06:30
        alarm = Alarm(time="06:30", days=["mon"])
        nxt = dt_util.as_local(alarm.next_occurrence())
        assert nxt.weekday() == 0
        assert nxt.day == 13  # next Monday


async def test_invalid_time_has_no_occurrence(hass) -> None:
    assert Alarm(time="nonsense").next_occurrence() is None


def test_describe_variants() -> None:
    assert "einmalig" in Alarm(time="07:00").describe()
    assert "täglich" in Alarm(time="07:00", days=list(
        ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    )).describe()
    assert "werktags" in Alarm(
        time="06:30", days=["mon", "tue", "wed", "thu", "fri"]
    ).describe()
    weekend = Alarm(time="09:00", days=["sat", "sun"]).describe()
    assert "Sa" in weekend and "So" in weekend


def test_ramp_grows_and_clamps() -> None:
    factors = [AlarmManager._ramp_factor(ring) for ring in range(1, 8)]
    assert factors[0] == ALARM_RAMP[0]
    assert factors == sorted(factors)          # never gets quieter
    assert factors[-1] == ALARM_RAMP[-1]       # clamped at the last step
    assert AlarmManager._ramp_factor(0) == ALARM_RAMP[0]


def test_roundtrip() -> None:
    alarm = Alarm(time="07:15", days=["mon", "fri"], label="Work")
    assert Alarm.from_dict(alarm.to_dict()) == alarm
