"""
midi_input.py
-------------
Wraps `mido` + `python-rtmidi` to read live MIDI from Ableton Live (via a
virtual MIDI port like IAC Driver) and/or the Yamaha SEQTRAK (which shows
up as a normal USB MIDI device on macOS, no extra drivers needed).

Everything gets funneled into one `MidiState` object each frame, which is
what scenes actually read from.

PER-CHANNEL ROUTING
--------------------
Every MIDI message carries a channel number (1-16 in Ableton/hardware
displays, 0-15 internally — mido and this file use the 0-indexed form).
This lets you assign different musical elements to different channels
and have each one drive a genuinely different visual response — e.g.
a drum track on channel 1 triggers big particle bursts, while a pad
track on channel 3 slowly shifts color.

In Ableton, set each MIDI track's output channel under the track's
output routing (Ch. 1, Ch. 2, etc.) — all tracks can still share the
same IAC output port. On the SEQTRAK, each part (drum/bass/synth/etc)
can be set to transmit on a different MIDI channel in its MIDI settings.

`config.CHANNEL_ROLES` maps a human-readable role name ("drums", "bass",
...) to a channel number, so scene code can say
`midi.role_triggers("drums")` instead of remembering magic numbers.
"""

import mido
from config import CC_MAP, MIDI_PORT_NAME, CHANNEL_ROLES, MIDI_DEBUG

NUM_CHANNELS = 16


class MidiState:
    """Holds the current, continuously-updated state of all MIDI input.

    Attributes:
        cc (dict[str, float]): named CC values, normalized 0.0-1.0,
            aggregated across all channels (last message wins). Kept for
            scenes/backwards-compatibility that don't care which channel.
        note_triggers (set[int]): note numbers that received a "note on"
            THIS FRAME ONLY, aggregated across all channels.
        active_notes (set[int]): notes currently held down, aggregated.
        program_change (int | None): set the frame a program change
            message arrives, otherwise None. Cleared after being read.
        channel_cc (dict[int, dict[str, float]]): per-channel CC values.
        channel_note_triggers (dict[int, set[int]]): per-channel note-on
            events fired THIS FRAME ONLY.
        channel_active_notes (dict[int, set[int]]): per-channel held notes.
    """

    def __init__(self):
        self.cc = {name: 0.0 for name in CC_MAP.values()}
        self.note_triggers = set()
        self.active_notes = set()
        self.program_change = None

        self.channel_cc = {ch: {} for ch in range(NUM_CHANNELS)}
        self.channel_note_triggers = {ch: set() for ch in range(NUM_CHANNELS)}
        self.channel_active_notes = {ch: set() for ch in range(NUM_CHANNELS)}

    def begin_frame(self):
        """Call once per frame BEFORE polling MIDI, to clear one-shot events."""
        self.note_triggers = set()
        self.program_change = None
        for ch in range(NUM_CHANNELS):
            self.channel_note_triggers[ch] = set()

    def _channels_for(self, role):
        """Normalizes config.CHANNEL_ROLES entries to a list of channels.

        A role can map to a single channel (int) or a list of channels
        (e.g. "drums" covering kick + snare + hi-hats + perc together).
        """
        ch = CHANNEL_ROLES.get(role)
        if ch is None:
            return []
        if isinstance(ch, int):
            return [ch]
        return list(ch)

    def role_cc(self, role, name, default=0.0):
        """Named CC value for a given role (see config.CHANNEL_ROLES).

        Checks each channel mapped to the role in order and returns the
        first one that has received this CC; falls back to the
        aggregated global value, then `default`.
        """
        channels = self._channels_for(role)
        if not channels:
            return self.cc.get(name, default)
        for ch in channels:
            if name in self.channel_cc[ch]:
                return self.channel_cc[ch][name]
        return self.cc.get(name, default)

    def role_triggers(self, role):
        """Set of notes triggered THIS FRAME across all channels mapped to `role`."""
        triggers = set()
        for ch in self._channels_for(role):
            triggers |= self.channel_note_triggers[ch]
        return triggers

    def role_active_notes(self, role):
        """Set of notes currently held across all channels mapped to `role`."""
        notes = set()
        for ch in self._channels_for(role):
            notes |= self.channel_active_notes[ch]
        return notes


def list_available_ports():
    """Prints all MIDI input ports currently visible to the OS.

    Handy for finding the exact name to put in config.MIDI_PORT_NAME.
    """
    ports = mido.get_input_names()
    print("Available MIDI input ports:")
    if not ports:
        print("  (none found — check your MIDI device / IAC driver is on)")
    for p in ports:
        print(f"  - {p}")
    return ports


def open_midi_port(state: MidiState):
    """Opens a MIDI input port and returns it, or None if none available.

    The returned port is non-blocking; call `poll_midi(port, state)` each
    frame in your main loop to drain any pending messages into `state`.
    """
    ports = list_available_ports()
    port_name = MIDI_PORT_NAME

    if port_name is None:
        if not ports:
            print("No MIDI ports found. Running with no MIDI input for now.")
            return None
        port_name = ports[0]
        print(f"MIDI_PORT_NAME not set in config.py — defaulting to '{port_name}'")

    try:
        port = mido.open_input(port_name)
        print(f"Opened MIDI port: {port_name}")
        return port
    except (IOError, OSError) as e:
        print(f"Could not open MIDI port '{port_name}': {e}")
        return None


def poll_midi(port, state: MidiState):
    """Drains all pending MIDI messages from `port` into `state`.

    Call this once per frame, right after `state.begin_frame()`.
    Safe to call with `port=None` (does nothing).
    """
    if port is None:
        return

    for msg in port.iter_pending():
        ch = getattr(msg, "channel", None)  # 0-15, or None for sysex/etc.

        if MIDI_DEBUG:
            ch_display = ch + 1 if ch is not None else "-"  # show as 1-16, matching gear displays
            print(f"[MIDI] type={msg.type} channel={ch_display} {msg}")

        if msg.type == "control_change":
            if msg.control in CC_MAP:
                name = CC_MAP[msg.control]
                value = msg.value / 127.0
                state.cc[name] = value
                if ch is not None:
                    state.channel_cc[ch][name] = value

        elif msg.type == "note_on" and msg.velocity > 0:
            # Any note-on is a valid trigger — which channel it arrives on
            # (not which note number) is what determines its role. The
            # note number itself is still useful data (e.g. mapping pitch
            # to screen position), just not a filter for "did this count".
            state.note_triggers.add(msg.note)
            if ch is not None:
                state.channel_note_triggers[ch].add(msg.note)
            state.active_notes.add(msg.note)
            if ch is not None:
                state.channel_active_notes[ch].add(msg.note)

        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            state.active_notes.discard(msg.note)
            if ch is not None:
                state.channel_active_notes[ch].discard(msg.note)

        elif msg.type == "program_change":
            state.program_change = msg.program
