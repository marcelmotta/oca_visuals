# Oca Collective — Visuals

A code-based, MIDI-reactive visual rig for live performance, built in
Python + ModernGL (OpenGL). Six modular scenes so far, switchable live
via MIDI program change, with smooth crossfades between them.

## 1. Install (macOS)

You need Python 3.10+ (check with `python3 --version`; install via
`brew install python` if needed), then:

```bash
cd oca_visuals
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Set up MIDI

**From Ableton Live 12:**
1. Open **Audio MIDI Setup** (Spotlight search it) → Window → Show MIDI
   Studio → double-click **IAC Driver** → check "Device is online" →
   confirm a port exists (default "Bus 1").
2. In Ableton: Preferences → Link/Tempo/MIDI → under MIDI Ports, turn on
   **Track** output for "IAC Driver (Bus 1)".
3. On a MIDI track, set its output to IAC Driver (Bus 1). Anything you
   play/sequence on that track now reaches this app.

**From the Yamaha SEQTRAK:** just plug it in via USB — it appears as a
class-compliant MIDI device automatically, no drivers needed.

**Finding the exact port name:** run the app once (`python3 main.py`) —
it prints all available MIDI ports to the terminal on startup. Copy the
exact name into `MIDI_PORT_NAME` in `config.py`.

## 3. Run it

```bash
python3 main.py
```

- **ESC** quits.
- **1-6** keys manually switch scenes (for testing without a MIDI
  controller connected).
- The mouse cursor auto-hides after ~2 seconds of no movement (like a
  video player) and reappears instantly on any movement — see
  `CURSOR_IDLE_HIDE_SECONDS` in `config.py` to change the delay or
  disable it entirely.
- MIDI-awareness for animation is handled per-scene rather than as a
  global freeze (an earlier global "freeze everything until MIDI
  arrives" attempt didn't work well and was removed) — with one
  exception: whether MIDI has been active "recently" is tracked in ONE
  shared place, `MidiState.recently_active()` (`midi_input.py`), driven
  by a genuine app-wide clock in `main.py`'s main loop rather than any
  single scene's own elapsed time. Every current (and future) scene or
  helper that needs to know "is MIDI active right now" reads from this
  same signal instead of reimplementing its own timeout.
  - **The spin-loop video's own playback** (the logo's rotation, baked
    into the footage itself, not a transform any scene applies) is
    gated on this signal via the shared `VideoTexture` helper
    (`video_texture.py`), used by all 6 scenes that display this
    footage. It starts held on the video's first frame and doesn't
    begin looping at all until MIDI is first received; once playing, it
    loops normally, and if MIDI goes quiet it lets the CURRENT loop
    finish playing to its last frame rather than cutting it off,
    holding there until MIDI activity returns, at which point it
    resumes from the start. This is independent of any other animation
    layered on top of the footage — e.g. scene 4's 3D plane tilt/bounce
    and scene 5's own kaleidoscope rotation keep running at all times
    regardless of MIDI.
  - Scene 5's sequential character-pop chase similarly only advances
    while MIDI is recently active, not just whenever MIDI Clock happens
    to be ticking (see `kaleidoscope_video.py`).
- Once MIDI is connected: notes in the C1–D#2 range (36–51) trigger
  bursts/pulses depending on the active scene; CC1, CC74, CC71, CC7
  control color/intensity/trail-length/brightness; program-change
  messages (0-5) switch scenes with a 2-second crossfade.

### Per-channel routing

Different MIDI channels drive different behavior — matches the Yamaha
SEQTRAK's fixed channel layout (see `CHANNEL_ROLES` in `config.py` if
routing from Ableton instead, or to remap):

| SEQTRAK channel | Instrument | Role | Drives |
|---|---|---|---|
| 1–3 | Kick, Snare, Snare2/Clap | `drums` | Big particle bursts / bright pulses (scenes 1-3); logo/video scenes' shared camera "punch" and background pixel-cloud |
| 4–7 | Hi-hat 1/2, Perc 1/2 | `percussion` | Gentle per-character particle burst in the logo/video scenes (scenes 4-5 only) |
| 8 | Bass/Synth 1 | `bass` | Continuous motion speed, swirl, trail length (via CC) |
| 9–10 | Synth 2, Pads/DX | `keys` | Color / hue, plus soft color-ring bursts. Channel 10 individually (`pads` role) also: blooms scene 2's background kaleidoscopic fractal for as long as a note is held, and glows random triangles of scene 6's ground mesh (smooth attack/release, synced to MIDI clock) on each trigger |
| 11 | Sampler | `texture` | Slow ambient twinkles / ripples |

In Ableton, set each MIDI track's output channel under that track's
routing to match. A role can point at a single channel or a list of
channels (see `drums` and `percussion`, which used to be one combined
mapping and are now deliberately kept separate) — adjust
`CHANNEL_ROLES` directly if you want different groupings.

## 4. Project structure

| File | Purpose |
|---|---|
| `config.py` | All MIDI mappings — edit this first when remapping controls |
| `midi_input.py` | Reads MIDI, exposes a clean `MidiState` object |
| `scene_base.py` | The interface every scene follows |
| `scene_manager.py` | Switches/crossfades between scenes |
| `main.py` | Window + main loop — what you actually run |
| `camera.py` | Shared virtual camera — automated pan/zoom/rotation driven by MIDI triggers and detected tempo |
| `video_texture.py` | Shared video-frame streaming helper, used by every scene that displays the spin-loop video |
| `hollow_logo.py` | Centered white outline-only logo overlay, used by scenes 1-3 |
| `particle_field.py` | Reusable point-cloud burst effect, embeddable in any scene (used by `kaleidoscope_video.py`) |
| `scenes/particle_burst.py` | House-of-Cards-style point cloud: high density, per-instrument-channel color, erratic fade-out, camera parallax |
| `scenes/feedback_trails.py` | Hollow-outline logo (same as scenes 1 and 3) over a kaleidoscopic folding fractal background (moved here from scene 6). Invisible at rest, blooms (brighter, more saturated, faster rotation/color-cycling) while channel 10 ("pads") has a note held, fading back out on release |
| `scenes/noise_field.py` | Breathing organic noise field: layered bg/fg noise planes, long ripple sustain, camera parallax |
| `scenes/logo_video_pulse.py` | The spin-loop video as a real 3D-projected plane with a subtle glitch effect and a dark contrast outline (so it stays visible against the background even when their colors closely match), over a glowing braid background. The folding-fractal bloom tried on top of the braid this round was pulled back out — see `scenes/logo_video_fractal.py` |
| `scenes/kaleidoscope_video.py` | The spin-loop video through a mirrored kaleidoscope, with seigaiha waves, asanoha lattice, drifting sakura petals, a gold mandala ring, and "温泉" characters that pop in sequence around the boundary, timed to MIDI Clock |
| `scenes/logo_video_fractal.py` | A saved checkpoint of scene 4's background experimentation: the same 3D-projected video-plane logo + glitch + contrast outline as scene 4, over a glowing braid, plus a wobbling wireframe ground mesh (jittered/Voronoi-like triangulated grid, real 3D perspective, converging toward the horizon like a pond/ocean surface) filling the bottom of the screen. Every triangle is always filled with a translucent base tint, individually shaded from a real surface normal derived from the wobble height field (actual topography — shadows/highlights — instead of one flat color); channel 10 ("pads") triggers make random triangles glow brighter/more saturated on top of that (quick attack, slow release), synced to MIDI clock, easing back to the base fill when quiet |
| `assets/onsen1.png`, `assets/onsen2.png` | Individual "温" / "泉" glyph textures used by `kaleidoscope_video.py` |
| `assets/oca_spin_loop_v3.mp4` | Source video used by every scene (via `video_texture.py`) |

### What changed in this pass

- **Scene 2 — actual smoothing bug fixed** — the decay factor (e.g.
  0.95) was being applied once per *rendered frame*, not once per
  second. At 60fps that compounds to `0.95^60 ≈ 0.05` remaining after
  one second — a number that looked conservative but was actually
  fading almost everything within a second, which is why it still
  looked choppy and fast despite the earlier change. Fixed: decay is
  now defined as a half-life in seconds (2–7s depending on the "bass"
  channel's `feedback_amount` CC) and converted to the correct per-frame
  factor using the actual elapsed time each frame, so it behaves
  consistently regardless of frame rate. Blur radius also increased and
  both blob orbits are slower.
- **Scenes 4 & 5 — per-character letter bursts** — on top of the
  existing "background pixel-cloud" (kept exactly as it was), both logo
  scenes now spawn a burst on each of the logo's three characters (each
  a different color) whenever a drum-channel trigger fires. Bursts are
  positioned by projecting each character's known position through the
  same 3D camera matrix used to draw the (possibly tilted) logo/video
  plane, so they track the character's actual on-screen position rather
  than a fixed guess. These bursts also dissolve as they approach the
  edge of the screen (a new opt-in `edge_fade` mode in
  `particle_field.py`, off by default so the original background
  pixel-cloud is unaffected).

## 5. Adding a new scene

1. Copy the shape of an existing scene file into `scenes/your_scene.py`,
   implementing `setup`, `update`, and `render` (see `scene_base.py`).
2. Import it in `scene_manager.py` and add it to `SCENE_CLASSES`.
3. Give it a number in `config.SCENE_PROGRAM_MAP`.

No other file needs to change — this is the whole point of the modular
structure, so the collective can keep adding scenes over time without
anyone needing to touch the MIDI or windowing code.

## 6. Version control

This project is tracked with git so any round of changes can be rolled
back. See `CHANGELOG.md` for a plain-language summary of what each
tagged version contains.

```bash
git log --oneline --decorate     # see version history
git describe --tags              # what version am I on right now?
git checkout v1                  # go back to an earlier version
git checkout main                # come back to the latest version
git diff v1 v2                   # see exactly what changed between two versions
```

If you're on an old version (`git checkout v1`) and want to make new
changes from there, run `git checkout -b new-branch-name` first so you
don't lose the newer versions still sitting on `main`.

Going forward, each round of changes will be committed and tagged
(v2, v3, ...) with a matching entry added to `CHANGELOG.md`.

## 7. Debugging MIDI

If a channel-triggered effect doesn't seem to respond, set
`MIDI_DEBUG = True` in `config.py`, run the app, and hit the pad/key in
question — the terminal will print every incoming message's type,
channel (shown as 1-16, matching how gear displays it), and note/CC
value. Compare that channel number against `CHANNEL_ROLES` in
`config.py`. This is the fastest way to confirm whether your
gear/DAW routing is actually sending what a scene expects — e.g. some
grooveboxes/DAW setups need a specific mode enabled to send separate
channels per part rather than everything on one channel.

## 8. Known limitations / next steps

- Currently outputs to a single window (as agreed) — extending to
  multiple screens/projector output later means opening additional GLFW
  windows (or contexts) and rendering different regions per screen; the
  scene/MIDI architecture here doesn't need to change for that.
- Particle counts and framebuffer sizes are tuned for smooth performance
  on a laptop; if you add heavier scenes later, mid-2010s-and-newer
  Apple Silicon or a dedicated GPU will give the most headroom.
- No audio-reactivity (mic/line-in analysis) yet — MIDI-only for now,
  as scoped. Straightforward to add later via a small FFT module feeding
  the same `MidiState`-style interface.
- Scenes 4 & 5 have a rare, brief, subtle random "glitch" (slice-tear +
  chromatic split) on the logo/video plane — see `next_glitch_time` /
  `glitch_active_until` in those files if you want to tune how often or
  how strong it is.
- Fullscreen (`FULLSCREEN = True` in `config.py`) automatically uses
  your display's native resolution and refresh rate — 4K works out of
  the box if that's what the screen/projector reports.
