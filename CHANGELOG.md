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

## v7 — 2026-07-21 — Camera decoupled from background, edge-to-center fractal bloom, logo glitch, fullscreen native resolution

- **Scenes 4 & 5 — braid confirmed final, kept as-is** (thick pipe +
  thin flowing sliver from v6).
- **Scenes 4 & 5 — fractal/braid no longer pulsate with the logo.**
  Removed the background shader's camera coupling entirely (it was
  reading the shared camera's zoom/pan/rotation, including its
  drum-triggered "punch," at reduced strength) — now only the logo/video
  plane itself reacts to hits; the background is fully independent.
- **Scenes 4 & 5 — fractal frequency increased again**, and it now
  blooms in cyclically from the edges toward the center (a sweeping
  reveal wave) rather than being uniformly visible everywhere at once.
- **Scenes 4 & 5 — subtle glitch effect added to the logo/video plane.**
  Rare (roughly every 10-25s), brief (0.05-0.15s), combining a small
  horizontal slice-tear with a slight chromatic (RGB) channel split —
  kept deliberately minor so it reads as a quick flicker, not a
  dramatic effect.
- **Fullscreen now auto-fits the display's native resolution/refresh
  rate** (including 4K, if that's what the screen/projector reports)
  instead of a hardcoded size.
- **(b) Percussion-triggered burst:** re-audited the full trigger →
  spawn → render path again and it continues to check out logically;
  still unresolved without the `MIDI_DEBUG` output requested in v6 to
  confirm whether channels 4-7 are actually arriving as separate
  channels from the SEQTRAK/Ableton setup.

## v6 — 2026-07-21 — Braid restored + thin flowing sliver, MIDI debug tool

- **Scenes 4 & 5 — braid separated into two distinct elements.** The
  previous version had conflated "make the streak thin/erratic" into
  the braid's own shape, making the whole pipe thin. Restored: the
  braid "pipe" itself is back to its original thickness and smooth
  sine-only path; a NEW, separate thin sliver of contrasting color now
  wanders erratically and travels along the strand, flowing inside the
  pipe's width — like colored light moving through a transparent tube,
  rather than the tube itself being thin.
- **MIDI debug tool.** Added `MIDI_DEBUG` in `config.py` — when set to
  `True`, every incoming MIDI message is printed to the terminal
  (type, channel as 1-16, note/CC value), to help confirm whether
  gear/DAW routing is actually sending distinct channels per part.
  Added after repeated reports that the percussion-triggered particle
  burst "isn't working" despite the trigger logic checking out
  end-to-end in code review — this is the fastest way to see what's
  actually arriving at the channel level.

## v5 — 2026-07-21 — Split drums/percussion mapping, letter effect reworked as gentle particles

- **New MIDI mapping split.** "Mapping 1" (the `drums` role) now covers
  only channels 1-3 (kick, snare, snare2/clap) — channels 4-7 (hi-hat
  1/2, perc 1/2) were moved out into a brand new `percussion` mapping,
  kept completely separate. This changes what channels 4-7 drive
  everywhere `drums` was previously read (camera tempo/punch detection,
  scene 2's pulse, scene 3's brightness CC) — they no longer contribute
  to those, only channels 1-3 do now.
- **Scenes 4 & 5 — glow pulse concept fully replaced.** The analytic
  shader-based glow (from v3/v4) is gone entirely — removed the
  `u_pulse_*` uniforms and shader code. In its place: a real, gentle
  burst of particles from each character (few particles, slow speed,
  muted saturation), using the same reusable `ParticleField` as the
  background pixel-cloud. Crucially, this new burst is triggered by the
  **new `percussion` mapping**, not `drums` — so hi-hats/perc now
  animate the characters, while kick/snare/snare2 still drive the
  background pixel-cloud and camera punch as before.

## v4 — 2026-07-21 — Dimmer/diffuse/noisy pulse, thinner erratic braid strands

- **Scenes 4 & 5 — glow pulse made dimmer, more diffuse, and grainy.**
  The band is now much wider/softer (lower falloff exponent) instead of
  a crisp ring, a noise-based "grain" term breaks it up into sparse,
  dusty flecks rather than a smooth gradient, and overall intensity was
  cut significantly (roughly 2.3x dimmer).
- **Scenes 4 & 5 — braid strands are now thin, with an erratic
  trajectory.** Falloff exponent raised substantially (much thinner
  lines), and a two-octave noise wobble was added on top of the
  existing sine curves so the path drifts irregularly instead of
  following a perfectly smooth periodic wave.

## v3 — 2026-07-21 — Gentler pulse, bigger points, 3-axis pop origins, denser fractal, braid flicker

- **Scenes 4 & 5 — pulsation replaced with a gentle glow.** The
  particle-ring burst (from v2) was still too intense/explosive. It's
  now a soft, analytic glow pulse computed directly in the background
  shader — a gently expanding, soft-edged ring of light with a quick
  fade-in and slow fade-out, no discrete points at all. Positioned the
  same way as before (projected through the logo's 3D transform so it
  tracks each character correctly).
- **Scene 1 — bigger points.** Base point size roughly doubled so the
  field reads as close/substantial rather than distant and small.
- **Scene 1 — pop origins randomized across X, Y, *and* Z.** Previously
  Y was always pinned to 0 for every burst (only X and, per-particle,
  Z varied) — now each pop's starting point is randomized across all
  three axes, so successive pops visibly start from different places
  in the field rather than always along the same horizontal line.
- **Scenes 4 & 5 — fractal frequency increased further** (zoomed out
  more to reveal more repeating detail), still with the morph/bloom
  speed unchanged.
- **Scenes 4 & 5 — braid now flickers** in a contrasting color: small
  stretches of the strands randomly brighten a few times a second, like
  light catching a moving thread, layered on top of the existing slow
  weave.

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
