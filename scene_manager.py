"""
scene_manager.py
-----------------
Owns every Scene instance and decides which one (or two, mid-crossfade)
gets rendered each frame. This is what turns individual scene files into
a structured "set": MIDI program-change messages (e.g. from an Ableton
MIDI clip, or a SEQTRAK pattern button) switch scenes with a smooth
crossfade rather than a hard cut — much better suited to slow, moody
music than a jump cut.

ADDING A NEW SCENE LATER:
1. Write scenes/your_scene.py following scene_base.Scene's interface.
2. Import it below and add it to SCENE_CLASSES.
3. Give it a program-change number in config.SCENE_PROGRAM_MAP.
That's the whole process — nothing else in the project needs to change.
"""

import moderngl

from config import SCENE_PROGRAM_MAP, CROSSFADE_DURATION, DEFAULT_SCENE
from scenes.particle_burst import ParticleBurstScene
from scenes.feedback_trails import FeedbackTrailsScene
from scenes.noise_field import NoiseFieldScene
from scenes.logo_video_pulse import LogoVideoPulseScene
from scenes.kaleidoscope_video import KaleidoscopeVideoScene

SCENE_CLASSES = {
    "particle_burst": ParticleBurstScene,
    "feedback_trails": FeedbackTrailsScene,
    "noise_field": NoiseFieldScene,
    "logo_video_pulse": LogoVideoPulseScene,
    "kaleidoscope_video": KaleidoscopeVideoScene,
}

BLIT_VERTEX = """
#version 330
in vec2 in_position;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

# Blends two textures together by `u_alpha` (0 = only A, 1 = only B).
CROSSFADE_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_tex_a;
uniform sampler2D u_tex_b;
uniform float u_alpha;
void main() {
    vec3 a = texture(u_tex_a, v_uv).rgb;
    vec3 b = texture(u_tex_b, v_uv).rgb;
    f_color = vec4(mix(a, b, u_alpha), 1.0);
}
"""


class SceneManager:
    def __init__(self, ctx, width, height):
        self.ctx = ctx
        self.width = width
        self.height = height

        self.scenes = {name: cls(ctx, width, height) for name, cls in SCENE_CLASSES.items()}

        self.current_name = DEFAULT_SCENE
        self.next_name = None
        self.crossfade_elapsed = 0.0
        self.crossfading = False

        # Each scene renders into its own offscreen buffer so we can blend
        # two scenes together smoothly during a crossfade.
        self.fbo_current = self._make_fbo()
        self.fbo_next = self._make_fbo()

        from utils import make_fullscreen_quad_vao
        self.crossfade_program = ctx.program(
            vertex_shader=BLIT_VERTEX, fragment_shader=CROSSFADE_FRAGMENT
        )
        self.crossfade_vao = make_fullscreen_quad_vao(ctx, self.crossfade_program)

    def _make_fbo(self):
        tex = self.ctx.texture((self.width, self.height), 4)
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        return self.ctx.framebuffer(color_attachments=[tex])

    def resize(self, width, height):
        """Recreates the crossfade buffers at a new size.

        Called whenever the actual window/framebuffer size changes —
        entering/leaving fullscreen, dragging a window edge, or a
        display change — so scenes always render at (and scenes that
        read `target.size`, like the logo scenes' aspect ratio, always
        see) the ACTUAL current output size rather than whatever size
        the app happened to start at.
        """
        if width <= 0 or height <= 0 or (width == self.width and height == self.height):
            return
        self.width = width
        self.height = height
        self.fbo_current = self._make_fbo()
        self.fbo_next = self._make_fbo()
        for scene in self.scenes.values():
            scene.resize(width, height)

    def handle_program_change(self, program_number):
        """Looks up the requested scene and starts a crossfade to it."""
        target_name = SCENE_PROGRAM_MAP.get(program_number)
        if target_name is None or target_name not in self.scenes:
            print(f"Program change {program_number} has no mapped scene.")
            return
        if target_name == self.current_name and not self.crossfading:
            return  # already showing this scene
        self.next_name = target_name
        self.crossfading = True
        self.crossfade_elapsed = 0.0
        print(f"Switching scene: {self.current_name} -> {target_name}")

    def update_and_render(self, dt, midi, camera, screen_fbo, freeze=False):
        """Renders the current (and, mid-crossfade, next) scene.

        `freeze=True` skips calling update() on any scene — render()
        still runs, so whatever was last computed keeps being redrawn as
        a static frame. Used to hold each scene's own animated content
        (particle motion, hue drift, camera reactions, etc.) still until
        MIDI is actually being received (see main.py).

        IMPORTANT: crossfading itself (switching which scene is shown)
        is NEVER gated by `freeze` — manually switching scenes (keys
        1-5) or a MIDI program-change message must always work
        immediately, even with no MIDI signal currently active. Only
        the CONTENT of each scene freezes, never the ability to change
        which scene is on screen.
        """
        if midi.program_change is not None:
            self.handle_program_change(midi.program_change)

        current_scene = self.scenes[self.current_name]
        if not freeze:
            current_scene.update(dt, midi, camera)
        current_scene.render(self.fbo_current)

        if self.crossfading:
            next_scene = self.scenes[self.next_name]
            if not freeze:
                next_scene.update(dt, midi, camera)
            next_scene.render(self.fbo_next)

            self.crossfade_elapsed += dt
            alpha = min(self.crossfade_elapsed / CROSSFADE_DURATION, 1.0)

            screen_fbo.use()
            self.fbo_current.color_attachments[0].use(location=0)
            self.fbo_next.color_attachments[0].use(location=1)
            self.crossfade_program["u_tex_a"] = 0
            self.crossfade_program["u_tex_b"] = 1
            self.crossfade_program["u_alpha"] = alpha
            self.crossfade_vao.render(moderngl.TRIANGLES)

            if alpha >= 1.0:
                self.current_name = self.next_name
                self.next_name = None
                self.crossfading = False
        else:
            # No crossfade in progress — just present the current scene.
            screen_fbo.use()
            self.fbo_current.color_attachments[0].use(location=0)
            self.crossfade_program["u_tex_a"] = 0
            self.crossfade_program["u_tex_b"] = 0
            self.crossfade_program["u_alpha"] = 0.0
            self.crossfade_vao.render(moderngl.TRIANGLES)
