"""Turn a loose entity reference from an LLM into a real entity id.

An LLM rarely knows the exact entity ids of a household — it guesses things
like ``climate.ac_arbeitszimmer`` when the entity is actually called
``climate.klimaanlage_buero``. Rejecting that with "unknown entity" makes the
model guess again instead of correcting itself, so this resolver

* accepts an exact entity id, a friendly name or a voice alias,
* scores fuzzy matches against exposed entities (a domain prefix in the
  query narrows the field), and
* raises an error that *lists concrete candidates*, which is what lets the
  model fix its own call on the next turn.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import TYPE_CHECKING

from homeassistant.components.homeassistant.exposed_entities import (
    async_should_expose,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

CONVERSATION_ASSISTANT = "conversation"

# Accept a match from this score up, and only if it beats the runner-up by
# this margin — otherwise ask the model to choose explicitly.
MATCH_THRESHOLD = 0.45
MATCH_MARGIN = 0.08
MAX_SUGGESTIONS = 6

_UMLAUTS = (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"))


def _as_text(value: object) -> str | None:
    """Return a usable string, or None for anything else.

    State attributes are not guaranteed to hold strings: Home Assistant uses
    sentinel objects for computed entity names, and integrations may put
    arbitrary objects in there. Anything that is not plain text carries no
    label we could match against.
    """
    if isinstance(value, str) and value.strip():
        return value
    return None


def _normalize(text: object) -> str:
    """Lowercase, de-umlaut and reduce to space-separated words."""
    plain = _as_text(text)
    if plain is None:
        return ""
    lowered = plain.lower()
    for source, target in _UMLAUTS:
        lowered = lowered.replace(source, target)
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _score(query: str, tokens: set[str], candidate: str) -> float:
    """Similarity of a candidate label to the query (0..1)."""
    normalized = _normalize(candidate)
    if not normalized:
        return 0.0
    ratio = SequenceMatcher(None, query, normalized).ratio()
    candidate_tokens = set(normalized.split())
    if not tokens:
        return ratio
    overlap = len(tokens & candidate_tokens) / len(tokens)
    # A full token hit is strong evidence, but never quite as strong as an
    # outright string match.
    return max(ratio, overlap * 0.95)


def resolve_entity(hass: HomeAssistant, reference: str) -> tuple[str, str]:
    """Return (entity_id, friendly_name) for a loose reference.

    Raises HomeAssistantError with concrete suggestions when the reference is
    ambiguous or matches nothing.
    """
    reference = reference.strip()
    if not reference:
        raise HomeAssistantError(
            "No entity given — pass the entity id or the name the user said"
        )
    registry = er.async_get(hass)

    exposed: list[tuple[str, str, list[str]]] = []
    for state in hass.states.async_all():
        if not async_should_expose(
            hass, CONVERSATION_ASSISTANT, state.entity_id
        ):
            continue
        entry = registry.async_get(state.entity_id)
        name = _as_text(state.attributes.get("friendly_name")) or state.entity_id
        aliases = [
            alias
            for alias in (entry.aliases if entry and entry.aliases else ())
            if _as_text(alias)
        ]
        exposed.append((state.entity_id, name, aliases))

    lowered = reference.lower()
    for entity_id, name, _aliases in exposed:
        if entity_id.lower() == lowered:
            return (entity_id, name)

    # The id exists but the user has not exposed it — a different problem
    # than a wrong guess, so say so plainly.
    if hass.states.get(reference) is not None:
        raise HomeAssistantError(
            f"Entity {reference} exists but is not exposed to the voice "
            "assistant, so it cannot be watched"
        )

    domain = reference.split(".", 1)[0] if "." in reference else None
    pool = exposed
    if domain:
        in_domain = [item for item in exposed if item[0].startswith(f"{domain}.")]
        if in_domain:
            pool = in_domain

    query = _normalize(
        reference.split(".", 1)[1] if "." in reference else reference
    )
    tokens = set(query.split())

    scored = sorted(
        (
            (
                max(
                    _score(query, tokens, name),
                    _score(query, tokens, entity_id),
                    *(_score(query, tokens, alias) for alias in aliases),
                ),
                entity_id,
                name,
            )
            for entity_id, name, aliases in pool
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    if not scored:
        raise HomeAssistantError(
            "No entities are exposed to the voice assistant, so nothing can "
            "be watched"
        )

    best = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if best[0] >= MATCH_THRESHOLD and best[0] - runner_up >= MATCH_MARGIN:
        return (best[1], best[2])

    suggestions = ", ".join(
        f"{entity_id} ({name})" for _score_, entity_id, name in
        scored[:MAX_SUGGESTIONS] if _score_ > 0
    )
    if best[0] >= MATCH_THRESHOLD:
        raise HomeAssistantError(
            f"{reference!r} is ambiguous. Call again with one of these exact "
            f"entity ids: {suggestions}"
        )
    raise HomeAssistantError(
        f"No entity matches {reference!r}. Call again with one of these exact "
        f"entity ids, or ask the user which device is meant: {suggestions}"
    )


# Domains where "on"/"off" really are the states. Everywhere else (climate,
# media_player, cover, lock, …) "turned on" means "left the off state".
ON_OFF_DOMAINS = frozenset(
    {
        "automation",
        "binary_sensor",
        "fan",
        "group",
        "humidifier",
        "input_boolean",
        "light",
        "remote",
        "schedule",
        "script",
        "siren",
        "switch",
    }
)

# The model often answers in the user's language; map the common words.
_STATE_ALIASES = {
    "an": "on",
    "ein": "on",
    "eingeschaltet": "on",
    "aus": "off",
    "ausgeschaltet": "off",
    "auf": "open",
    "offen": "open",
    "geoeffnet": "open",
    "zu": "closed",
    "geschlossen": "closed",
    "zuhause": "home",
    "daheim": "home",
    "abwesend": "not_home",
    "unterwegs": "not_home",
}


def normalize_trigger(
    entity_id: str, to_state: str | None, from_state: str | None
) -> tuple[str | None, str | None]:
    """Return (to_state, from_state) adjusted to what the domain can produce.

    "Remind me when the AC turns on" arrives as ``to_state="on"``, but a
    climate entity never reports "on" — it reports "cool", "heat" and so on.
    For those domains the request is rewritten to "left the off state",
    which is what the user meant.
    """
    to_state = _canonical_state(to_state)
    from_state = _canonical_state(from_state)
    domain = entity_id.split(".", 1)[0]

    if to_state == "on" and domain not in ON_OFF_DOMAINS:
        return (None, from_state or "off")
    return (to_state, from_state)


def _canonical_state(state: str | None) -> str | None:
    if state is None:
        return None
    cleaned = state.strip()
    if not cleaned:
        return None
    return _STATE_ALIASES.get(_normalize(cleaned), cleaned)
