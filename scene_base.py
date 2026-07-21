"""
scene_base.py
-------------
Every visual scene (particle_burst, feedback_trails, noise_field, and any
new ones you add) inherits from `Scene` and implements three methods:

    setup(ctx)        -- called once, build shaders/buffers here
    update(dt, midi)  -- called every frame BEFORE render, update state
    render(target)    -- called every frame, draw into `target` framebuffer

This shared shape is what lets scene_manager.py treat every scene
identically, and lets you drop in a brand new scene file without touching
anything else in the project.
"""

from abc import ABC, abstractmethod


class Scene(ABC):
    name = "unnamed_scene"

    def __init__(self, ctx):
        """`ctx` is the shared ModernGL context (moderngl.Context)."""
        self.ctx = ctx
        self.setup(ctx)

    @abstractmethod
    def setup(self, ctx):
        """One-time setup: compile shaders, allocate buffers/textures."""
        raise NotImplementedError

    @abstractmethod
    def update(self, dt, midi, camera):
        """Advance simulation state.

        Args:
            dt (float): seconds since last frame.
            midi (midi_input.MidiState): current MIDI state. Read
                midi.role_cc(...)/midi.role_triggers(...) for per-channel
                values (see config.CHANNEL_ROLES).
            camera (camera.Camera): shared virtual camera. Read
                camera.offset/.zoom/.rotation/.punch (usually via
                camera.layer_params(parallax) for a specific depth
                layer) and store what you need on `self` here — render()
                should just use the values you computed.
        """
        raise NotImplementedError

    @abstractmethod
    def render(self, target):
        """Draw the scene into `target`, a moderngl.Framebuffer.

        Scenes should NOT clear the default framebuffer themselves in a
        way that assumes they own the whole screen forever — the scene
        manager handles clearing/compositing/crossfades. Just render your
        content into `target`.
        """
        raise NotImplementedError

    def teardown(self):
        """Optional: override to release any extra GPU resources."""
        pass
