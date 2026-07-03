"""Backward compatibility with the original omnichannel communicator script.

The original ``script.system_universal_omnichannel_communicator_priority_edition``
fires Telegram inline-button events that existing automations (scripts.yaml,
packages/ai_assist.yaml) consume. Herold must reproduce these event names
bit-exact.
"""

from __future__ import annotations

from .const import LEGACY_DEFAULT_CALLBACK

__all__ = ["LEGACY_DEFAULT_CALLBACK", "get_legacy_event_names"]


def get_legacy_event_names(callback_event: str) -> tuple[str, str]:
    """Return the (yes, no) event names for a callback event id.

    Original script semantics — must not change:

    * ``callback_event="AI_CONFIRM"`` (the legacy default) fires ``AI_YES`` and
      ``AI_NO`` — WITHOUT the ``CONFIRM`` part. This is the historical quirk of
      the original script and existing automations depend on exactly these
      names.
    * Any custom ``callback_event="XYZ"`` fires ``XYZ_YES`` and ``XYZ_NO``.

    Answer handling itself (query mode) lands in Phase 2; this utility only
    prepares the mapping so the semantics are pinned down early.
    """
    if callback_event == LEGACY_DEFAULT_CALLBACK:
        return ("AI_YES", "AI_NO")
    return (f"{callback_event}_YES", f"{callback_event}_NO")
