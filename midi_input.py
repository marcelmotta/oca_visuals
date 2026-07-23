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

MIDI CLOCK
----------
Separately from notes/CC/channels, this also tracks MIDI Clock — the
standard real-time sync signal (24 pulses per quarter note) that
Ableton and most sequencers/grooveboxes can transmit. This is NOT sent
by default — you need to explicitly enable clock/sync output on the
relevant port (in Ableton: Preferences > Link/Tempo/MIDI > turn on
"Sync" output for the port; on hardware, look for a "MIDI clock out" or
"sync out" setting). `MidiState.triplet_tick_pending` fires once every
8 clock pulses (24/3 — a musical triplet subdivision of the beat),
which scenes can use to time sequential per-step animations to the
actual tempo rather than a hardcoded speed.
"""

import mido
from config import CC_MAP, MIDI_PORT_NAME, CHANNEL_ROLES, MIDI_DEBUG

NUM_CHANNELS = 16
CLOCK_PULSES_PER_QUARTER_NOTE = 24
CLOCK_PULSES_PER_TRIPLET = CLOCK_PULSES_PER_QUARTER_NOTE // 3  # = 8

MIDI_QUIET_TIMEOUT = 0.4  # seconds of silence before recently_active() flips off


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
        message_received_this_frame (bool): True for exactly one frame
            whenever a channel-based MIDI message (note, CC, program
            change — not channel-less messages like clock) arrived
            during that frame. Feeds `advance_activity_clock()` below,
            which turns it into a rolling "has MIDI been active
            recently" signal — a momentary flag, not a permanent latch,
            so it can toggle on and off repeatedly as playing starts and
            stops.
        seconds_since_message (float): seconds elapsed since the last
            channel-based MIDI message, advanced once per frame by
            `advance_activity_clock()` regardless of which scene is
            active — a genuine app-wide clock, not a per-scene one (a
            scene's own elapsed time only advances while it's the one
            being shown). This is what `recently_active()` reads.

    ONE SHARED "IS MIDI ACTIVE" SIGNAL
    -----------------------------------
    Several scenes/helpers need to know "has real MIDI activity happened
    recently" (e.g. to freeze the shared spin-loop video on MIDI-quiet,
    or gate a per-scene animation) — rather than each reimplementing its
    own last-message-time bookkeeping, they all call `recently_active()`
    here. This is the one place that logic lives, for every current and
    future scene.
    """

    def __init__(self):
        self.cc = {name: 0.0 for name in CC_MAP.values()}
        self.note_triggers = set()
        self.active_notes = set()
        self.program_change = None
        self.message_received_this_frame = False
        # No message has ever arrived yet, so nothing should read as
        # "recently active" before the first one does.
        self.seconds_since_message = float("inf")

        self.channel_cc = {ch: {} for ch in range(NUM_CHANNELS)}
        self.channel_note_triggers = {ch: set() for ch in range(NUM_CHANNELS)}
        self.channel_active_notes = {ch: set() for ch in range(NUM_CHANNELS)}

        self.clock_pulse_count = 0
        self.triplet_tick_pending = False

    def advance_activity_clock(self, dt):
        """Call once per frame, after poll_midi(), regardless of which
        scene is currently active."""
        if self.message_received_this_frame:
            self.seconds_since_message = 0.0
        else:
            self.seconds_since_message += dt

    def recently_active(self, timeout=MIDI_QUIET_TIMEOUT):
        """True if a channel-based MIDI message arrived within the last
        `timeout` seconds."""
        return self.seconds_since_message < timeout

    def begin_frame(self):
        """Call once per frame BEFORE polling MIDI, to clear one-shot events."""
        self.note_triggers = set()
        self.program_change = None
        self.triplet_tick_pending = False
        self.message_received_this_frame = False
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


def list_available_ports(quiet=False):
    """Prints all MIDI input ports currently visible to the OS.

    Handy for finding the exact name to put in config.MIDI_PORT_NAME.
    Pass quiet=True to skip printing (used for periodic hot-plug retries
    so they don't spam the console every couple seconds).
    """
    ports = mido.get_input_names()
    if not quiet:
        print("Available MIDI input ports:")
        if not ports:
            print("  (none found — check your MIDI device / IAC driver is on)")
        for p in ports:
            print(f"  - {p}")
    return ports


def open_midi_port(state: MidiState, quiet=False):
    """Opens a MIDI input port and returns it, or None if none available.

    The returned port is non-blocking; call `poll_midi(port, state)` each
    frame in your main loop to drain any pending messages into `state`.
    Pass quiet=True to suppress the "no ports found" style messages —
    used for periodic hot-plug retries once the show is already running.
    """
    ports = list_available_ports(quiet=quiet)
    port_name = MIDI_PORT_NAME

    if port_name is None:
        if not ports:
            if not quiet:
                print("No MIDI ports found. Running with no MIDI input for now.")
            return None
        port_name = ports[0]
        if not quiet:
            print(f"MIDI_PORT_NAME not set in config.py — defaulting to '{port_name}'")

    try:
        port = mido.open_input(port_name)
        print(f"Opened MIDI port: {port_name}")  # always announce success, even when quiet
        return port
    except (IOError, OSError) as e:
        if not quiet:
            print(f"Could not open MIDI port '{port_name}': {e}")
        return None


def poll_midi(port, state: MidiState):
    """Drains all pending MIDI messages from `port` into `state`.

    Call this once per frame, right after `state.begin_frame()`.
    Safe to call with `port=None` (does nothing).

    Returns True if the port is still OK, False if it just disconnected
    (e.g. the device was unplugged) — the caller should discard the
    port and treat it as None from then on, so hot-plug reconnection
    logic (see main.py) will pick it back up automatically once it's
    plugged back in.
    """
    if port is None:
        return True

    try:
        pending = list(port.iter_pending())
    except (IOError, OSError):
        return False

    for msg in pending:
        ch = getattr(msg, "channel", None)  # 0-15, or None for sysex/etc.

        # Flags THIS FRAME as having real MIDI activity (note, CC,
        # program change — not clock/other channel-less system
        # messages, since "from any of the channels" implies an actual
        # channel). main.py turns this into a rolling recent-activity
        # timeout that can toggle on/off repeatedly, not a one-way latch.
        if ch is not None:
            state.message_received_this_frame = True

        if MIDI_DEBUG and msg.type != "clock":
            ch_display = ch + 1 if ch is not None else "-"  # show as 1-16, matching gear displays
            print(f"[MIDI] type={msg.type} channel={ch_display} {msg}")

        if msg.type == "clock":
            state.clock_pulse_count += 1
            if state.clock_pulse_count % CLOCK_PULSES_PER_TRIPLET == 0:
                state.triplet_tick_pending = True

        elif msg.type == "control_change":
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

    return True
