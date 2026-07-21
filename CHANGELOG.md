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
