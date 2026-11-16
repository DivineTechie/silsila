"""Generates the film's music bed and sound effects. Nothing is sampled or downloaded: every sound is
computed here from sine tones and filtered noise.

    uv run --with numpy python make_sound.py      # after record.mjs: it reads out/timeline.json

Writes out/music.wav (a slow, quiet bed for the whole film) and out/sfx.wav (a soft tick on each click, a
breath of noise on each scene change, two bell notes when the judging criterion changes, a small pop as a
graphic comes in, and a closing chord). build.mjs lowers the music under the voice and mixes all three.

The music: four chords of eight seconds each (A minor 9, F major 9, C add 9, G 6/9), played as soft pads
that fade into one another, a low root note, and five slow bell notes per chord. The film ends on C.
"""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import numpy as np

SR = 48000
HERE = Path(__file__).parent
OUT = HERE / "out"


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def add(track: np.ndarray, at: float, sound: np.ndarray) -> None:
    """Mix a stereo sound into the track, starting at `at` seconds."""
    i = int(round(at * SR))
    if i >= len(track) or i + len(sound) <= 0:
        return
    j = min(len(track), i + len(sound))
    track[max(i, 0):j] += sound[max(-i, 0):j - i]


def stereo(mono: np.ndarray, pan: float = 0.0) -> np.ndarray:
    """pan from -1 (left) to 1 (right), equal power."""
    a = (pan + 1) * math.pi / 4
    return np.stack([mono * math.cos(a), mono * math.sin(a)], axis=1) * math.sqrt(2)


def save(path: Path, track: np.ndarray) -> None:
    data = (np.clip(track, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


# ---------------------------------------------------------------- music -----------------------------------
CHORD = 8.0  # seconds each
#          root  pad notes (MIDI)
CHORDS = [
    (45, [57, 60, 64, 67, 71]),  # A minor 9
    (41, [53, 57, 60, 64, 67]),  # F major 9
    (48, [52, 55, 60, 62, 67]),  # C add 9
    (43, [55, 59, 62, 64, 69]),  # G 6/9
]
HOME = 2  # the film ends on C
BELLS = [(0.0, 0), (1.5, 2), (3.0, 4), (4.5, 1), (6.0, 3)]  # when in the chord, and which pad note (an octave up)


def pad(freq: float, seconds: float, fade: float, seed: int) -> np.ndarray:
    """A soft sustained note: a sine with two quiet overtones, slightly detuned between the ears, breathing slowly."""
    t = np.arange(int(seconds * SR)) / SR
    env = np.ones_like(t)
    n = int(fade * SR)
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, n))
    env[:n] = ramp
    env[-n:] = ramp[::-1]
    breath = 1 - 0.18 * (0.5 + 0.5 * np.sin(2 * math.pi * (0.07 + 0.013 * (seed % 5)) * t + seed))

    def tone(f: float) -> np.ndarray:
        return np.sin(2 * math.pi * f * t) + 0.22 * np.sin(2 * math.pi * 2 * f * t) + 0.06 * np.sin(2 * math.pi * 3 * f * t)

    return np.stack([tone(freq * 0.9996), tone(freq * 1.0004)], axis=1) * (env * breath)[:, None]


def bell(freq: float, seconds: float = 4.0) -> np.ndarray:
    """A soft struck note that rings and fades."""
    t = np.arange(int(seconds * SR)) / SR
    attack = np.minimum(1, t / 0.008)
    y = np.sin(2 * math.pi * freq * t) * np.exp(-t / 1.1) + 0.28 * np.sin(2 * math.pi * 2 * freq * t) * np.exp(-t / 0.45)
    y += 0.08 * np.sin(2 * math.pi * 3 * freq * t) * np.exp(-t / 0.2)
    return y * attack


def music(total: float) -> np.ndarray:
    track = np.zeros((int(total * SR), 2))
    fade = 3.0
    n_chords = math.ceil(total / CHORD)
    for k in range(n_chords):
        start = k * CHORD
        ending = start >= total - 14  # the last chords are the home chord
        root, notes = CHORDS[HOME if ending else k % len(CHORDS)]
        # each chord sounds from a little before its turn to a little after, so chords melt into each other
        for i, m in enumerate(notes):
            add(track, start - fade / 2, pad(hz(m), CHORD + fade, fade, seed=k * 7 + i) * 0.11)
        bass = pad(hz(root), CHORD + fade, fade, seed=k)
        add(track, start - fade / 2, bass * 0.16)
        for j, (when, which) in enumerate(BELLS):
            add(track, start + when, stereo(bell(hz(notes[which] + 12)), pan=0.4 if (k + j) % 2 else -0.4) * 0.05)
    t = np.arange(len(track)) / SR
    track *= (np.minimum(1, t / 3.0) * np.minimum(1, np.maximum(0, (total - t) / 5.0)))[:, None]
    return track / np.max(np.abs(track)) * 0.7


# -------------------------------------------------------------- effects -----------------------------------
def tick() -> np.ndarray:
    """A click on a button: a short, soft, falling tick with a little body."""
    t = np.arange(int(0.14 * SR)) / SR
    f = 700 + 400 * np.exp(-t / 0.02)
    y = np.sin(2 * math.pi * np.cumsum(f) / SR) * np.exp(-t / 0.022) + 0.6 * np.sin(2 * math.pi * 220 * t) * np.exp(-t / 0.03)
    return stereo(y * np.minimum(1, t / 0.002)) * 0.062


def breath(seconds: float, level: float, rng: np.random.Generator) -> np.ndarray:
    """A scene change: noise that opens up and closes again, like a soft breath."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal((n, 2))
    cutoff = 300 + 2300 * np.sin(math.pi * t / seconds) ** 2  # the filter opens and closes
    a = 1 - np.exp(-2 * math.pi * cutoff / SR)
    y = np.zeros((n, 2))
    last = np.zeros(2)
    for i in range(n):  # one-pole low-pass with a moving cutoff
        last = last + a[i] * (noise[i] - last)
        y[i] = last
    rise = 0.62 * seconds
    env = np.where(t < rise, np.sin(0.5 * math.pi * t / rise) ** 2, np.cos(0.5 * math.pi * (t - rise) / (seconds - rise)) ** 2)
    y *= env[:, None]
    return y / np.max(np.abs(y)) * level


def chime() -> np.ndarray:
    """A new judging criterion: two bell notes, a fifth apart, in the music's key."""
    out = np.zeros((int(2.4 * SR), 2))
    for when, midi, pan in [(0.0, 79, -0.25), (0.11, 86, 0.25)]:  # G5, D6
        t = np.arange(int(2.2 * SR)) / SR
        f = hz(midi)
        y = (np.sin(2 * math.pi * f * t) + 0.18 * np.sin(2 * math.pi * 2.76 * f * t) * np.exp(-t / 0.15)) * np.exp(-t / 0.5) * np.minimum(1, t / 0.004)
        add(out, when, stereo(y, pan) * 0.06)
    return out


def pop() -> np.ndarray:
    """A graphic coming in: one short, low, round note."""
    t = np.arange(int(0.5 * SR)) / SR
    y = np.sin(2 * math.pi * hz(74) * t) * np.exp(-t / 0.09) * np.minimum(1, t / 0.006)  # D5
    return stereo(y) * 0.035


def closing() -> np.ndarray:
    """The last card: the home chord, one note after another."""
    out = np.zeros((int(5.0 * SR), 2))
    for i, midi in enumerate([72, 76, 79, 84]):  # C5 E5 G5 C6
        add(out, i * 0.13, stereo(bell(hz(midi), 4.5), pan=-0.3 + 0.2 * i) * 0.045)
    return out


def effects(total: float, events: list[dict]) -> np.ndarray:
    rng = np.random.default_rng(3)
    sounds = {"tap": tick(), "whoosh": breath(0.9, 0.05, rng), "swish": breath(0.6, 0.032, rng), "chime": chime(), "pop": pop(), "close": closing()}
    track = np.zeros((int(total * SR), 2))
    last: dict[str, float] = {}
    for e in events:
        kind, at = e["type"], e["at"]
        if kind not in sounds or at - last.get(kind, -9) < 0.25:  # never the same sound twice within a quarter second
            continue
        last[kind] = at
        add(track, at, sounds[kind])
    return track


def main() -> None:
    tl = json.loads((OUT / "timeline.json").read_text())
    total = math.ceil(tl["seconds"]) + 1
    m = music(total)
    save(OUT / "music.wav", m)
    events = tl.get("events", [])
    fx = effects(total, events)
    save(OUT / "sfx.wav", fx)
    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    rms = lambda x: 20 * math.log10(max(1e-9, float(np.sqrt(np.mean(x ** 2)))))
    print(f"music.wav: {total} s, rms {rms(m):.1f} dBFS, peak {20 * math.log10(float(np.max(np.abs(m)))):.1f} dBFS")
    print(f"sfx.wav: {len(events)} cues {counts}, peak {20 * math.log10(max(1e-9, float(np.max(np.abs(fx))))):.1f} dBFS")


if __name__ == "__main__":
    main()
