"""Generate the built-in wake-up tones.

Synthesised rather than sourced so the repository stays free of third-party
audio licensing. Run from the repo root after changing a waveform:

    python scripts/generate_sounds.py
"""

from __future__ import annotations

import math
from pathlib import Path
import struct
import wave

# 16 kHz is ample for tones topping out around 2.2 kHz and keeps the
# repository small — these files ship with the integration.
RATE = 16000
OUT = Path(__file__).resolve().parent.parent / (
    "custom_components/herold/frontend/sounds"
)


def _write(name: str, samples: list[float]) -> None:
    """Write mono 16-bit PCM, normalised to avoid clipping."""
    peak = max((abs(value) for value in samples), default=1.0) or 1.0
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, value / peak)) * 32000))
        for value in samples
    )
    path = OUT / f"{name}.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)
    print(f"{path.name}: {len(samples) / RATE:.1f}s, {path.stat().st_size // 1024} KiB")


def _tone(freq: float, duration: float, harmonics=(1.0, 0.35, 0.12)) -> list[float]:
    """A bell-ish tone: a few harmonics under an exponential decay."""
    count = int(RATE * duration)
    out = []
    for index in range(count):
        position = index / RATE
        envelope = math.exp(-3.2 * position / duration)
        value = sum(
            gain * math.sin(2 * math.pi * freq * (order + 1) * position)
            for order, gain in enumerate(harmonics)
        )
        out.append(value * envelope)
    return out


def _silence(duration: float) -> list[float]:
    return [0.0] * int(RATE * duration)


def chime() -> list[float]:
    """Soft three-note bell — pleasant but present."""
    out: list[float] = []
    for freq in (784.0, 988.0, 1319.0):
        out += _tone(freq, 0.9)
    out += _silence(0.4)
    for freq in (784.0, 988.0, 1319.0):
        out += _tone(freq, 1.2)
    return out


def beep() -> list[float]:
    """Classic alarm clock: hard square bursts in a triplet pattern."""
    out: list[float] = []
    for _ in range(4):
        for _ in range(3):
            count = int(RATE * 0.12)
            for index in range(count):
                position = index / RATE
                square = 1.0 if math.sin(2 * math.pi * 2200 * position) > 0 else -1.0
                # Short fades stop the clicks a raw square would produce.
                fade = min(1.0, position / 0.005, (0.12 - position) / 0.005)
                out.append(square * fade * 0.8)
            out += _silence(0.09)
        out += _silence(0.45)
    return out


def siren() -> list[float]:
    """Urgent two-tone sweep, the one that gets people out of bed."""
    out: list[float] = []
    phase = 0.0
    duration = 6.0
    count = int(RATE * duration)
    for index in range(count):
        position = index / RATE
        # Sweep 700 <-> 1500 Hz twice per second
        sweep = 0.5 + 0.5 * math.sin(2 * math.pi * 1.6 * position)
        freq = 700 + 800 * sweep
        phase += 2 * math.pi * freq / RATE
        value = math.sin(phase) + 0.3 * math.sin(2 * phase)
        attack = min(1.0, position / 0.15)
        out.append(value * attack)
    return out


def sunrise() -> list[float]:
    """Very slow swell — for the gentle urgency level."""
    out: list[float] = []
    duration = 6.0
    count = int(RATE * duration)
    for index in range(count):
        position = index / RATE
        swell = math.sin(math.pi * position / duration) ** 2
        value = (
            math.sin(2 * math.pi * 396 * position)
            + 0.5 * math.sin(2 * math.pi * 528 * position)
            + 0.25 * math.sin(2 * math.pi * 792 * position)
        )
        # Slow tremolo keeps it from sounding like a test tone
        tremolo = 0.85 + 0.15 * math.sin(2 * math.pi * 0.7 * position)
        out.append(value * swell * tremolo)
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, generator in (
        ("chime", chime),
        ("beep", beep),
        ("siren", siren),
        ("sunrise", sunrise),
    ):
        _write(name, generator())
