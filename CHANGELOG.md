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

## v18 — 2026-07-21 — New scene 7: hollow-character sequence from client artwork

- **New scene 7 — `hollow_chars_pulse.py`**, a structural copy of scene
  5 (same 3D camera-angle plane, background pixel-cloud, per-character
  particle burst, fractal/noise/braid background, glitch effect,
  pad-triggered fractal bloom) but displaying a STATIC image instead of
  the spin-loop video.
- **Source asset extracted from the client's `OCA_clientversion.ai`**
  (page 2): identified three large connected hollow-outline text
  shapes via connected-component analysis on the rendered page, cross-
  checked against the PDF's actual glyph position data (which showed
  fragmented per-letter runs consistent with "RHYTHM GATHERING" /
  "SOUND FLOWING" arranged in a circular layout) — isolated just those
  three shapes (excluding surrounding poster text like artist names,
  date, and venue info) into a clean transparent PNG
  (`assets/hollow_chars.png`).
- **Flagged for confirmation**: this identification was done
  programmatically (OCR did not work on the stylized connected font),
  so the extracted asset was shared for a visual sanity check before
  being wired in. The letter-burst positions in this new scene use a
  single placeholder center anchor rather than mapped per-character
  positions, since this artwork's internal layout hasn't been analyzed
  the way the OCA logo's three circles were.

## v17 — 2026-07-21 — Recovery: v12-v15 work restored after silent data loss

**What happened:** while implementing the v16 cursor fix, discovered
that all code changes from v12 through v15 had silently disappeared
from the project files — the container's working state had reverted to
v11 at some point without any visible error, and everything reported
as "done" in those four rounds never actually persisted. Git history
confirms this: v16 was built directly on top of the v11 commit.

**What this version restores** (rebuilt from scratch to match what
v12-v15 were meant to contain):
- MIDI Clock support in `midi_input.py` (`triplet_tick_pending`, fired
  every 8 pulses / a musical triplet)
- The dual randomized bloom-cell fractal system in `logo_pulse.py` and
  `logo_video_pulse.py` (varied origins, staggered/overlapping timing,
  area-uniform reveal metric)
- Full rebuild of `kaleidoscope_video.py`: the video-texture-aspect fix,
  the synth2-gated psychedelic asanoha background layer, and the
  always-lit glyph-based "温泉" ring with the MIDI-clock-driven pop
  chase
- Regenerated `assets/onsen1.png` / `assets/onsen2.png`

Re-verified numerically after rebuilding: the dual bloom cells still
never drop combined brightness below ~50-60%, and the fractal
detail-distribution and glyph-ring math all check out the same as
originally validated. Everything from v1-v11 and the v16 cursor fix
was confirmed still intact and unaffected throughout this.

## v16 — 2026-07-21 — Auto-hiding mouse cursor

- **Mouse cursor now auto-hides after ~2 seconds of no movement**
  (like a video player or any other fullscreen visual app), and
  reappears instantly the moment the mouse moves again. Configurable
  via `CURSOR_IDLE_HIDE_SECONDS` in `config.py` (set to `None` to
  disable and always show the cursor).

## v15 — 2026-07-21 — Fractal bloom variety + smoother blend, scene 6 always-lit characters

- **Scenes 4 & 5 — fractal bloom no longer always starts from the same
  spot.** Replaced the single sweep fixed to screen center with TWO
  overlapping "bloom cells," each with its own randomized origin.
  Scene 4 (auto mode): the two cells are staggered by half the cycle
  length, so one is always fading in while the other fades out —
  verified numerically that combined brightness never drops below 60%
  of full. Scene 5 (triggered mode): a new pad trigger shifts the
  current bloom into a "previous" cell that keeps fading out on its
  own while a fresh one starts fading in, so consecutive triggers
  blend into each other instead of cutting off abruptly.
- **Scenes 4 & 5 — smoother-feeling transition.** Switched the reveal
  comparison from raw distance to distance-squared, since screen area
  grows with r² and sweeping raw distance reveals area unevenly.
- **Scene 6 — characters are now always lit** at a legible baseline;
  the MIDI-clock chase is a brighten + slight outward glide layered on
  top, not a visibility toggle.

## v14 — 2026-07-21 — Fixed mirrored text, rebuilt as per-character MIDI-clock-driven pop chase

- **Found the actual cause of the mirrored/wrong-order characters** —
  the previous baked-ring + counter-flip approach was mathematically a
  no-op, not a fix; the real issue was in how per-character rotation
  was baked into the source image.
- **Redesigned around two individual glyph textures** ("温"/"泉",
  unrotated), each ring position its own controllable "slot," using the
  angular position as the glyph's own texture coordinate directly —
  correct orientation by construction.
- **Real MIDI Clock support added** (`midi_input.py`) — tracks the
  standard 24-pulses-per-quarter-note sync signal and fires a
  `triplet_tick_pending` event every 8 pulses. Requires clock/sync
  output enabled at the source (off by default on most gear/DAWs).
- **Sequential per-character pop, timed to that clock**, order
  configurable via `RING_POP_ORDER` (clockwise / counter-clockwise /
  random).

## v13 — 2026-07-21 — Scene 6 psychedelic background + text ring, scene 5 pad-triggered fractal

- **Scene 6 background layer made genuinely psychedelic and more
  Japanese**: a real hex-tessellated asanoha (hemp-leaf) lattice
  layered with the polar crossing-line/petal motif, and a hue that
  cycles with angle, radius, and time simultaneously.
- **Scene 6 — "温泉" text ring added**, pre-rendered via the Noto Sans
  CJK font for portability (not rendered live from a font at runtime).
- **Scene 5 — fractal bloom triggered by channel 10 ("pads")** instead
  of cycling automatically; scene 4 keeps its automatic cycle.

## v12 — 2026-07-21 — Scene 6: contrasting background layer + fixed elliptical logo mirroring

- **Fixed elliptical mirrored logo elements**: the kaleidoscope's fold
  was aspect-corrected for screen space, but the resulting sample
  position wasn't corrected for the video texture's OWN aspect ratio
  (the source is portrait) — added `u_video_aspect` to fix this
  separately.
- **New background kaleidoscope layer, gated by channel 9 ("synth2")**:
  a procedural asanoha-inspired motif fills the empty/black areas
  behind the foreground video-kaleidoscope while that channel has a
  note held, eased in/out.

## v11 — 2026-07-21 — Scenes 1/2 aspect-ratio fix, validated across all scenes, new kaleidoscope scene

- **Root cause of scenes 1 & 2 looking "sparse and close": found and
  fixed.** Both had an internal trail-accumulation buffer hardcoded to
  1280x720 (16:9), decoupled from the actual output resolution. That
  buffer gets blitted onto whatever the real output is via a simple
  full-screen stretch — if the real display isn't exactly 16:9 (very
  common; many laptop/external displays aren't), that stretch is
  non-uniform, squashing/compressing content along whichever axis is
  proportionally smaller. Fixed by computing that buffer's size from
  the ACTUAL output aspect ratio instead of a hardcoded one (new
  `compute_work_size()` in `utils.py`), and added a proper
  `Scene.resize()` hook (called by `SceneManager` whenever the window
  size changes) so this stays correct if the output size changes later,
  not just at startup.
- **Validated the same class of bug across scenes 3-5**
  (`noise_field`, `logo_pulse`, `logo_video_pulse`): confirmed none of
  them have a fixed-resolution internal buffer like scenes 1 & 2 did.
- **Found and fixed a related but distinct issue while checking:**
  circular patterns (the fractal bloom, noise ripples, feedback blobs,
  the particle field's swirl/burst motion) were all computed in raw
  normalized coordinates without correcting for the screen's actual
  aspect ratio, which stretches anything meant to look round into an
  ellipse on any non-square display. Added proper aspect correction to
  all five scenes.
- **New scene 6 — `kaleidoscope_video.py`.** The spin-loop video fed
  through a mirrored radial kaleidoscope (6-12 wedges, count nudged by
  the "keys" channel), dressed with a few Japanese-inspired elements: a
  seigaiha (layered wave/fan) pattern in indigo behind everything,
  drifting sakura (cherry blossom) petals spawned gently on drum hits,
  a thin gold mandala ring with periodic notches, and color grading
  pulled toward a traditional indigo/vermillion/gold palette rather
  than the source video's raw colors. Rotation speed follows the
  "bass" channel; program-change 5 switches to it.

## v10 — 2026-07-21 — Fractal bloom: smooth in/out, much longer cycle

- **Scenes 4 & 5 — fixed the actual cause of "fades suddenly."** The
  reveal wave used `fract(time)`, a sawtooth: it ramped up smoothly but
  then snapped back to empty instantly at the end of every cycle.
  Verified numerically (sampled the center-screen mask across a cycle):
  it held at full brightness then dropped to zero within ~0.25s out of
  a 6.3s cycle — a highly asymmetric slow-rise/instant-fall shape,
  which reads exactly as "fades suddenly." Replaced with a continuous
  triangle wave (smooth ramp up, smooth ramp down, no jump at the
  wrap point) and roughly tripled the period (was ~6.3s round trip,
  now ~20s), so there's real time for it to fully bloom before it
  recedes again, and the recede itself is now gradual.

## v9 — 2026-07-21 — Fractal is one connected entity (not tiled), real window-resize handling

- **Scenes 4 & 5 — removed the fractal tiling.** The v8 fix solved the
  "only visible near center" bug but did so by repeating small tiles,
  which read as copy-pasted thumbnails rather than one fractal. Now a
  single, non-tiled fractal at a scale verified numerically to spread
  real detail across edges, corners, and center (not just the middle) —
  so the edge-to-center reveal wave now blooms an actual connected
  shape inward, the way a real fractal zoom feels, rather than either
  a mostly-empty field (v7) or repeated copies (v8).
- **Fixed a real window-resize bug.** The app had no framebuffer-resize
  handling at all — if the window changed size any way other than our
  own startup fullscreen path (dragging an edge, the OS's native
  maximize/fullscreen button, an external display change), rendering
  stayed pinned to whatever size it started at, and the OS just
  stretched those old pixels to fit — which is exactly what "stuck at
  the original aspect ratio" looks like. Added a proper
  framebuffer-size callback that keeps the GL viewport and the scene
  manager's internal buffers (and anything reading `target.size`, like
  the logo scenes' aspect ratio) in sync with the actual current size
  at all times, plus a per-frame viewport safeguard against moderngl's
  own framebuffer-switching resetting it mid-frame.

## v8 — 2026-07-21 — Fixed the actual fractal bug, calmer pulse, visible glitch

- **Scenes 4 & 5 — found and fixed the real fractal bug.** Every prior
  "increase frequency" request was implemented by zooming the Julia
  set's input coordinates further OUT — but for this kind of fractal,
  points far from the origin escape almost immediately, so a larger
  multiplier actually SHRINKS the area with any visible detail down to
  a small patch near the screen center, with everywhere else reading
  as flat/empty. That's why it looked like it bloomed from the center
  regardless of the reveal-wave mask — there was nothing outside the
  center for the mask to reveal. Verified numerically: the old approach
  had visible detail in only 1 of 9 screen regions; the fix (tiling the
  fractal into a repeating grid instead of zooming out) spreads it
  evenly across all 9. Also sped up the reveal-wave cycle substantially
  (was ~20s, now ~6.3s).
- **Scenes 4 & 5 — logo pulse toned down.** The drum-punch contribution
  to the logo's yaw/roll tilt cut roughly 4-5x (was 0.55/0.35, now
  0.12/0.08) — should read as a small, discrete nudge per hit rather
  than a big lurch.
- **Scenes 4 & 5 — glitch made much more noticeable.** Switched from
  uniform tiny jitter on every band to a sparser-but-much-stronger tear
  (only some horizontal bands shift, and when they do it's a real
  displacement), tripled the chromatic split, and roughly tripled the
  duration (was 0.05-0.15s, now 0.18-0.4s) so there's actually time to
  perceive it.

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
