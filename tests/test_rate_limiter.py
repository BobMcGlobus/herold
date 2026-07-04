"""Per-priority rate limiting and P2 aggregation buffering."""

from types import SimpleNamespace

from custom_components.herold.models import Notification
from custom_components.herold.rate_limiter import RateLimiter


def _limiter(hass) -> RateLimiter:
    return RateLimiter(SimpleNamespace(hass=hass))


async def test_p4_is_never_limited(hass) -> None:
    limiter = _limiter(hass)
    for _ in range(10):
        allowed, _ = limiter.check(Notification(message="alarm", priority=4))
        assert allowed


async def test_p3_dedup_by_tag(hass) -> None:
    limiter = _limiter(hass)
    first = Notification(message="Fenster offen", priority=3, tag="fenster")
    duplicate = Notification(message="Fenster offen!", priority=3, tag="fenster")
    other = Notification(message="Tür offen", priority=3, tag="tuer")

    assert limiter.check(first)[0] is True
    assert limiter.check(duplicate)[0] is False
    assert limiter.check(other)[0] is True


async def test_p3_dedup_by_message_without_tag(hass) -> None:
    limiter = _limiter(hass)
    assert limiter.check(Notification(message="gleich", priority=3))[0] is True
    assert limiter.check(Notification(message="gleich", priority=3))[0] is False
    assert limiter.check(Notification(message="anders", priority=3))[0] is True


async def test_p2_window_buffers_overflow(hass) -> None:
    limiter = _limiter(hass)
    for index in range(3):
        allowed, _ = limiter.check(
            Notification(message=f"m{index}", priority=2)
        )
        assert allowed

    allowed, reason = limiter.check(Notification(message="m3", priority=2))
    assert allowed is False
    assert "buffered" in reason
    assert len(limiter._p2_buffer) == 1

    limiter.shutdown()


async def test_ignore_rate_limit_bypasses(hass) -> None:
    limiter = _limiter(hass)
    tagged = {"tag": "x", "priority": 3}
    assert limiter.check(Notification(message="a", **tagged))[0] is True
    bypass = Notification(
        message="b", context={"ignore_rate_limit": True}, **tagged
    )
    assert limiter.check(bypass)[0] is True
