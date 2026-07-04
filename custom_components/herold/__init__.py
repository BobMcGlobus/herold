"""The Herold integration — omnichannel notification hub."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_FLASH_ENTITIES, CONF_ROOMS, DOMAIN, LEGACY_CONF_LIGHT_ENTITY
from .coordinator import HeroldCoordinator
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Herold from a config entry."""
    coordinator = HeroldCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: HeroldCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            async_unregister_services(hass)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if entry.version > 2:
        # Downgrade from a future version — cannot migrate safely.
        return False

    if entry.version < 2:
        # v1 → v2: room light_entity (single) becomes flash_entities (multi,
        # lights and scenes).
        data = _migrate_rooms_v2(entry.data)
        options = _migrate_rooms_v2(entry.options)
        hass.config_entries.async_update_entry(
            entry, data=data, options=options, version=2
        )
        _LOGGER.debug("Migrated config entry %s to version 2", entry.entry_id)

    return True


def _migrate_rooms_v2(config: dict[str, Any]) -> dict[str, Any]:
    """Convert light_entity to flash_entities in a config mapping."""
    rooms = config.get(CONF_ROOMS)
    if not rooms:
        return dict(config)
    migrated_rooms = []
    for raw in rooms:
        room = dict(raw)
        light = room.pop(LEGACY_CONF_LIGHT_ENTITY, None)
        room.setdefault(CONF_FLASH_ENTITIES, [light] if light else [])
        migrated_rooms.append(room)
    return {**config, CONF_ROOMS: migrated_rooms}


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
