"""Notification template rendering."""

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.herold.const import CONF_TEMPLATES
from custom_components.herold.templates import resolve_template

CONFIG = {
    CONF_TEMPLATES: {
        "appliance_done": {
            "message": "{{ appliance }} ist fertig",
            "priority": 3,
            "title": None,
            "tag": "appliance_{{ appliance | lower }}",
        }
    }
}


async def test_resolve_renders_placeholders(hass) -> None:
    resolved = resolve_template(
        hass, CONFIG, "appliance_done", {"appliance": "Waschmaschine"}
    )
    assert resolved == {
        "message": "Waschmaschine ist fertig",
        "priority": 3,
        "tag": "appliance_waschmaschine",
    }


async def test_unknown_template_raises(hass) -> None:
    with pytest.raises(HomeAssistantError, match="Unknown notification template"):
        resolve_template(hass, {}, "nope", None)
