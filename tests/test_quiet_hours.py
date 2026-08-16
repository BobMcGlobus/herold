"""Quiet hours window handling and the resulting volume level.

The window is evaluated in the user's local time, so these tests pin the
Home Assistant timezone to UTC and freeze UTC timestamps.
"""

from freezegun import freeze_time
import pytest

from custom_components.herold.const import (
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    VOLUME_LOUD,
    VOLUME_NORMAL,
    VOLUME_QUIET,
)
from custom_components.herold.models import Room
from custom_components.herold.quiet_hours import is_quiet_now, level_for

NIGHT = {CONF_QUIET_HOURS_START: "22:00:00", CONF_QUIET_HOURS_END: "07:00:00"}
DAYTIME = {CONF_QUIET_HOURS_START: "09:00:00", CONF_QUIET_HOURS_END: "17:00:00"}


@pytest.fixture(autouse=True)
async def _utc_timezone(hass):
    """Evaluate local time as UTC so frozen timestamps line up."""
    await hass.config.async_set_time_zone("UTC")


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-07-04 23:30:00+00:00", True),   # after start, before midnight
        ("2026-07-04 03:00:00+00:00", True),   # after midnight, before end
        ("2026-07-04 12:00:00+00:00", False),  # broad daylight
        ("2026-07-04 22:00:00+00:00", True),   # inclusive start
        ("2026-07-04 07:00:00+00:00", False),  # exclusive end
    ],
)
async def test_window_crossing_midnight(hass, now: str, expected: bool) -> None:
    with freeze_time(now):
        assert is_quiet_now(NIGHT) is expected


async def test_window_within_one_day(hass) -> None:
    with freeze_time("2026-07-04 12:00:00+00:00"):
        assert is_quiet_now(DAYTIME) is True
    with freeze_time("2026-07-04 20:00:00+00:00"):
        assert is_quiet_now(DAYTIME) is False


async def test_no_window_configured(hass) -> None:
    assert is_quiet_now({}) is False
    assert is_quiet_now({CONF_QUIET_HOURS_START: "22:00:00"}) is False


async def test_identical_bounds_are_ignored(hass) -> None:
    assert (
        is_quiet_now(
            {
                CONF_QUIET_HOURS_START: "22:00:00",
                CONF_QUIET_HOURS_END: "22:00:00",
            }
        )
        is False
    )


async def test_level_follows_quiet_hours(hass) -> None:
    with freeze_time("2026-07-04 23:30:00+00:00"):
        assert level_for(2, NIGHT) == VOLUME_QUIET
        assert level_for(3, NIGHT) == VOLUME_QUIET
        # An alarm is never quieted
        assert level_for(4, NIGHT) == VOLUME_LOUD
    with freeze_time("2026-07-04 12:00:00+00:00"):
        assert level_for(2, NIGHT) == VOLUME_NORMAL
        assert level_for(4, NIGHT) == VOLUME_LOUD


def test_room_volume_lookup() -> None:
    room = Room(name="Test", volume_quiet=0.2, volume_loud=0.9)
    assert room.volume_for(VOLUME_QUIET) == 0.2
    assert room.volume_for(VOLUME_LOUD) == 0.9
    # Unset levels leave the volume untouched
    assert room.volume_for(VOLUME_NORMAL) is None
