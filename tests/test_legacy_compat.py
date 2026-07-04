"""The legacy event semantics are non-negotiable — pin them with tests."""

from custom_components.herold.legacy_compat import (
    LEGACY_DEFAULT_CALLBACK,
    get_legacy_event_names,
)


def test_default_callback_drops_confirm_part() -> None:
    """AI_CONFIRM fires AI_YES/AI_NO — exactly like the original script."""
    assert get_legacy_event_names(LEGACY_DEFAULT_CALLBACK) == ("AI_YES", "AI_NO")


def test_custom_callback_gets_suffixes() -> None:
    """Custom callback XYZ fires XYZ_YES/XYZ_NO."""
    assert get_legacy_event_names("HEIZUNG") == ("HEIZUNG_YES", "HEIZUNG_NO")


def test_default_is_ai_confirm() -> None:
    """The default callback id must stay AI_CONFIRM."""
    assert LEGACY_DEFAULT_CALLBACK == "AI_CONFIRM"
