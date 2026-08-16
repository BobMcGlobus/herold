"""Volume override: capture, restore and overlapping announcements."""

from homeassistant.components.media_player import MediaPlayerEntityFeature

from custom_components.herold.volume import VolumeController

PLAYER = "media_player.sonos_roam"
FEATURES = int(MediaPlayerEntityFeature.VOLUME_SET)


def _set_player(hass, volume: float, state: str = "idle") -> None:
    hass.states.async_set(
        PLAYER,
        state,
        {"volume_level": volume, "supported_features": FEATURES},
    )


async def test_sets_and_restores_volume(hass) -> None:
    _set_player(hass, 0.3)
    calls = []
    hass.services.async_register(
        "media_player", "volume_set", lambda call: calls.append(call.data)
    )

    controller = VolumeController(hass)
    async with controller.announce_at(PLAYER, 0.8):
        await hass.async_block_till_done()
        assert calls[0]["volume_level"] == 0.8
    await hass.async_block_till_done()

    assert [call["volume_level"] for call in calls] == [0.8, 0.3]


async def test_overlapping_announcements_restore_once(hass) -> None:
    _set_player(hass, 0.3)
    calls = []
    hass.services.async_register(
        "media_player", "volume_set", lambda call: calls.append(call.data)
    )
    controller = VolumeController(hass)

    async with controller.announce_at(PLAYER, 0.8):
        async with controller.announce_at(PLAYER, 0.9):
            await hass.async_block_till_done()
        # Inner block finished — the original volume must NOT be back yet
        await hass.async_block_till_done()
        assert calls[-1]["volume_level"] == 0.9
    await hass.async_block_till_done()

    assert calls[-1]["volume_level"] == 0.3


async def test_no_volume_configured_is_a_noop(hass) -> None:
    _set_player(hass, 0.3)
    calls = []
    hass.services.async_register(
        "media_player", "volume_set", lambda call: calls.append(call.data)
    )

    controller = VolumeController(hass)
    async with controller.announce_at(PLAYER, None):
        pass
    await hass.async_block_till_done()
    assert calls == []


async def test_player_without_volume_support_is_skipped(hass) -> None:
    hass.states.async_set(PLAYER, "idle", {"supported_features": 0})
    calls = []
    hass.services.async_register(
        "media_player", "volume_set", lambda call: calls.append(call.data)
    )

    controller = VolumeController(hass)
    async with controller.announce_at(PLAYER, 0.8):
        pass
    await hass.async_block_till_done()
    assert calls == []


async def test_unknown_entity_is_skipped(hass) -> None:
    calls = []
    hass.services.async_register(
        "media_player", "volume_set", lambda call: calls.append(call.data)
    )

    controller = VolumeController(hass)
    async with controller.announce_at("media_player.nope", 0.8):
        pass
    await hass.async_block_till_done()
    assert calls == []
