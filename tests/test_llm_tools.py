"""German time phrasing used in the spoken tool confirmations."""

from datetime import timedelta

from freezegun import freeze_time
from homeassistant.util import dt as dt_util

from custom_components.herold.llm_tools import describe_when


@freeze_time("2026-07-04 10:00:00+00:00")
def test_today_and_tomorrow(hass) -> None:
    now = dt_util.utcnow()
    assert "heute um" in describe_when(now + timedelta(hours=2), hass)
    assert "morgen um" in describe_when(now + timedelta(days=1), hass)


@freeze_time("2026-07-04 10:00:00+00:00")
def test_weekday_within_the_week(hass) -> None:
    phrase = describe_when(dt_util.utcnow() + timedelta(days=3), hass)
    assert any(
        day in phrase
        for day in ("Montag", "Dienstag", "Mittwoch", "Donnerstag",
                    "Freitag", "Samstag", "Sonntag")
    )


@freeze_time("2026-07-04 10:00:00+00:00")
def test_far_future_uses_date(hass) -> None:
    phrase = describe_when(dt_util.utcnow() + timedelta(days=30), hass)
    assert phrase.startswith("am ")
    assert "." in phrase
