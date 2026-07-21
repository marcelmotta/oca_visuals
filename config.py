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
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
WINDOW_TITLE = "Oca Collective — Visuals"
FULLSCREEN = False  # set True for showtime on the projector/output screen
TARGET_FPS = 60

# --- MIDI input --------------------------------------------------------
# Leave as None to auto-select (the app will print available ports on
# startup and you can paste the exact name here once you know it).
MIDI_PORT_NAME = None  # e.g. "IAC Driver Bus 1" (Ableton) or "SEQTRAK"

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
# A role can map to a single channel OR a list of channels (e.g. "drums"
# below groups every percussive channel together, so any hit anywhere in
# the kit triggers the same "big reactive hit" behavior). If routing
# Ableton instead, just send each instrument out on the matching channel
# number for the same behavior.
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
    "drums": [0, 1, 2, 3, 4, 5, 6],  # any kit hit -> big bursts / pulses
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
