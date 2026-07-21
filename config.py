"""
config.py
---------
All MIDI mapping lives here. If you want to change what a knob or key does,
this is almost always the only file you need to touch.

HOW MIDI WORKS IN THIS PROJECT (quick primer):
- A MIDI "note" message fires once when a key/pad is pressed (note on) and
  once when released (note off). We use notes as TRIGGERS (e.g. "burst a
  new wave of particles").
- A MIDI "CC" (control change) message is a knob/fader/mod-wheel. It sends
  a continuous stream of values from 0-127 as you move it. We use CCs for
  CONTINUOUS control (e.g. "color hue" or "particle speed").
- A MIDI "program change" message is normally used to switch instrument
  patches. We repurpose it here to switch VISUAL SCENES, so you (or
  someone else in the collective) can flip through the set list live.

WINDOW / OUTPUT SETTINGS
"""

# --- Window / output -------------------------------------------------------
# WINDOW_WIDTH/HEIGHT are only used in windowed mode (FULLSCREEN=False),
# e.g. for testing on your laptop screen. In fullscreen mode, the window
# automatically uses whatever resolution and refresh rate the connected
# display/projector reports as its native mode — including 4K, if that's
# what it is — so you don't need to hardcode a target resolution here.
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
WINDOW_TITLE = "Oca Collective — Visuals"
FULLSCREEN = False  # set True for showtime on the projector/output screen
TARGET_FPS = 60

# A note on 4K performance: the shader work (noise, the Julia-set
# fractal, particle rendering) scales with pixel count, and 4K has
# ~9x the pixels of 720p. On a discrete GPU or Apple Silicon this is
# generally very manageable for what this project draws — but if you
# see dropped frames at 4K on older/integrated graphics, the simplest
# fix is running at your display's next resolution down, or lowering
# MAX_ITER in the fractal shaders (search for "MAX_ITER" in
# scenes/logo_pulse.py). The particle/feedback "work_size" framebuffers
# used internally by a few scenes are already fixed at 1280x720
# regardless of output resolution, which keeps their cost constant.

# --- MIDI input --------------------------------------------------------
# Leave as None to auto-select (the app will print available ports on
# startup and you can paste the exact name here once you know it).
MIDI_PORT_NAME = None  # e.g. "IAC Driver Bus 1" (Ableton) or "SEQTRAK"

# Set to True to print every incoming MIDI message (type, channel, note
# /control, value) to the terminal. Useful for confirming that your gear
# is actually sending what you expect on the channels you expect — e.g.
# if a channel-triggered effect "isn't working," turn this on, hit the
# pad in question, and check the printed channel number matches what
# CHANNEL_ROLES expects. Leave off during a show (it's noisy and adds
# print overhead).
MIDI_DEBUG = False

# --- CC mappings -------------------------------------------------------
# Maps a MIDI CC number -> a named control that scenes read from.
# CC 1 is the standard mod wheel; CC 74 is a common filter-cutoff CC on
# many controllers/DAW templates (including Ableton's default macros).
# Feel free to remap these numbers to whatever you route from Ableton or
# the SEQTRAK.
CC_MAP = {
    1: "color_shift",     # mod wheel -> hue rotation
    74: "intensity",      # filter cutoff -> speed / spread / brightness
    71: "feedback_amount",  # resonance -> trail smear amount
    7: "master_brightness",  # channel volume -> overall brightness
}

# --- Channel routing -----------------------------------------------------
# Assigns a human-readable role to each MIDI channel, so scenes can ask
# for "the drums channel" instead of remembering a number. Displayed
# channel numbers in Ableton/most gear are 1-16; here they're 0-indexed
# (0 = "channel 1" on your controller/DAW).
#
# This matches the Yamaha SEQTRAK's fixed channel layout:
#   Ch 1  Kick            Ch 7  Percussion 2
#   Ch 2  Snare           Ch 8  Bass/Synth 1
#   Ch 3  Snare 2 / Clap  Ch 9  Synth 2
#   Ch 4  Hi-hat 1        Ch 10 Pads/DX
#   Ch 5  Hi-hat 2        Ch 11 Sampler
#   Ch 6  Percussion 1
#
# A role can map to a single channel OR a list of channels. "drums" and
# "percussion" below are two separate groupings — "drums" covers just
# kick/snare/snare2 (channels 1-3), while "percussion" covers the
# hi-hats and other percussion (channels 4-7) as its own mapping, so
# scenes can react differently to "drums" hits vs "percussion" hits. If
# routing Ableton instead, just send each instrument out on the matching
# channel number for the same behavior.
CHANNEL_ROLES = {
    # Individual channels, in case you want finer per-instrument control
    # in a scene later (not required by the current scenes).
    "kick": 0,
    "snare": [1, 2],       # Snare + Snare 2/Clap
    "hihat": [3, 4],       # Hi-hat 1 + 2
    "perc": [5, 6],        # Percussion 1 + 2
    "bass": 7,             # Bass/Synth 1
    "synth2": 8,
    "pads": 9,             # Pads/DX
    "sampler": 10,

    # Broader groupings the current scenes actually read from:
    "drums": [0, 1, 2],       # channels 1-3 (kick, snare, snare2/clap) -> big bursts / pulses
    "percussion": [3, 4, 5, 6],  # channels 4-7 (hi-hat 1+2, perc 1+2) -> its own mapping, kept separate from "drums"
    "keys": [8, 9],                   # Synth 2 + Pads/DX -> color
    "texture": [10],                  # Sampler -> ambient twinkles/ripples
}

# --- Note mappings -------------------------------------------------------
# Which notes act as "burst" triggers inside scenes. Using a full octave
# starting at C1 (MIDI note 36) is a common convention for drum racks /
# pads in Ableton, and matches SEQTRAK's pattern trigger pads too.
TRIGGER_NOTE_LOW = 36
TRIGGER_NOTE_HIGH = 51  # 16 pads, C1..D#2

# --- Scene switching (Program Change) -----------------------------------
# Program change value -> scene name. Extend this as you add scenes.
SCENE_PROGRAM_MAP = {
    0: "particle_burst",
    1: "feedback_trails",
    2: "noise_field",
    3: "logo_pulse",
    4: "logo_video_pulse",
}

# How long a crossfade between scenes takes, in seconds.
CROSSFADE_DURATION = 2.0

# Default scene on startup (by name, must exist in SCENE_PROGRAM_MAP values)
DEFAULT_SCENE = "particle_burst"
