"""Quiet hours: how loud an announcement may be at this time of day.

Independent of DND (which drops notifications entirely) — quiet hours only
lower the volume level. P4 alarms are never quieted; a P3 at three in the
morning speaks quietly rather than at full blast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import (
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    PRIORITY_ALARM,
    VOLUME_LOUD,
    VOLUME_NORMAL,
    VOLUME_QUIET,
)

if TYPE_CHECKING:
    from datetime import time
    from typing import Any


def is_quiet_now(config: dict[str, Any]) -> bool:
    """Return True if the current local time falls inside the quiet window."""
    window = _window(config)
    if window is None:
        return False
    start, end = window
    now = dt_util.now().time()
    if start <= end:
        return start <= now < end
    # Window crosses midnight (the usual case: 22:00 → 07:00)
    return now >= start or now < end


def level_for(priority: int, config: dict[str, Any]) -> str:
    """Return the volume level an announcement should use."""
    if priority >= PRIORITY_ALARM:
        return VOLUME_LOUD
    if is_quiet_now(config):
        return VOLUME_QUIET
    return VOLUME_NORMAL


def _window(config: dict[str, Any]) -> tuple[time, time] | None:
    raw_start = config.get(CONF_QUIET_HOURS_START)
    raw_end = config.get(CONF_QUIET_HOURS_END)
    if not raw_start or not raw_end:
        return None
    start = dt_util.parse_time(str(raw_start))
    end = dt_util.parse_time(str(raw_end))
    if start is None or end is None or start == end:
        return None
    return (start, end)
