# Changelog

This tracks tagged versions of the visual rig so we can always see what
changed and roll back if a change doesn't work out. Each version is both
a git tag and a section below in plain language (no need to read code to
know what a version contains).

## How to use this (see also README.md "Version control" section)

- See what version you're on: `git describe --tags`
- Go back to an earlier version: `git checkout v1` (or v2, v3, ...)
- Go back to the latest: `git checkout main`
- Compare two versions: `git diff v1 v2`

## v2 — 2026-07-21 — Bug fixes + more aggressive logo camera

- **Scene 2 — fixed a real white-out bug.** The previous version's
  fix (frame-rate-independent decay) exposed a second bug: the shader
  was accumulating `prev*decay + new_glow` every frame, which is
  unbounded — once decay correctly became a slow real-time value, more
  brightness was added each frame than could ever decay away, so the
  whole buffer rocketed to solid white within a second or two. Fixed by
  switching to a bounded decay-weighted blend toward a target color
  (`mix(target, prev, decay)`) instead of open-ended addition — this
  can never blow out, while still producing the same slow trailing
  effect.
- **Scenes 4 & 5 — letter bursts are now a coherent expanding RING**
  instead of a scattered directional burst (same speed/life for every
  particle in the ring, so they move together as one pulse rather than
  spreading into a cloud) — reads much more clearly as a "pulsation."
- **Scenes 4 & 5 — fractal made more present.** Increased spatial
  frequency (zoomed out to reveal more detail) and raised opacity;
  left the `c`-vector rotation speed (the "bloom"/morph speed)
  unchanged, as requested.
- **Scenes 4 & 5 — more aggressive 3D camera angles.** Yaw and pitch
  amplitudes roughly doubled, and a Z-axis roll was added (there was no
  roll at all before) — verified numerically that even at maximum
  combined rotation the plane stays safely within the camera's near/far
  planes (no clipping).

## v1 — 2026-07-21 — Baseline snapshot

This is the first tagged version, taken after the first several rounds
of building/tuning the rig, so it's a baseline rather than a "v0"
starting point. It includes everything built up to this point:

- 5 scenes: `particle_burst`, `feedback_trails`, `noise_field`,
  `logo_pulse`, `logo_video_pulse`
- Per-instrument-channel MIDI routing (kick/snare/hihat/perc/bass/synth2
  /pads/sampler), matching the SEQTRAK's fixed channel layout
- Shared virtual camera (`camera.py`) with automated pan/zoom/rotation,
  tempo-synced breathing, and drum-trigger punches
- Scene 1: dense continuous particle field, per-channel color, erratic
  jitter/flicker during fade-out
- Scene 2: frame-rate-independent decay (half-life in seconds) with a
  soft multi-tap blur for genuinely smooth, slow blending
- Scenes 4 & 5: logo/video rendered as a real 3D-projected plane
  (genuine camera-angle perspective), a fractal + noise + braid
  background, a background pixel-cloud burst, and per-character letter
  bursts (one distinct color per character, edge-fading, tracking the
  plane's current on-screen position) on every drum trigger
