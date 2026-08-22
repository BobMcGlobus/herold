"""Urgency profiles, snooze budgets, blocking and volume bounds."""

from types import SimpleNamespace

import pytest

from custom_components.herold.alarm_output import AlarmOutput
from custom_components.herold.const import (
    ALARM_STATUS_ARMED,
    CONF_ALARM_SICK_ENTITY,
    CONF_ALARM_VOLUME_MAX,
    CONF_ALARM_VOLUME_MIN,
    CONF_ALARM_WORKDAY_SENSOR,
    URGENCY_GENTLE,
    URGENCY_INSISTENT,
    URGENCY_NORMAL,
)
from custom_components.herold.models import Alarm


def _output(config: dict) -> AlarmOutput:
    return AlarmOutput(SimpleNamespace(config=config))


# -- Snooze budget ---------------------------------------------------------


def test_normal_alarm_grants_three_full_snoozes() -> None:
    alarm = Alarm(time="07:00", urgency=URGENCY_NORMAL)
    for _ in range(3):
        assert alarm.snooze_minutes(9) == 9
        alarm.snoozes += 1
    # Budget spent — the alarm refuses to be quiet again
    assert alarm.snooze_minutes(9) is None


def test_insistent_alarm_grants_one_snooze_only() -> None:
    alarm = Alarm(time="07:00", urgency=URGENCY_INSISTENT)
    assert alarm.snooze_minutes(9) == 9
    alarm.snoozes += 1
    assert alarm.snooze_minutes(9) is None


def test_gentle_alarm_does_not_limit_snoozes() -> None:
    alarm = Alarm(time="07:00", urgency=URGENCY_GENTLE)
    alarm.snoozes = 20
    assert alarm.snooze_minutes(9) == 9


def test_shrinking_snooze_gets_shorter_each_time() -> None:
    """Insistent alarms shorten the snooze; the budget caps it at one."""
    from custom_components.herold.const import SNOOZE_SHRINK_FACTORS

    lengths = [round(9 * factor) for factor in SNOOZE_SHRINK_FACTORS]
    assert lengths == sorted(lengths, reverse=True)
    assert lengths[0] == 9


# -- Volume bounds ---------------------------------------------------------


def test_volume_starts_at_the_floor_and_climbs_to_the_ceiling() -> None:
    output = _output(
        {CONF_ALARM_VOLUME_MIN: 0.4, CONF_ALARM_VOLUME_MAX: 1.0}
    )
    alarm = Alarm(time="07:00", urgency=URGENCY_NORMAL)
    volumes = [output.volume_for_ring(alarm, ring) for ring in range(1, 8)]
    assert volumes[0] >= 0.4          # never below the floor
    assert volumes == sorted(volumes)  # never gets quieter
    assert volumes[-1] == 1.0          # reaches the ceiling
    assert max(volumes) <= 1.0


def test_volume_floor_applies_even_on_the_first_ring() -> None:
    """A speaker left at 5 % overnight must not swallow the alarm."""
    output = _output({CONF_ALARM_VOLUME_MIN: 0.5, CONF_ALARM_VOLUME_MAX: 0.9})
    alarm = Alarm(time="07:00", urgency=URGENCY_GENTLE)
    assert output.volume_for_ring(alarm, 1) >= 0.5


def test_swapped_bounds_are_tolerated() -> None:
    output = _output({CONF_ALARM_VOLUME_MIN: 0.9, CONF_ALARM_VOLUME_MAX: 0.3})
    alarm = Alarm(time="07:00")
    volume = output.volume_for_ring(alarm, 1)
    assert 0.3 <= volume <= 0.9


def test_gentle_starts_quieter_than_insistent() -> None:
    output = _output({CONF_ALARM_VOLUME_MIN: 0.2, CONF_ALARM_VOLUME_MAX: 1.0})
    gentle = Alarm(time="07:00", urgency=URGENCY_GENTLE)
    insistent = Alarm(time="07:00", urgency=URGENCY_INSISTENT)
    assert output.volume_for_ring(gentle, 1) < output.volume_for_ring(
        insistent, 1
    )


# -- Urgency profiles ------------------------------------------------------


def test_insistent_rings_more_often_and_faster() -> None:
    gentle = Alarm(time="07:00", urgency=URGENCY_GENTLE).profile
    insistent = Alarm(time="07:00", urgency=URGENCY_INSISTENT).profile
    assert insistent["interval"] < gentle["interval"]
    assert insistent["max_rings"] > gentle["max_rings"]


def test_unknown_urgency_falls_back_to_normal() -> None:
    alarm = Alarm(time="07:00", urgency="whatever")
    assert alarm.profile == Alarm(time="07:00", urgency=URGENCY_NORMAL).profile


# -- Workday and sick day blocking ----------------------------------------


@pytest.fixture
def manager_factory(hass):
    from custom_components.herold.alarm import AlarmManager

    def build(config: dict):
        coordinator = SimpleNamespace(hass=hass, config=config)
        manager = AlarmManager.__new__(AlarmManager)
        manager.coordinator = coordinator
        return manager

    return build


async def test_work_alarm_skipped_on_a_holiday(hass, manager_factory) -> None:
    hass.states.async_set("binary_sensor.workday", "off")
    manager = manager_factory({CONF_ALARM_WORKDAY_SENSOR: "binary_sensor.workday"})
    assert manager.is_blocked(Alarm(time="06:30", workday_only=True)) == (
        "not a workday"
    )


async def test_work_alarm_skipped_when_sick(hass, manager_factory) -> None:
    hass.states.async_set("binary_sensor.workday", "on")
    hass.states.async_set("input_boolean.krank", "on")
    manager = manager_factory(
        {
            CONF_ALARM_WORKDAY_SENSOR: "binary_sensor.workday",
            CONF_ALARM_SICK_ENTITY: "input_boolean.krank",
        }
    )
    assert manager.is_blocked(Alarm(time="06:30", workday_only=True)) == "sick day"


async def test_non_work_alarm_rings_on_a_holiday(hass, manager_factory) -> None:
    """A holiday alarm is set *because* it is a holiday — never block it."""
    hass.states.async_set("binary_sensor.workday", "off")
    hass.states.async_set("input_boolean.krank", "on")
    manager = manager_factory(
        {
            CONF_ALARM_WORKDAY_SENSOR: "binary_sensor.workday",
            CONF_ALARM_SICK_ENTITY: "input_boolean.krank",
        }
    )
    assert manager.is_blocked(Alarm(time="09:00", workday_only=False)) is None


async def test_work_alarm_rings_on_a_workday(hass, manager_factory) -> None:
    hass.states.async_set("binary_sensor.workday", "on")
    manager = manager_factory({CONF_ALARM_WORKDAY_SENSOR: "binary_sensor.workday"})
    assert manager.is_blocked(Alarm(time="06:30", workday_only=True)) is None


async def test_no_sensors_configured_never_blocks(hass, manager_factory) -> None:
    manager = manager_factory({})
    assert manager.is_blocked(Alarm(time="06:30", workday_only=True)) is None


# -- Temporary alarms ------------------------------------------------------


def test_expiry() -> None:
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    past = Alarm(time="07:00", valid_until=dt_util.utcnow() - timedelta(hours=1))
    future = Alarm(time="07:00", valid_until=dt_util.utcnow() + timedelta(days=1))
    assert past.is_expired is True
    assert future.is_expired is False
    assert Alarm(time="07:00").is_expired is False


def test_roundtrip_keeps_the_new_fields() -> None:
    alarm = Alarm(
        time="06:30",
        days=["mon", "fri"],
        label="Work",
        key="shift_plan",
        urgency=URGENCY_INSISTENT,
        sound_mode="media",
        sound="media-source://media_source/local/wake.mp3",
        announce=False,
        voice_snooze=True,
        routine="script.good_morning",
        workday_only=True,
        status=ALARM_STATUS_ARMED,
    )
    assert Alarm.from_dict(alarm.to_dict()) == alarm
