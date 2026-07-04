"""Notification templates: reusable message presets with Jinja placeholders.

Templates live in the config entry (editable via options → templates) as
``{name: {message, priority, title, tag}}``. The message, title and tag
fields render as Jinja templates with the caller's ``template_vars``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.template import Template

from .const import CONF_TEMPLATES

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def resolve_template(
    hass: HomeAssistant,
    config: dict[str, Any],
    name: str,
    variables: dict[str, Any] | None,
) -> dict[str, Any]:
    """Render a named template into notification field defaults."""
    templates: dict[str, Any] = config.get(CONF_TEMPLATES) or {}
    template = templates.get(name)
    if template is None:
        raise HomeAssistantError(
            f"Unknown notification template: {name!r} "
            f"(available: {sorted(templates) or 'none'})"
        )

    variables = variables or {}
    resolved: dict[str, Any] = {}
    for field in ("message", "title", "tag"):
        raw = template.get(field)
        if raw:
            resolved[field] = _render(hass, raw, variables, name, field)
    if template.get("priority") is not None:
        resolved["priority"] = int(template["priority"])
    return resolved


def _render(
    hass: HomeAssistant,
    raw: str,
    variables: dict[str, Any],
    name: str,
    field: str,
) -> str:
    try:
        return Template(raw, hass).async_render(
            variables=variables, parse_result=False
        )
    except Exception as err:  # Template errors are user-config errors
        raise HomeAssistantError(
            f"Template {name!r} field {field!r} failed to render: {err}"
        ) from err
