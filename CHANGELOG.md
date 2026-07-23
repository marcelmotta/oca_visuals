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

## v35 — 2026-07-22 — Faster freeze reaction + settle-then-reset instead of freezing mid-motion

- **Freeze reaction sped up**: `MIDI_ACTIVITY_TIMEOUT_SECONDS` cut from
  5s to 0.3s, so pausing MIDI reads as an almost-immediate reaction.
- **Freezing mid-animation replaced with a proper settle-then-reset.**
  Previously, stopping MIDI would freeze every scene at whatever
  arbitrary instant the timeout elapsed — including the logo plane
  stuck at a random mid-tilt angle. Now there's a brief settle window
  (`MIDI_SETTLE_DURATION_SECONDS`, default 1.5s) where everything keeps
  animating normally so anything genuinely in motion (a burst
  mid-flight, a crossfade) finishes/settles on its own, and only after
  that does every scene reset ONCE to a defined neutral pose — the
  logo's rotation returns to its initial untilted orientation,
  particles/ripples/petals are cleared, trail buffers wiped — and holds
  there until MIDI resumes. New `Scene.reset_to_static()` hook
  (default no-op) implemented for all 5 scenes.
- Verified the full state machine numerically across multiple simulated
  on/off/on/off cycles: correct fast reaction, correct settle window,
  and the reset firing exactly once per quiet period (not repeatedly).
- Re-ran the render-before-update safety audit after these changes;
  still clean.

## v34 — 2026-07-22 — Static-until-MIDI reworked: repeatable toggle + scene-switching always works

- **Found that the previous version's fix had never actually been
  shipped.** The v33 zip that was sent only had the original one-way
  latch (freezes once at launch, never re-freezes) — a proper rework
  was already sitting in the project as uncommitted changes, never
  packaged. This version finishes and ships that work, verified before
  committing rather than assumed correct.
- **Freeze now toggles repeatedly, not a one-way switch.** Tracks time
  since the last channel-based MIDI message; if none arrives for
  `MIDI_ACTIVITY_TIMEOUT_SECONDS` (default 5s), the show freezes again,
  and un-freezes the moment MIDI resumes — verified numerically across
  a simulated multi-cycle on/off/on/off sequence.
- **Scene switching (keyboard or MIDI program-change) now always works
  immediately, even while frozen.** The crossfade timer advances
  unconditionally regardless of freeze state — only each scene's own
  animated content (particle motion, hue drift, etc.) freezes, never
  the ability to change which scene is showing.
- Re-ran the earlier static-analysis safety check (render() depending
  on update()-only attributes) against the current state to confirm
  nothing regressed.

## v33 — 2026-07-22 — Fractal removed from scene 4 entirely, static-until-MIDI feature added

- **Scene 4 — fractal background removed completely**, per feedback
  that the "black animation tied to channel 10" persisted despite
  several fix attempts (brightness floor, removing an artifact-
  introducing clear zone, a persistent baseline tint). Rather than
  patch the same system again, it's been pulled out entirely — the
  scene is now just the logo (3D plane + glitch) and the braid, as a
  clean foundation to rebuild the fractal from scratch on.
- **New feature: stay on a static frame until MIDI arrives.** By
  default, every scene (and the shared camera's own autonomous drift)
  now stays completely still from launch until MIDI is actually
  received from a connected device — a one-way latch, so ordinary gaps
  /silence between notes afterward don't re-freeze the show. Toggle via
  `WAIT_FOR_MIDI_BEFORE_ANIMATING` in `config.py`. While implementing
  this, a static-analysis pass caught a real crash risk: `render()` in
  three scenes (`feedback_trails`, `kaleidoscope_video`, `noise_field`)
  depended on attributes only ever set inside `update()` — since the
  new feature can call `render()` before `update()` has run even once,
  this would have crashed on the very first frame. Fixed by giving all
  of them safe defaults in `setup()`, verified with the same static
  analysis afterward.

## v32 — 2026-07-22 — Denser/stronger wind gust, real cause of "black animation" found

- **Scene 1 — wind gust made denser and more cohesive.** Ambient
  particle spawn rate now boosts substantially while wind is active
  (up to +220/sec on top of the base rate), so there's enough material
  in the air for the gust to read as a moving mass rather than a few
  sparse points getting nudged. Overall push strength increased (~1.7x)
  and per-particle jitter increased for more visible dispersion, while
  the shared directional term still keeps it reading as one gust.
- **Scene 4 — audited every use of channel 11 ("texture"/"sampler") in
  the project as requested**: it's referenced only in scenes 1 and 3
  (unrelated files) — not anywhere in scene 4's code. That check led to
  the actual mechanism, though: verified numerically that without any
  pad (channel 10) trigger ever firing, the fractal's bloom stays
  permanently at zero — the background is pure black (except the
  braid) the entire time, by construction. Channel 10 triggers are the
  ONLY thing that ever makes that permanently-black background move at
  all (via the traveling reveal wave), which is what was actually being
  seen as "a black animation tied to channel 10" — not something drawn
  by the trigger, but the only thing that ever animates an otherwise
  permanently-black background. Fixed with a persistent dim baseline
  tint so the background is never pure black in the first place,
  whether the bloom is dormant or actively cycling — verified the
  baseline is always above zero brightness.

## v31 — 2026-07-22 — Actually fixed the black blur (brightness floor), added wind effect to scene 1

- **Scene 4 — found the REAL cause of the black blur this time.**
  Verified numerically: a Julia set's escaped region (the vast majority
  of a typical view) evaluates to near-zero iteration count — measured
  at ~99% of the screen rendering as near-total black with the previous
  `f*f` brightness formula. With a pure-black base and the fractal as
  the only fill layer, that meant the "fractal background" was
  genuinely black across nearly the whole screen almost all the time —
  not a rare edge case, the norm. Fixed with a brightness floor
  (`mix(0.15, 1.0, f*f)`), verified numerically to bring the near-black
  fraction from 99% down to exactly 0%.
- **Scene 1 — new erratic "wind" effect, triggered by "synth2" (channel
  9).** While that channel has a note held (eased in/out), particles
  get pushed by a gusting force — direction and strength built from
  several non-harmonically-related sine waves (verified numerically to
  have multiple distinct frequency components, not simple periodic
  motion) plus per-particle random jitter, so particles scatter
  individually like debris in wind rather than drifting in unison.

## v30 — 2026-07-22 — Fixed real aspect-ratio bug (scene 1), removed black-disc artifact (scene 4)

- **Scene 1 — found the actual cause of "confined to a square region."**
  The vertex shader divides the final x position by `u_aspect` (to keep
  swirl/burst motion circular rather than elliptical) — but particle
  spawn positions were chosen in a plain -1..1 range without accounting
  for that division, so everything ended up confined to a square-
  looking region in the middle of any widescreen output, exactly as
  reported. Verified numerically: a spawn position that should reach
  the true screen edge was only reaching 53% of the way there. Fixed by
  scaling spawn x-ranges (both ambient particles and burst origins) by
  the actual aspect ratio, so they correctly reach ~95% of true screen
  width after the shader's correction — confirmed numerically.
- **Scene 4 — found and removed the actual cause of the "black blur."**
  The v28 fix added a static radial "clear zone" to keep the fractal
  from covering the logo at peak bloom — but since the background
  starts at pure black and the fractal is the only thing that can light
  that area up, suppressing it there created a PERMANENT black disc at
  screen center, in the fractal's own layer specifically (which is
  exactly what was reported: present in the background/fractal layer,
  not affecting the braid or logo, since those are computed/drawn
  separately). Removed the artificial zone entirely and replaced it
  with a simple, non-artifact-introducing intensity cap (0.65 -> 0.4)
  — verified numerically that the fractal's contribution is now uniform
  at every radius during full bloom, with no fixed dark patch anywhere.

## v29 — 2026-07-22 — Scene 4 removed, scene 5 stripped down to 3 elements, wider particle bursts

- **Scene 1 — burst origins widened toward the screen edges.** Bursts
  were clustering toward the center (origin ranges were only ±0.6/±0.8
  out of the full ±1.0 screen extent); widened to ±0.85-0.95 for a
  fuller "landscape" spread. Note: the continuous ambient background
  particles already used the full range — this only affects the
  discrete per-hit bursts.
- **Scene 4 ("logo_pulse") removed entirely.** Scenes renumbered to
  close the gap: what was scene 5 (`logo_video_pulse`) is now scene 4,
  and what was scene 6 (`kaleidoscope_video`) is now scene 5.
  Program-change/key mappings updated accordingly (0-4 instead of 0-5).
- **Scene 5 (formerly 6... see above, formerly "scene 5" in
  conversation, `logo_video_pulse.py`) isolated down to exactly 3
  elements**, per feedback that a persistent "triggered blur" issue
  remained even after the v28 fix: 1) the braid (thick pipe + thin
  flowing sliver), 2) the animated video plane with its glitch effect,
  and 3) the fractal background (pad-triggered, with the v28 center
  -clear fix retained). Removed: the noise-wash background layer, the
  background pixel-cloud particle burst, and the percussion-triggered
  per-character letter burst. The file is now fully self-contained
  (previously shared shader code with the now-deleted logo_pulse.py).
  This was as much a simplification as a targeted fix — with fewer
  simultaneous effects, whatever was still causing the residual blur
  no longer has as many places to hide.

## v28 — 2026-07-22 — Fixed fractal bloom obscuring the logo's center (scenes 4 & 5)

- **Found the actual cause of the reported "blur blocking the center"
  on channel 10.** At full bloom, the fractal's reveal mask saturates
  to 1.0 across the ENTIRE screen (it's based on `dist_sq >= 0`, which
  is always true) — meaning at peak bloom the fractal fully covers
  every part of the frame where the video's black background is
  transparent, i.e. everywhere except the mark's own white shapes,
  including right behind/around the logo. Channel 10 (pads) is what
  triggers scene 5's bloom, which is why it looked tied to that channel
  specifically; the same mechanism exists in scene 4 too (shared code),
  just less obviously since that bloom cycles automatically rather
  than from an obvious user action.
- **Fixed with a protected "clear zone"**: the fractal's contribution
  now ramps from zero at the exact center up to full strength by radius
  0.45, so the area immediately around the logo/video plane always
  stays clear regardless of bloom state, while the fractal still blooms
  fully everywhere further out. Verified numerically before/after.
- Note: scene 6 doesn't have this fractal-bloom mechanism at all (it's
  specific to scenes 4/5's shared background shader) — if scene 6 has a
  separate issue, it needs its own description since this fix doesn't
  touch it.

## v27 — 2026-07-22 — MIDI hot-plug, less vivid glitch, scene 3 ripple tuning + directional shading

- **MIDI hot-plug support.** Previously the MIDI port was only opened
  once at startup — plugging the SEQTRAK in after launch did nothing
  until restart. Now retries opening a port every 3 seconds in the
  background if none is connected (or one disconnects mid-show), via a
  cheap OS port-list check — negligible CPU cost since it's done every
  few seconds, not every frame.
- **Scenes 4 & 5 — glitch color toned down.** Reduced the chromatic
  (RGB) split amount by 40% (0.02 -> 0.012) for less vivid fringing
  during the glitch. (Scene 6 doesn't currently have a glitch effect —
  see note below.)
- **Scene 3 — fewer secondary ripples, slower expansion.** Retuned the
  ripple's wave frequency/decay (verified numerically) so it now shows
  about 2 visible bands (the primary impact + one clear secondary)
  instead of 4-5, and slowed the expansion speed noticeably (0.55 ->
  0.35).
- **Scene 3 — real directional shading added**, replacing the flat
  brightness bump: the ripple's gradient now builds a fake surface
  normal, lit by a fixed "parallel light source" direction, giving a
  genuine bright/dark sheen depending on slope direction (verified
  numerically: flat areas shade to exactly zero, and different slope
  directions produce both brighter and darker results, not just a
  uniform glow) — much closer to real light catching moving water.

## v26 — 2026-07-22 — Scene 3: ripples now refract the background instead of drawing a ring on top

- **Reworked ripples into a genuine refraction effect.** Instead of an
  additive colored ring drawn over the noise field, each ripple now
  computes a small displacement (a decaying oscillation trailing the
  leading edge — several bands, like real water) that WARPS the
  sampling coordinate used for the background/foreground noise layers
  themselves. The underlying pattern visibly distorts as a ripple
  passes through it, as if seen through a disturbed water surface with
  the noise field as the bottom surface beneath it, plus a subtle
  bright/dark sheen at the ripple's steepest point rather than a flat
  colored ring. Verified numerically: displacement peaks at a modest
  ~2% of screen half-width right at the leading edge, decaying over
  several oscillations behind it — a real warp, not an extreme one.

## v25 — 2026-07-22 — Scene 3: no more MIDI-linked pulsation, slower background, droplet-style ripples

- **Camera zoom removed entirely from scene 3's background/foreground
  layers** (was damped to 40% in v24, evidently still noticeable) —
  only rotate/pan remain, so the scene no longer visibly reacts to
  drum-hit "punches" or tempo-linked breathing at all.
- **Background layer flow speed halved** — the back-and-forth noise
  animation was moving too fast; time multipliers cut from
  0.06/0.05/0.02 to 0.03/0.025/0.01.
- **Ripples redesigned to look like an actual droplet impact**: a
  primary ring plus two smaller, fainter trailing rings behind it
  (rather than one plain ring), faster decay (max age cut from 4s to
  1.8s), and — the main mechanism now — a genuine distance-based
  falloff, so the ripple visibly dissipates once it's spread about
  half the screen's width, rather than fading on a fixed timer
  regardless of size. Verified numerically: the ripple is fully faded
  by ~0.9s via the distance falloff, well inside the old 4s duration.

## v24 — 2026-07-22 — Scene 3: smoother/subtler pulse, restored autonomous droplets

- **Smoothed several sources of "pulse" in scene 3**: the shared
  camera's zoom punch (from drum hits) is now damped to 40% of its
  previous influence here; the ripple ring itself is wider/softer and
  dimmer (0.7 -> 0.4 weight); the "drums" channel's brightness CC now
  swings a much narrower 0.75-1.25 range instead of 0.5-1.5.
- **Restored autonomous droplets/ripples** that pop in on their own at
  random screen positions on a random timer (independent of any MIDI
  input), reusing the same (now subtler) ripple rendering — ambient
  background life even with no input.

## v23 — 2026-07-22 — Thinner hollow logo outline

- **Reduced `OUTLINE_THICKNESS`** in `hollow_logo.py` by 30% (0.012 ->
  0.0084) per feedback that the outline on scenes 1-3 read too thick.

## v22 — 2026-07-22 — White hollow-outline logo added to scenes 1-3

- **Factored out shared `video_texture.py`** — the video-frame-streaming
  logic (open capture, decode/resize frames, advance at native
  playback speed) was duplicated across scenes 5 and 6; now shared by
  all five scenes that use the video.
- **New `hollow_logo.py`**: a centered, white OUTLINE-ONLY rendering of
  the spin-loop video logo (edges only, not filled) — samples a binary
  inside/outside mask at each pixel plus a ring of samples around it at
  a small radius; if any disagree with the center, that pixel is near a
  boundary and drawn white, everything else discarded. Verified
  numerically on an actual video frame that this produces a thin,
  non-degenerate boundary (not solid, not empty).
- **Added to scenes 1-3** (`particle_burst`, `feedback_trails`,
  `noise_field`) as a final overlay pass on top of each scene's own
  content — kept deliberately simple (flat, centered, no 3D tilt),
  unlike the full solid/3D treatment in scenes 4 and 5, so it doesn't
  compete with what's already a busy scene. Outline thickness and
  display size are tunable constants in `hollow_logo.py`.

## v21 — 2026-07-22 — Fixed a second, distinct bug: rotation made all characters vanish

- **The v20 fix introduced a real regression**: `theta_center` is
  computed in the ring's ROTATED frame (`u_rotation` already added into
  `angle` before this point), but was then used directly to place
  `slot_center_pos` in raw screen space — a mismatch that grows with
  `u_rotation` and, once the ring is spinning at all, pushes every
  character's valid sampling region outside [0,1] simultaneously. That
  produced exactly what was reported: characters completely gone.
  Traced to the exact line via direct numeric tracing (not guessing) —
  confirmed valid pixel coverage dropped to exactly zero the moment
  rotation was nonzero, at every tested resolution.
- **Fixed by converting back to the screen-space angle**
  (`theta_center - u_rotation`) before using it for position/
  decomposition. Verified numerically: valid coverage now stays
  constant (~12.9%) across rotation values from -10 to +6.5, and the
  v20 mirroring fix still holds correctly in combination with this
  (re-ran the upright/orientation check across 4 rotation values × 12
  angles = 48 cases, all passing).

## v20 — 2026-07-22 — Actually found and fixed the ring-text mirroring root cause

- **Root cause identified via rigorous numeric verification** (built a
  synthetic reference texture with known left/right and top/bottom
  markers, and tested exact coordinate math point-by-point — not just
  guessing signs): the ring-text mapping was taking (angle, radius)
  offsets straight to (glyph_uv.x, glyph_uv.y) without ever rotating
  into each slot's own tangent frame. That's only a valid approximation
  directly at the top of the ring, where the tangent happens to align
  with the screen's x-axis — at every other position around the ring
  it's an increasingly transposed mapping, and a coordinate transpose
  is mathematically a reflection. That's what was producing the
  mirroring, and why it persisted across multiple sign-flip attempts
  that were treating the symptom rather than this cause.
- **Fixed by properly decomposing each slot's local offset into genuine
  radial (outward) and tangential (reading-direction) components via
  an actual rotation matrix**, then mapping those (not raw angle/radius)
  to the glyph's texture coordinates. Verified correct at 24 angles
  spaced around the full circle, combined with multiple ring-rotation
  values, using exact deterministic point-sampling (not statistical
  correlation, which turned out to give misleading results for
  off-axis slots during earlier verification attempts).

## v19 — 2026-07-21 — Scene 7 removed

- **Removed `hollow_chars_pulse.py`** (scene 7) and its asset
  (`assets/hollow_chars.png`) entirely, along with all registrations
  in `config.py`, `scene_manager.py`, and `main.py`. Back to 6 scenes
  (program-change 0-5). The hollow-character identification from v18
  wasn't confirmed as correct before being asked to remove it.

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

## v18 — 2026-07-21 — Fixed horizontally mirrored ring characters

- **Scene 6 — fixed character mirroring.** The "unwrap text around a
  circle" technique mapped the angular sweep direction straight to the
  glyph texture's horizontal coordinate — this is equivalent to
  wrapping a printed strip around a cylinder with the printed side
  facing inward instead of outward, so every character came out
  mirrored left-right from the normal outside viewpoint. Fixed by
  flipping the within-slot horizontal sampling direction; which slot
  each character occupies (and the MIDI-clock pop-chase ordering) is
  unaffected — only the read direction within each character's own
  glyph changed.

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
