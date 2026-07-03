"""Shared entity base class for the Herold integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_INTEGRATION_NAME, DEFAULT_INTEGRATION_NAME, DOMAIN

if TYPE_CHECKING:
    from .coordinator import HeroldCoordinator


class HeroldEntity(Entity):
    """Base entity: groups all Herold entities under one service device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.config.get(
                CONF_INTEGRATION_NAME, DEFAULT_INTEGRATION_NAME
            ),
            manufacturer="BobMcGlobus",
            model="Herold Omnichannel Communicator",
            entry_type=DeviceEntryType.SERVICE,
        )
