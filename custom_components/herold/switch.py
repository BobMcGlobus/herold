"""DND switch for the Herold integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_CREATE_INTERNAL_SWITCH,
    DEFAULT_CREATE_INTERNAL_SWITCH,
    DOMAIN,
    signal_dnd,
)
from .entity import HeroldEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import HeroldCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the DND switch if enabled in the config flow."""
    coordinator: HeroldCoordinator = hass.data[DOMAIN][entry.entry_id]
    if not coordinator.config.get(
        CONF_CREATE_INTERNAL_SWITCH, DEFAULT_CREATE_INTERNAL_SWITCH
    ):
        return
    async_add_entities([HeroldDNDSwitch(coordinator)])


class HeroldDNDSwitch(HeroldEntity, RestoreEntity, SwitchEntity):
    """Master DND switch; merged with the external DND entity by the coordinator."""

    _attr_translation_key = "dnd"
    _attr_icon = "mdi:bell-off"

    def __init__(self, coordinator: HeroldCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_dnd"

    @property
    def is_on(self) -> bool:
        """Return the internal master DND state."""
        return self.coordinator.dnd_state.master_active

    async def async_added_to_hass(self) -> None:
        """Restore the last state and subscribe to DND updates."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and not self.coordinator.dnd_restored_from_session:
            # A restored DND session already decided the state; plain restore
            # would re-activate an expired session.
            self.coordinator.set_master_dnd(
                last_state.state == STATE_ON, from_session=True
            )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_dnd(self.coordinator.entry.entry_id),
                self._handle_dnd_update,
            )
        )

    @callback
    def _handle_dnd_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Activate master DND."""
        self.coordinator.set_master_dnd(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deactivate master DND."""
        self.coordinator.set_master_dnd(False)
