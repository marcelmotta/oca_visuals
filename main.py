"""
main.py
-------
Run this file to start the show:

    python main.py

It opens one window (single-screen output for now, as agreed), reads
live MIDI from Ableton Live and/or the SEQTRAK, and renders whichever
scene is currently active — crossfading smoothly whenever a MIDI
program-change message asks for a different one.

MIDI devices can be plugged in at any time, including after the app is
already running — it retries opening a port every few seconds in the
background if none is connected yet (or if one disconnects mid-show).

CONTROLS WHILE RUNNING:
- Press ESC or close the window to quit.
- Press number keys 1/2/3 to manually switch scenes for testing, even
  with no MIDI device connected yet.
- The mouse cursor auto-hides after a couple seconds of no movement
  (like a video player) and reappears instantly on any movement — see
  CURSOR_IDLE_HIDE_SECONDS in config.py to change the delay or disable.
"""

import time
import glfw
import moderngl

from config import (
    WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_TITLE, FULLSCREEN, TARGET_FPS,
    CURSOR_IDLE_HIDE_SECONDS,
)
from midi_input import MidiState, open_midi_port, poll_midi
from scene_manager import SceneManager
from camera import Camera


def create_window():
    if not glfw.init():
        raise RuntimeError("Could not initialize GLFW")

    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)

    if FULLSCREEN:
        # Use the display's own native resolution and refresh rate
        # (whatever that is — 1080p, 4K, etc.) rather than a hardcoded
        # size, so the output always fills the screen/projector at its
        # correct aspect ratio. This also means 4K "just works" if
        # that's what the connected display reports, with no extra
        # config needed.
        monitor = glfw.get_primary_monitor()
        video_mode = glfw.get_video_mode(monitor)
        width, height = video_mode.size.width, video_mode.size.height
        glfw.window_hint(glfw.REFRESH_RATE, video_mode.refresh_rate)
        print(f"Fullscreen: using display's native {width}x{height} "
              f"@ {video_mode.refresh_rate}Hz")
    else:
        monitor = None
        width, height = WINDOW_WIDTH, WINDOW_HEIGHT

    window = glfw.create_window(width, height, WINDOW_TITLE, monitor, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("Could not create GLFW window")

    glfw.make_context_current(window)
    glfw.swap_interval(1)  # vsync on, keeps us near TARGET_FPS without spinning
    return window


def main():
    window = create_window()
    ctx = moderngl.create_context()

    fb_width, fb_height = glfw.get_framebuffer_size(window)
    ctx.viewport = (0, 0, fb_width, fb_height)

    scene_manager = SceneManager(ctx, fb_width, fb_height)
    camera = Camera()

    midi_state = MidiState()
    midi_port = open_midi_port(midi_state)

    # Manual scene-switch keys for testing without a MIDI controller.
    key_to_program = {glfw.KEY_1: 0, glfw.KEY_2: 1, glfw.KEY_3: 2, glfw.KEY_4: 3,
                       glfw.KEY_5: 4, glfw.KEY_6: 5}

    def key_callback(_window, key, _scancode, action, _mods):
        if action != glfw.PRESS:
            return
        if key == glfw.KEY_ESCAPE:
            glfw.set_window_should_close(window, True)
        elif key in key_to_program:
            scene_manager.handle_program_change(key_to_program[key])

    glfw.set_key_callback(window, key_callback)

    # IMPORTANT: without this, if the window changes size any way OTHER
    # than our own startup fullscreen path — dragging an edge, using the
    # OS's native maximize/fullscreen button, an external display change
    # — the app keeps rendering at whatever size it started at, and
    # GLFW/the OS just stretches those old pixels to fit the new window
    # bounds. That's exactly what "stuck at the original aspect ratio"
    # looks like. This callback keeps the GL viewport and the scene
    # manager's internal buffers (and therefore anything reading
    # target.size, like the logo scenes' aspect ratio) in sync with
    # whatever the actual current size is, at all times.
    def framebuffer_size_callback(_window, width, height):
        if width > 0 and height > 0:
            ctx.viewport = (0, 0, width, height)
            scene_manager.resize(width, height)

    glfw.set_framebuffer_size_callback(window, framebuffer_size_callback)

    # Cursor auto-hide: like a video player or any other fullscreen
    # visual app, the mouse pointer shouldn't just sit on screen forever
    # once you stop moving it. Any mouse movement resets the idle timer
    # and instantly shows the cursor again; it hides itself after
    # CURSOR_IDLE_HIDE_SECONDS of no movement. Set that to None in
    # config.py to disable this and always show the cursor.
    cursor_state = {"last_move_time": time.perf_counter(), "hidden": False}

    def cursor_pos_callback(_window, _x, _y):
        cursor_state["last_move_time"] = time.perf_counter()
        if cursor_state["hidden"]:
            glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_NORMAL)
            cursor_state["hidden"] = False

    if CURSOR_IDLE_HIDE_SECONDS is not None:
        glfw.set_cursor_pos_callback(window, cursor_pos_callback)

    last_time = time.perf_counter()
    print("Running. Press ESC to quit, or 1/2/3/4/5/6 to switch scenes manually.")

    # MIDI hot-plug: if no device was connected at startup (or one gets
    # unplugged mid-show), retry opening a port every few seconds rather
    # than only checking once at launch. This is a cheap check (just
    # asking the OS for the current port list) done every few seconds,
    # not every frame, so the added CPU cost is negligible.
    MIDI_RECONNECT_INTERVAL = 3.0
    midi_reconnect_timer = 0.0

    while not glfw.window_should_close(window):
        glfw.poll_events()

        now = time.perf_counter()
        dt = now - last_time
        last_time = now
        # Clamp dt so a debugger breakpoint or hiccup doesn't cause a huge
        # simulation jump (e.g. a particle burst teleporting off-screen).
        dt = min(dt, 1.0 / 15.0)

        midi_state.begin_frame()
        midi_ok = poll_midi(midi_port, midi_state)
        if not midi_ok:
            print("MIDI port disconnected — will keep retrying in the background.")
            midi_port = None

        if midi_port is None:
            midi_reconnect_timer += dt
            if midi_reconnect_timer >= MIDI_RECONNECT_INTERVAL:
                midi_reconnect_timer = 0.0
                midi_port = open_midi_port(midi_state, quiet=True)

        camera.update(dt, midi_state)

        if CURSOR_IDLE_HIDE_SECONDS is not None and not cursor_state["hidden"]:
            if now - cursor_state["last_move_time"] >= CURSOR_IDLE_HIDE_SECONDS:
                glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_HIDDEN)
                cursor_state["hidden"] = True

        ctx.screen.use()
        # Re-assert the viewport every frame: binding other framebuffers
        # during a scene's render (trail buffers, crossfade targets,
        # etc.) can change moderngl's tracked viewport, so we make sure
        # it's correct again right before drawing to the actual screen.
        ctx.viewport = (0, 0, *glfw.get_framebuffer_size(window))
        ctx.clear(0.0, 0.0, 0.0, 1.0)
        scene_manager.update_and_render(dt, midi_state, camera, ctx.screen)

        glfw.swap_buffers(window)

    glfw.terminate()


if __name__ == "__main__":
    main()
