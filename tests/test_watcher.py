"""Watch matching semantics: transitions, thresholds and descriptions."""

from custom_components.herold.models import Watch


def _watch(**kwargs) -> Watch:
    kwargs.setdefault("entity_id", "binary_sensor.front_door")
    kwargs.setdefault("payload", {"message": "Paket mitgeben!"})
    return Watch(**kwargs)


def test_to_state_fires_only_on_transition() -> None:
    watch = _watch(to_state="on")
    assert watch.matches("off", "on") is True
    # Already on and re-reported (e.g. attribute change): not a transition
    assert watch.matches("on", "on") is False
    assert watch.matches("on", "off") is False


def test_to_state_fires_from_unknown_previous() -> None:
    watch = _watch(to_state="on")
    assert watch.matches(None, "on") is True


def test_from_state_restricts_the_source() -> None:
    watch = _watch(to_state="home", from_state="not_home")
    assert watch.matches("not_home", "home") is True
    assert watch.matches("zone.work", "home") is False


def test_any_change_without_target_state() -> None:
    watch = _watch()
    assert watch.matches("off", "on") is True
    assert watch.matches("on", "on") is False


def test_below_threshold_fires_on_crossing_only() -> None:
    watch = _watch(entity_id="sensor.temperature", below=5.0)
    assert watch.matches("6.0", "4.5") is True
    # Already below — no new crossing
    assert watch.matches("4.5", "4.0") is False
    assert watch.matches("4.0", "6.0") is False


def test_above_threshold_fires_on_crossing_only() -> None:
    watch = _watch(entity_id="sensor.temperature", above=25.0)
    assert watch.matches("24.0", "26.0") is True
    assert watch.matches("26.0", "27.0") is False


def test_numeric_watch_ignores_non_numeric_states() -> None:
    watch = _watch(entity_id="sensor.temperature", below=5.0)
    assert watch.matches("6.0", "unavailable") is False


def test_describe_renders_german_conditions() -> None:
    assert "über 25" in _watch(above=25.0).describe()
    assert "unter 5" in _watch(below=5.0).describe()
    assert "«on»" in _watch(to_state="on").describe()
    assert "ändert" in _watch().describe()


def test_describe_prefers_friendly_name() -> None:
    watch = _watch(to_state="on", friendly_name="Front door")
    assert "Front door" in watch.describe()


def test_roundtrip() -> None:
    watch = _watch(to_state="on", friendly_name="Front door", once=True)
    assert Watch.from_dict(watch.to_dict()) == watch
