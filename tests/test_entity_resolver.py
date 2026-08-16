"""Loose entity references from an LLM are resolved to real entity ids."""

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest

from custom_components.herold.entity_resolver import (
    normalize_trigger,
    resolve_entity,
)


@pytest.fixture(autouse=True)
def _expose_everything(monkeypatch):
    """Treat all entities as exposed; exposure itself is HA's concern."""
    monkeypatch.setattr(
        "custom_components.herold.entity_resolver.async_should_expose",
        lambda hass, assistant, entity_id: True,
    )


def _add(hass, entity_id: str, name: str, state: str = "off") -> None:
    hass.states.async_set(entity_id, state, {"friendly_name": name})


async def test_exact_entity_id_wins(hass) -> None:
    _add(hass, "climate.klimaanlage_buero", "Klimaanlage Büro")
    assert resolve_entity(hass, "climate.klimaanlage_buero") == (
        "climate.klimaanlage_buero",
        "Klimaanlage Büro",
    )


async def test_friendly_name_is_matched(hass) -> None:
    _add(hass, "climate.klimaanlage_buero", "Klimaanlage Büro")
    entity_id, _name = resolve_entity(hass, "Klimaanlage Büro")
    assert entity_id == "climate.klimaanlage_buero"


async def test_umlauts_and_casing_are_ignored(hass) -> None:
    _add(hass, "cover.rolladen_buero", "Rolladen Büro")
    entity_id, _name = resolve_entity(hass, "rolladen buero")
    assert entity_id == "cover.rolladen_buero"


async def test_guessed_id_resolves_via_domain_and_tokens(hass) -> None:
    """The failure from the field: a hallucinated id in the right domain."""
    _add(hass, "climate.klimaanlage_arbeitszimmer", "Klimaanlage Arbeitszimmer")
    _add(hass, "light.arbeitszimmer_decke", "Arbeitszimmer Decke")
    entity_id, _name = resolve_entity(hass, "climate.ac_arbeitszimmer")
    assert entity_id == "climate.klimaanlage_arbeitszimmer"


async def test_alias_is_matched(hass) -> None:
    _add(hass, "climate.hvac_1", "HVAC 1")
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "climate", "demo", "unique1", suggested_object_id="hvac_1"
    )
    registry.async_update_entity(entry.entity_id, aliases={"Klimaanlage"})
    _add(hass, entry.entity_id, "HVAC 1")
    entity_id, _name = resolve_entity(hass, "Klimaanlage")
    assert entity_id == entry.entity_id


async def test_unknown_reference_lists_candidates(hass) -> None:
    _add(hass, "light.kueche", "Küche")
    _add(hass, "light.flur", "Flur")
    with pytest.raises(HomeAssistantError) as err:
        resolve_entity(hass, "Dampfmaschine im Keller")
    # The suggestions are what let the model correct itself
    assert "light.kueche" in str(err.value) or "light.flur" in str(err.value)


async def test_unexposed_entity_says_so(hass, monkeypatch) -> None:
    _add(hass, "lock.tresor", "Tresor")
    monkeypatch.setattr(
        "custom_components.herold.entity_resolver.async_should_expose",
        lambda hass, assistant, entity_id: False,
    )
    with pytest.raises(HomeAssistantError, match="not exposed"):
        resolve_entity(hass, "lock.tresor")


async def test_empty_reference(hass) -> None:
    with pytest.raises(HomeAssistantError, match="No entity given"):
        resolve_entity(hass, "  ")


def test_turn_on_is_rewritten_for_non_on_off_domains() -> None:
    # A climate entity reports cool/heat, never "on"
    assert normalize_trigger("climate.ac", "on", None) == (None, "off")
    assert normalize_trigger("media_player.tv", "an", None) == (None, "off")
    # Lights really do have an "on" state
    assert normalize_trigger("light.desk", "on", None) == ("on", None)
    assert normalize_trigger("binary_sensor.door", "on", None) == ("on", None)


def test_german_state_words_are_mapped() -> None:
    assert normalize_trigger("cover.blind", "offen", None) == ("open", None)
    assert normalize_trigger("light.desk", "aus", None) == ("off", None)
    assert normalize_trigger("person.someone", "zuhause", None) == ("home", None)


def test_off_works_across_domains() -> None:
    assert normalize_trigger("climate.ac", "off", None) == ("off", None)


def test_blank_states_become_none() -> None:
    assert normalize_trigger("light.desk", "", "") == (None, None)
