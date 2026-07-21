"""
camera.py
---------
A shared "virtual camera" that every scene reads from, so the whole show
has automated, MIDI-reactive perspective movement instead of a static
frame.

WHAT IT DOES:
- Slow, lazy autonomous pan (a big, gentle figure-eight drift).
- Zoom "breathes" in time with the detected tempo (see BeatClock below),
  so it pulses roughly on the beat even before you tune anything.
- Every drum-channel hit gives the camera a snappy zoom "punch" that
  decays back out — this is the direct MIDI-trigger-driven perspective
  change.
- Slow rotation driven by the bass channel's continuous control (CC),
  so a filter sweep visibly twists the whole frame.

HOW SCENES USE IT:
Each scene's `update()` stores `self.camera = camera` (or just reads the
fields it needs) and its `render()` builds a small transform from
`camera.offset`, `camera.zoom`, `camera.rotation`, `camera.punch` — with
a per-layer "parallax" multiplier (0 = doesn't move at all / far
background, 1 = moves fully / near foreground) so background and
foreground layers drift at different rates, which is what actually
sells the sense of depth.
"""

import math
import numpy as np


class BeatClock:
    """Estimates the current beat period from drum-channel hit timing.

    Keeps a short rolling window of recent inter-hit intervals and takes
    the median (robust to the occasional double-hit or missed hit),
    rather than trying to do full beat-tracking DSP — simple and good
    enough to make the camera's breathing feel tempo-locked.
    """

    def __init__(self, default_period=0.5):
        self.last_beat_time = None
        self.period = default_period  # seconds per beat; 0.5 = 120 BPM guess
        self._intervals = []

    def register_beat(self, now):
        if self.last_beat_time is not None:
            interval = now - self.last_beat_time
            # Ignore intervals that are clearly not "one beat" (double
            # triggers, or a long gap between phrases).
            if 0.15 < interval < 2.0:
                self._intervals.append(interval)
                if len(self._intervals) > 8:
                    self._intervals.pop(0)
                self.period = float(np.median(self._intervals))
        self.last_beat_time = now


class Camera:
    def __init__(self):
        self.time = 0.0
        self.offset = np.array([0.0, 0.0], dtype="f4")
        self.zoom = 1.0
        self.rotation = 0.0
        self.punch = 0.0  # decaying 0-1, spikes on drum hits
        self.beat_clock = BeatClock()

    def update(self, dt, midi):
        self.time += dt

        for _ in midi.role_triggers("drums"):
            self.beat_clock.register_beat(self.time)
            self.punch = 1.0
        self.punch *= 0.90

        bass = midi.role_cc("bass", "intensity", 0.3)
        period = self.beat_clock.period

        # Slow autonomous pan.
        self.offset[0] = 0.14 * math.sin(self.time * 0.05)
        self.offset[1] = 0.09 * math.sin(self.time * 0.035 + 1.3)

        # Zoom breathes on a multiple of the detected beat period, plus a
        # sharp punch on every drum hit.
        breathing = 0.05 * math.sin(2 * math.pi * self.time / max(period * 4, 0.5))
        self.zoom = 1.0 + breathing + self.punch * 0.15

        # Slow continuous rotation, sped up by the bass channel's CC.
        self.rotation += dt * 0.06 * (0.2 + bass)

    def layer_params(self, parallax):
        """Returns (offset, zoom, rotation) scaled for a depth layer.

        `parallax` should be 0..1: 0 = doesn't move (far background),
        1 = moves fully with the camera (near foreground). Values outside
        0..1 are fine too (>1 = exaggerated foreground parallax).
        """
        offset = self.offset * parallax
        zoom = 1.0 + (self.zoom - 1.0) * parallax
        rotation = self.rotation * parallax
        return offset, zoom, rotation
