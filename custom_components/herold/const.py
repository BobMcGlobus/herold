"""Constants for the Herold integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "herold"

# Priority model (see HEROLD_PLAN.md section 3)
PRIORITY_INTERNAL: Final = 0
PRIORITY_TODO: Final = 1
PRIORITY_NORMAL: Final = 2
PRIORITY_IMPORTANT: Final = 3
PRIORITY_ALARM: Final = 4

# Configuration keys
CONF_INTEGRATION_NAME: Final = "integration_name"
CONF_RECIPIENT: Final = "recipient"
CONF_ROOMS: Final = "rooms"
CONF_ROOM_NAME: Final = "name"
CONF_OCCUPANCY_ENTITIES: Final = "occupancy_entities"
CONF_SAT_ENTITY: Final = "sat_entity"
CONF_MEDIA_PLAYER_ENTITY: Final = "media_player_entity"
CONF_LIGHT_ENTITY: Final = "light_entity"
CONF_PRIORITY_WEIGHT: Final = "priority_weight"
CONF_PRIMARY_TTS: Final = "primary_tts_entity"
CONF_FALLBACK_TTS: Final = "fallback_tts_entity"
CONF_INTERNET_SENSOR: Final = "internet_sensor"
CONF_MOBILE_APP_DEVICES: Final = "mobile_app_devices"
CONF_EXTERNAL_DND_ENTITY: Final = "external_dnd_entity"
CONF_CREATE_INTERNAL_SWITCH: Final = "create_internal_switch"
CONF_ENABLE_OFFLINE_FALLBACK: Final = "enable_offline_fallback"
CONF_ENABLE_OFFLINE_QUEUE: Final = "enable_offline_queue"

# Defaults
DEFAULT_INTEGRATION_NAME: Final = "Herold"
DEFAULT_PRIORITY: Final = PRIORITY_NORMAL
DEFAULT_PRIORITY_WEIGHT: Final = 0
DEFAULT_CREATE_INTERNAL_SWITCH: Final = True
DEFAULT_ENABLE_OFFLINE_FALLBACK: Final = False
DEFAULT_ENABLE_OFFLINE_QUEUE: Final = True

# Channel names
CHANNEL_VOICE: Final = "voice"
CHANNEL_PUSH: Final = "push"

# Fired events
EVENT_DELIVERED: Final = "herold_delivered"
EVENT_ANSWERED: Final = "herold_answered"
EVENT_ESCALATED: Final = "herold_escalated"
EVENT_EXPIRED: Final = "herold_expired"

# Legacy compatibility with the original omnichannel script
LEGACY_DEFAULT_CALLBACK: Final = "AI_CONFIRM"

# Services
SERVICE_SEND: Final = "send"

ATTR_MESSAGE: Final = "message"
ATTR_PRIORITY: Final = "priority"
ATTR_RECIPIENT: Final = "recipient"
ATTR_TARGET_PLAYER: Final = "target_player"
ATTR_TITLE: Final = "title"
ATTR_TAG: Final = "tag"
ATTR_TTL_MINUTES: Final = "ttl_minutes"
ATTR_CALLBACK_EVENT: Final = "callback_event"

# Voice channel behavior (ported from the original script)
ALARM_VOICE_PREFIX: Final = "ACHTUNG! KRITISCHE MELDUNG!"
ALARM_ANNOUNCE_DELAY_SECONDS: Final = 3

TEST_NOTIFICATION_MESSAGE: Final = "Herold Test-Nachricht — funktioniert"


def signal_delivery(entry_id: str) -> str:
    """Dispatcher signal fired after a delivery attempt finished."""
    return f"{DOMAIN}_{entry_id}_delivery"


def signal_dnd(entry_id: str) -> str:
    """Dispatcher signal fired when the DND state changed."""
    return f"{DOMAIN}_{entry_id}_dnd"
