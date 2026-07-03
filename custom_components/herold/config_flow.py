"""Config flow for the Herold integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
import voluptuous as vol

from .const import (
    CONF_CREATE_INTERNAL_SWITCH,
    CONF_ENABLE_OFFLINE_FALLBACK,
    CONF_ENABLE_OFFLINE_QUEUE,
    CONF_EXTERNAL_DND_ENTITY,
    CONF_FALLBACK_TTS,
    CONF_INTEGRATION_NAME,
    CONF_INTERNET_SENSOR,
    CONF_LIGHT_ENTITY,
    CONF_MEDIA_PLAYER_ENTITY,
    CONF_MOBILE_APP_DEVICES,
    CONF_OCCUPANCY_ENTITIES,
    CONF_PRIMARY_TTS,
    CONF_PRIORITY_WEIGHT,
    CONF_RECIPIENT,
    CONF_ROOM_NAME,
    CONF_ROOMS,
    CONF_SAT_ENTITY,
    DEFAULT_CREATE_INTERNAL_SWITCH,
    DEFAULT_ENABLE_OFFLINE_FALLBACK,
    DEFAULT_ENABLE_OFFLINE_QUEUE,
    DEFAULT_INTEGRATION_NAME,
    DEFAULT_PRIORITY_WEIGHT,
    DOMAIN,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_RECIPIENT): EntitySelector(
            EntitySelectorConfig(domain="person")
        ),
        vol.Optional(
            CONF_INTEGRATION_NAME, default=DEFAULT_INTEGRATION_NAME
        ): TextSelector(),
    }
)

ROOM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ROOM_NAME): TextSelector(),
        vol.Required(CONF_OCCUPANCY_ENTITIES): EntitySelector(
            EntitySelectorConfig(domain="binary_sensor", multiple=True)
        ),
        vol.Optional(CONF_SAT_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="assist_satellite")
        ),
        vol.Optional(CONF_MEDIA_PLAYER_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="media_player")
        ),
        vol.Optional(CONF_LIGHT_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="light")
        ),
        vol.Optional(
            CONF_PRIORITY_WEIGHT, default=DEFAULT_PRIORITY_WEIGHT
        ): NumberSelector(
            NumberSelectorConfig(min=0, max=100, step=1, mode=NumberSelectorMode.BOX)
        ),
    }
)

VOICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PRIMARY_TTS): EntitySelector(
            EntitySelectorConfig(domain="tts")
        ),
        vol.Optional(CONF_FALLBACK_TTS): EntitySelector(
            EntitySelectorConfig(domain="tts")
        ),
        vol.Required(CONF_INTERNET_SENSOR): EntitySelector(
            EntitySelectorConfig(domain="binary_sensor")
        ),
    }
)

PUSH_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_MOBILE_APP_DEVICES, default=[]): EntitySelector(
            EntitySelectorConfig(domain="notify", multiple=True)
        ),
    }
)

DND_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_EXTERNAL_DND_ENTITY): EntitySelector(
            EntitySelectorConfig(domain=["input_boolean", "binary_sensor"])
        ),
        vol.Required(
            CONF_CREATE_INTERNAL_SWITCH, default=DEFAULT_CREATE_INTERNAL_SWITCH
        ): BooleanSelector(),
    }
)

OFFLINE_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_ENABLE_OFFLINE_FALLBACK, default=DEFAULT_ENABLE_OFFLINE_FALLBACK
        ): BooleanSelector(),
        vol.Required(
            CONF_ENABLE_OFFLINE_QUEUE, default=DEFAULT_ENABLE_OFFLINE_QUEUE
        ): BooleanSelector(),
    }
)

BASIC_KEYS = (CONF_RECIPIENT, CONF_INTEGRATION_NAME)
VOICE_KEYS = (CONF_PRIMARY_TTS, CONF_FALLBACK_TTS, CONF_INTERNET_SENSOR)
PUSH_KEYS = (CONF_MOBILE_APP_DEVICES,)
DND_KEYS = (CONF_EXTERNAL_DND_ENTITY, CONF_CREATE_INTERNAL_SWITCH)
OFFLINE_KEYS = (CONF_ENABLE_OFFLINE_FALLBACK, CONF_ENABLE_OFFLINE_QUEUE)


def _validate_room(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate a room form; at least one voice output is mandatory."""
    errors: dict[str, str] = {}
    if not user_input.get(CONF_OCCUPANCY_ENTITIES):
        errors[CONF_OCCUPANCY_ENTITIES] = "room_no_occupancy"
    if not user_input.get(CONF_SAT_ENTITY) and not user_input.get(
        CONF_MEDIA_PLAYER_ENTITY
    ):
        errors["base"] = "room_no_output"
    return errors


def _normalize_room(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize a room form result for config entry storage."""
    return {
        CONF_ROOM_NAME: user_input[CONF_ROOM_NAME].strip(),
        CONF_OCCUPANCY_ENTITIES: list(user_input[CONF_OCCUPANCY_ENTITIES]),
        CONF_SAT_ENTITY: user_input.get(CONF_SAT_ENTITY),
        CONF_MEDIA_PLAYER_ENTITY: user_input.get(CONF_MEDIA_PLAYER_ENTITY),
        CONF_LIGHT_ENTITY: user_input.get(CONF_LIGHT_ENTITY),
        CONF_PRIORITY_WEIGHT: int(
            user_input.get(CONF_PRIORITY_WEIGHT, DEFAULT_PRIORITY_WEIGHT)
        ),
    }


class HeroldConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: basics → rooms (repeatable) → voice → push → dnd → offline."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._rooms: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the basics step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_rooms()
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

    async def async_step_rooms(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a room (repeatable via the room menu)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_room(user_input)
            if not errors:
                self._rooms.append(_normalize_room(user_input))
                return await self.async_step_room_menu()
        return self.async_show_form(
            step_id="rooms",
            data_schema=self.add_suggested_values_to_schema(
                ROOM_SCHEMA, user_input
            ),
            errors=errors or None,
        )

    async def async_step_room_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask whether to add another room or continue."""
        return self.async_show_menu(
            step_id="room_menu", menu_options=["rooms", "voice"]
        )

    async def async_step_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the voice step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_push()
        return self.async_show_form(step_id="voice", data_schema=VOICE_SCHEMA)

    async def async_step_push(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the push step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_dnd()
        return self.async_show_form(step_id="push", data_schema=PUSH_SCHEMA)

    async def async_step_dnd(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the DND step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_offline()
        return self.async_show_form(step_id="dnd", data_schema=DND_SCHEMA)

    async def async_step_offline(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the offline step and create the entry."""
        if user_input is not None:
            self._data.update(user_input)
            self._data[CONF_ROOMS] = self._rooms
            return self.async_create_entry(
                title=self._data.get(
                    CONF_INTEGRATION_NAME, DEFAULT_INTEGRATION_NAME
                ),
                data=self._data,
            )
        return self.async_show_form(step_id="offline", data_schema=OFFLINE_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> HeroldOptionsFlow:
        """Return the options flow handler."""
        return HeroldOptionsFlow()


class HeroldOptionsFlow(OptionsFlow):
    """Section-wise editing; rooms can be added/edited/removed without rebuild."""

    def __init__(self) -> None:
        self._config: dict[str, Any] | None = None
        self._edit_index: int = 0

    @property
    def _current(self) -> dict[str, Any]:
        """Merged, mutable copy of the current configuration."""
        if self._config is None:
            self._config = {
                **self.config_entry.data,
                **self.config_entry.options,
            }
            self._config[CONF_ROOMS] = [
                dict(room) for room in self._config.get(CONF_ROOMS, [])
            ]
        return self._config

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the section menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["basic", "rooms_menu", "voice", "push", "dnd", "offline"],
        )

    def _async_step_section(
        self,
        step_id: str,
        schema: vol.Schema,
        keys: tuple[str, ...],
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Generic section edit: prefill, merge and save."""
        if user_input is not None:
            for key in keys:
                if key in user_input:
                    self._current[key] = user_input[key]
                else:
                    self._current.pop(key, None)
            return self.async_create_entry(title="", data=self._current)
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, self._current),
        )

    async def async_step_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the basic section."""
        return self._async_step_section("basic", USER_SCHEMA, BASIC_KEYS, user_input)

    async def async_step_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the voice section."""
        return self._async_step_section("voice", VOICE_SCHEMA, VOICE_KEYS, user_input)

    async def async_step_push(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the push section."""
        return self._async_step_section("push", PUSH_SCHEMA, PUSH_KEYS, user_input)

    async def async_step_dnd(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the DND section."""
        return self._async_step_section("dnd", DND_SCHEMA, DND_KEYS, user_input)

    async def async_step_offline(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the offline section."""
        return self._async_step_section(
            "offline", OFFLINE_SCHEMA, OFFLINE_KEYS, user_input
        )

    async def async_step_rooms_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the rooms submenu."""
        return self.async_show_menu(
            step_id="rooms_menu",
            menu_options=["room_add", "room_edit", "room_remove", "save"],
        )

    async def async_step_room_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a room."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_room(user_input)
            if not errors:
                self._current[CONF_ROOMS].append(_normalize_room(user_input))
                return await self.async_step_rooms_menu()
        return self.async_show_form(
            step_id="room_add",
            data_schema=self.add_suggested_values_to_schema(ROOM_SCHEMA, user_input),
            errors=errors or None,
        )

    async def async_step_room_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a room to edit."""
        rooms: list[dict[str, Any]] = self._current[CONF_ROOMS]
        if not rooms:
            return await self.async_step_rooms_menu()
        if user_input is not None:
            self._edit_index = int(user_input["room_index"])
            return await self.async_step_room_edit_form()
        options = [
            SelectOptionDict(value=str(index), label=room[CONF_ROOM_NAME])
            for index, room in enumerate(rooms)
        ]
        schema = vol.Schema(
            {
                vol.Required("room_index"): SelectSelector(
                    SelectSelectorConfig(
                        options=options, mode=SelectSelectorMode.DROPDOWN
                    )
                )
            }
        )
        return self.async_show_form(step_id="room_edit", data_schema=schema)

    async def async_step_room_edit_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected room."""
        errors: dict[str, str] = {}
        room = self._current[CONF_ROOMS][self._edit_index]
        if user_input is not None:
            errors = _validate_room(user_input)
            if not errors:
                self._current[CONF_ROOMS][self._edit_index] = _normalize_room(
                    user_input
                )
                return await self.async_step_rooms_menu()
        return self.async_show_form(
            step_id="room_edit_form",
            data_schema=self.add_suggested_values_to_schema(
                ROOM_SCHEMA, user_input or room
            ),
            errors=errors or None,
        )

    async def async_step_room_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove rooms (at least one room must remain)."""
        errors: dict[str, str] = {}
        rooms: list[dict[str, Any]] = self._current[CONF_ROOMS]
        if user_input is not None:
            indexes = {int(index) for index in user_input.get("room_indexes", [])}
            remaining = [
                room for index, room in enumerate(rooms) if index not in indexes
            ]
            if not remaining:
                errors["base"] = "no_rooms_left"
            else:
                self._current[CONF_ROOMS] = remaining
                return await self.async_step_rooms_menu()
        options = [
            SelectOptionDict(value=str(index), label=room[CONF_ROOM_NAME])
            for index, room in enumerate(rooms)
        ]
        schema = vol.Schema(
            {
                vol.Required("room_indexes", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.LIST,
                        multiple=True,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="room_remove", data_schema=schema, errors=errors or None
        )

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Persist room changes and finish the options flow."""
        return self.async_create_entry(title="", data=self._current)
