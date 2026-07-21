"""
hollow_chars_pulse.py
----------------------
Scene 7: an exact copy of scene 5 (logo_video_pulse.py) — same 3D
camera-angle plane, same background pixel-cloud + per-character
particle burst, same fractal/noise/braid background, same glitch effect
— except the spinning video is replaced with a STATIC image: the
hollow/outline character sequence extracted from page 2 of the
client-provided artwork (OCA_clientversion.ai), assets/hollow_chars.png.

WHERE THIS ASSET CAME FROM:
Page 2 of the source file contains three large connected hollow-outline
text shapes (letters rendered as connected outline strokes with the
letter counters as holes — no fill), consistent with "RHYTHM GATHERING"
/ "SOUND FLOWING" arranged in a circular/badge layout, based on the
per-glyph position data extracted from the PDF content stream. Those
three shapes were isolated programmatically (by connected-component
area, excluding the surrounding poster text like artist names/date/
venue which aren't part of the character sequence) and exported as a
clean transparent PNG. If this reads as the wrong design element once
you see it rendered, swapping assets/hollow_chars.png for a corrected
export is the only change needed — everything else in this file is
identical machinery to scene 5.

Since this is a static image rather than a video, there's no frame
decode/playback loop — the texture is loaded once in setup(), same as
logo_pulse.py's static PNG approach.

CHARACTER_ANCHORS below is a simple placeholder (single center point)
since this artwork's internal layout (which parts are "letters" for the
particle-burst effect) hasn't been mapped out the way the OCA logo's
three circles were — worth revisiting once the asset is confirmed.
"""

import math
import os
import numpy as np
import moderngl
from PIL import Image

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from particle_field import ParticleField

from scenes.logo_pulse import (
    BG_VERTEX, BG_FRAGMENT, LOGO_VERTEX, LOGO_FRAGMENT,
    _perspective_matrix, _rotation_x, _rotation_y, _rotation_z, _translation_z,
)

IMAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "hollow_chars.png",
)

# Placeholder — a single center anchor, since this artwork's internal
# letter layout hasn't been mapped the way the OCA logo's three circles
# were. Revisit if you want the letter-burst to target specific
# characters in this new artwork instead.
CHARACTER_ANCHORS = [(0.0, 0.0)]


class HollowCharsPulseScene(Scene):
    name = "hollow_chars_pulse"

    def setup(self, ctx):
        img = Image.open(IMAGE_PATH).convert("RGBA")
        self.logo_width, self.logo_height = img.size
        self.logo_aspect = self.logo_width / self.logo_height

        self.texture = ctx.texture(img.size, 4, img.tobytes())
        self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.texture.build_mipmaps()

        self.bg_program = ctx.program(vertex_shader=BG_VERTEX, fragment_shader=BG_FRAGMENT)
        self.bg_vao = make_fullscreen_quad_vao(ctx, self.bg_program)

        self.logo_program = ctx.program(vertex_shader=LOGO_VERTEX, fragment_shader=LOGO_FRAGMENT)
        half_h = 1.0
        half_w = half_h * self.logo_aspect
        quad = np.array([
            -half_w, -half_h, 0.0,  0.0, 0.0,
             half_w, -half_h, 0.0,  1.0, 0.0,
             half_w,  half_h, 0.0,  1.0, 1.0,
            -half_w, -half_h, 0.0,  0.0, 0.0,
             half_w,  half_h, 0.0,  1.0, 1.0,
            -half_w,  half_h, 0.0,  0.0, 1.0,
        ], dtype="f4")
        logo_vbo = ctx.buffer(quad.tobytes())
        self.logo_vao = ctx.vertex_array(
            self.logo_program, [(logo_vbo, "3f 2f", "in_position", "in_uv")]
        )

        self.fov = math.radians(50)
        self.distance = half_h / math.tan(self.fov / 2.0)

        self.particles = ParticleField(ctx, max_particles=3000)
        self.letter_particles = ParticleField(ctx, max_particles=2000, edge_fade=True)

        self.time = 0.0
        self.pulse = 0.0
        self.camera = None
        self.letter_trigger_pending = False

        self.next_glitch_time = np.random.uniform(10.0, 25.0)
        self.glitch_active_until = 0.0
        self.glitch_seed = 0.0

        # Fractal bloom is MIDI-triggered in this scene (channel 10 /
        # "pads"), same as scene 5.
        self.bloom_trigger_duration = 7.0
        self.bloom_cell_start = [-9999.0, -9999.0]
        self.bloom_cell_origin = [self._random_bloom_origin(), self._random_bloom_origin()]

    def _random_bloom_origin(self):
        return (float(np.random.uniform(-0.55, 0.55)), float(np.random.uniform(-0.45, 0.45)))

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera

        triggered = bool(midi.role_triggers("drums"))
        self.pulse = 1.0 if triggered else self.pulse * 0.95
        self.letter_trigger_pending = bool(midi.role_triggers("percussion"))

        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0
        self.intensity = 0.3 + midi.role_cc("bass", "intensity", 0.0) * 1.5

        if midi.role_triggers("pads"):
            self.bloom_cell_start[1] = self.bloom_cell_start[0]
            self.bloom_cell_origin[1] = self.bloom_cell_origin[0]
            self.bloom_cell_start[0] = self.time
            self.bloom_cell_origin[0] = self._random_bloom_origin()

        self.bloom_cell_phase = [
            min((self.time - start) / self.bloom_trigger_duration, 1.0)
            for start in self.bloom_cell_start
        ]

        if self.time >= self.next_glitch_time and self.time >= self.glitch_active_until:
            duration = np.random.uniform(0.18, 0.4)
            self.glitch_active_until = self.time + duration
            self.glitch_seed = np.random.uniform(0.0, 1000.0)
            self.next_glitch_time = self.glitch_active_until + np.random.uniform(8.0, 18.0)

        if triggered:
            origin = (np.random.uniform(-0.8, 0.8), np.random.uniform(-0.6, 0.6))
            self.particles.spawn_burst(
                origin=origin, hue=(self.hue + 0.5) % 1.0, n=350,
                speed_range=(0.4, 1.2), life_range=(2.0, 4.0), sat=0.9,
            )
        self.particles.update(dt)
        self.letter_particles.update(dt)

    def render(self, target):
        ctx = self.ctx
        target.use()
        cam = self.camera

        cam_time = cam.time if cam else self.time
        cam_punch = cam.punch if cam else 0.0
        yaw = 0.75 * math.sin(cam_time * 0.15) + cam_punch * 0.12
        pitch = 0.50 * math.sin(cam_time * 0.11 + 1.0)
        roll = 0.40 * math.sin(cam_time * 0.08 + 2.4) + cam_punch * 0.08

        aspect = target.size[0] / target.size[1]
        proj = _perspective_matrix(self.fov, aspect, 0.1, 10.0)
        model = _rotation_z(roll) @ _rotation_x(pitch) @ _rotation_y(yaw)
        view = _translation_z(-self.distance)
        mvp = proj @ view @ model

        if self.letter_trigger_pending:
            anchors = np.array(
                [[x, y, 0.0, 1.0] for x, y in CHARACTER_ANCHORS], dtype="f4"
            )
            clip = (mvp @ anchors.T).T
            ndc = clip[:, :2] / clip[:, 3:4]
            for i, (nx, ny) in enumerate(ndc):
                char_hue = (self.hue + i / max(len(CHARACTER_ANCHORS), 1)) % 1.0
                self.letter_particles.spawn_burst(
                    origin=(float(nx), float(ny)), hue=char_hue, n=45,
                    speed_range=(0.12, 0.35), life_range=(2.0, 3.5), sat=0.55,
                )
            self.letter_trigger_pending = False

        self.bg_program["u_time"] = self.time
        self.bg_program["u_hue"] = self.hue
        self.bg_program["u_intensity"] = self.intensity
        self.bg_program["u_bloom_origin"] = self.bloom_cell_origin
        self.bg_program["u_bloom_phase"] = self.bloom_cell_phase
        self.bg_program["u_aspect"] = target.size[0] / target.size[1]
        self.bg_vao.render(moderngl.TRIANGLES)

        self.particles.render()
        self.letter_particles.render()

        mvp_col_major = mvp.T.astype("f4").copy()

        self.texture.use(location=0)
        self.logo_program["u_logo"] = 0
        self.logo_program["u_mvp"].write(mvp_col_major.tobytes())
        glitch_active = self.time < self.glitch_active_until
        self.logo_program["u_glitch_amount"] = 1.0 if glitch_active else 0.0
        self.logo_program["u_glitch_seed"] = self.glitch_seed

        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.logo_vao.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)
