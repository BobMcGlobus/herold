"""Editing an existing alarm — what the card's settings sheet sends."""

from types import SimpleNamespace

import pytest

from custom_components.herold.alarm import AlarmManager
from custom_components.herold.const import DEFAULT_ALARM_MESSAGE
from custom_components.herold.models import Alarm


@pytest.fixture
async def manager(hass):
    """An alarm manager on a coordinator stub — no channels, no dispatch."""
    coordinator = SimpleNamespace(
        hass=hass,
        entry=SimpleNamespace(entry_id="test"),
        config={},
        store=SimpleNamespace(alarms={}, async_schedule_save=lambda: None),
    )
    instance = AlarmManager(coordinator)
    yield instance
    # Rescheduling arms real timers; leaving them behind trips the HA test
    # harness' lingering-timer check.
    await instance.async_shutdown()


async def _stored(manager: AlarmManager, **fields) -> Alarm:
    alarm = Alarm(time="07:00", **fields)
    manager.alarms[alarm.id] = alarm
    return alarm


async def test_emptied_routine_is_removed(hass, manager: AlarmManager) -> None:
    """Without this, a routine could only ever be swapped, never dropped."""
    alarm = await _stored(manager, routine="script.good_morning")
    await manager.async_update(alarm.id, {"routine": ""})
    assert alarm.routine is None


async def test_emptied_expiry_makes_the_alarm_permanent(
    hass, manager: AlarmManager
) -> None:
    from homeassistant.util import dt as dt_util

    alarm = await _stored(manager, valid_until=dt_util.utcnow())
    await manager.async_update(alarm.id, {"valid_until": ""})
    assert alarm.valid_until is None
    assert alarm.is_expired is False


async def test_emptied_label_is_removed(hass, manager: AlarmManager) -> None:
    alarm = await _stored(manager, label="Arbeit")
    await manager.async_update(alarm.id, {"label": ""})
    assert alarm.label is None


async def test_emptied_message_falls_back_to_the_default(
    hass, manager: AlarmManager
) -> None:
    """An empty wake message means "say the usual", never "say nothing"."""
    alarm = await _stored(manager, message="Aufstehen, Sportsfreund.")
    await manager.async_update(alarm.id, {"message": ""})
    assert alarm.message == DEFAULT_ALARM_MESSAGE


async def test_editing_clears_a_spent_snooze_budget(
    hass, manager: AlarmManager
) -> None:
    alarm = await _stored(manager, urgency="insistent")
    alarm.snoozes = 1
    alarm.rings = 4
    await manager.async_update(alarm.id, {"time": "06:15"})
    assert (alarm.time, alarm.snoozes, alarm.rings) == ("06:15", 0, 0)


async def test_days_can_be_emptied_into_a_one_shot(
    hass, manager: AlarmManager
) -> None:
    alarm = await _stored(manager, days=["mon", "tue"])
    await manager.async_update(alarm.id, {"days": []})
    assert alarm.days == []
    assert alarm.is_repeating is False


async def test_unknown_fields_are_ignored(hass, manager: AlarmManager) -> None:
    """The card is versioned separately; an unknown key must not explode."""
    alarm = await _stored(manager)
    await manager.async_update(alarm.id, {"nonsense": "x", "label": "Sport"})
    assert alarm.label == "Sport"
    assert not hasattr(alarm, "nonsense")


async def test_emptied_target_goes_back_to_automatic(
    hass, manager: AlarmManager
) -> None:
    """Pinning a speaker must be undoable, not a one-way door."""
    alarm = await _stored(manager, target="media_player.desk")
    await manager.async_update(alarm.id, {"target": ""})
    assert alarm.target is None


async def test_follow_me_can_be_switched_back_off(
    hass, manager: AlarmManager
) -> None:
    """A boolean False is falsy but must still be applied."""
    alarm = await _stored(manager, follow_me=True)
    await manager.async_update(alarm.id, {"follow_me": False})
    assert alarm.follow_me is False
