"""
logo_video_pulse.py
--------------------
Scene: the spin-loop video rendered as a real 3D-projected plane
(genuine camera-angle perspective, with a subtle glitch effect), over a
background of just one element: a translucent, glowing braid of
slowly-moving strands across the horizon (a thick "pipe" plus a thin,
erratically-wandering sliver of light flowing through it).

The fractal background system that used to live here has been removed
entirely — despite several fix attempts (a brightness floor, removing
an artifact-introducing "clear zone," a persistent baseline tint), a
"black animation tied to channel 10 (pads)" was still being reported.
Rather than attempt yet another patch on the same system, it was pulled
out completely so the fractal can be rebuilt from scratch as its own
piece of work, on a clean slate with just the logo + braid as the
foundation.

MIDI mapping:
- "keys" channel CC -> hue.
- "drums" channel triggers -> a brief camera "punch" (via the shared
  Camera object) that nudges the logo's tilt.
"""

import math
import os
import numpy as np
import moderngl

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from video_texture import VideoTexture

VIDEO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "oca_spin_loop_v3.mp4",
)

MAX_TEXTURE_DIM = 1024

# --- Background pass: braid only --------------------------------------

BG_VERTEX = """
#version 330
in vec2 in_position;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

BG_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 f_color;

uniform float u_time;
uniform float u_hue;
uniform float u_aspect;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}
float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}
vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= u_aspect;

    // Dim baseline tint so the background is never pure black.
    vec3 color = hsv2rgb(vec3(u_hue, 0.5, 0.08));

    // --- Braid: thick "pipe" + thin flowing sliver ---
    vec3 braid_color = hsv2rgb(vec3(fract(u_hue + 0.55), 0.45, 1.0));
    vec3 sliver_color = hsv2rgb(vec3(fract(u_hue + 0.05), 0.85, 1.0));
    float braid = 0.0;
    float sliver_glow = 0.0;
    for (int i = 0; i < 3; i++) {
        float phase = float(i) * 2.094395;

        float strand_y = -0.05
            + 0.07 * sin(uv.x * 2.6 + u_time * 0.12 + phase)
            + 0.025 * sin(uv.x * 6.3 - u_time * 0.07 + phase * 1.7);
        float d = abs(uv.y - strand_y);
        float pipe_glow = exp(-d * d * 260.0);
        braid += pipe_glow;

        float wobble = noise(vec2(uv.x * 3.5 + float(i) * 11.0, u_time * 0.35 + phase))
            + 0.5 * noise(vec2(uv.x * 9.0 - float(i) * 5.0, u_time * 0.6));
        float sliver_y = strand_y + 0.035 * (wobble - 0.75);
        float sd = abs(uv.y - sliver_y);
        float sliver_shape = exp(-sd * sd * 2200.0);

        float travel = smoothstep(0.3, 1.0,
            sin(uv.x * 4.0 - u_time * (1.2 + float(i) * 0.3) + phase));
        sliver_glow += sliver_shape * travel;
    }
    color += braid_color * braid * 0.45;
    color += sliver_color * sliver_glow * 0.55;

    f_color = vec4(color, 1.0);
}
"""

# --- Video plane pass: real 3D perspective, with glitch --------------

LOGO_VERTEX = """
#version 330
in vec3 in_position;
in vec2 in_uv;
out vec2 v_uv;
uniform mat4 u_mvp;
void main() {
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_position, 1.0);
}
"""

LOGO_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_logo;
uniform float u_glitch_amount;
uniform float u_glitch_seed;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

void main() {
    vec2 uv = v_uv;

    vec3 tex_rgb;
    if (u_glitch_amount > 0.0) {
        float band = floor(v_uv.y * 14.0);
        float band_rand = hash(vec2(band, u_glitch_seed));
        float tear = step(0.55, band_rand) * (band_rand - 0.5) * 2.0;
        uv.x += tear * 0.12 * u_glitch_amount;

        float split = 0.012 * u_glitch_amount;
        float r = texture(u_logo, vec2(uv.x + split, 1.0 - uv.y)).r;
        float g = texture(u_logo, vec2(uv.x, 1.0 - uv.y)).g;
        float b = texture(u_logo, vec2(uv.x - split, 1.0 - uv.y)).b;
        tex_rgb = vec3(r, g, b);
    } else {
        tex_rgb = texture(u_logo, vec2(uv.x, 1.0 - uv.y)).rgb;
    }

    float lum = dot(tex_rgb, vec3(0.299, 0.587, 0.114));
    float alpha = smoothstep(0.35, 0.55, lum);
    if (alpha <= 0.01) discard;
    f_color = vec4(tex_rgb, alpha);
}
"""


def _perspective_matrix(fovy, aspect, near, far):
    f = 1.0 / math.tan(fovy / 2.0)
    return np.array([
        [f / aspect, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, (far + near) / (near - far), (2 * far * near) / (near - far)],
        [0, 0, -1, 0],
    ], dtype="f4")


def _rotation_x(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([
        [1, 0, 0, 0],
        [0, c, -s, 0],
        [0, s, c, 0],
        [0, 0, 0, 1],
    ], dtype="f4")


def _rotation_y(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([
        [c, 0, s, 0],
        [0, 1, 0, 0],
        [-s, 0, c, 0],
        [0, 0, 0, 1],
    ], dtype="f4")


def _rotation_z(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([
        [c, -s, 0, 0],
        [s, c, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
    ], dtype="f4")


def _translation_z(dz):
    m = np.eye(4, dtype="f4")
    m[2, 3] = dz
    return m


class LogoVideoPulseScene(Scene):
    name = "logo_video_pulse"

    def setup(self, ctx):
        self.video = VideoTexture(ctx, VIDEO_PATH, max_dim=MAX_TEXTURE_DIM)

        self.bg_program = ctx.program(vertex_shader=BG_VERTEX, fragment_shader=BG_FRAGMENT)
        self.bg_vao = make_fullscreen_quad_vao(ctx, self.bg_program)

        self.logo_program = ctx.program(vertex_shader=LOGO_VERTEX, fragment_shader=LOGO_FRAGMENT)
        half_h = 1.0
        half_w = half_h * self.video.aspect
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

        self.time = 0.0
        self.hue = 0.0
        self.camera = None

        # Random, infrequent, brief glitch.
        self.next_glitch_time = np.random.uniform(10.0, 25.0)
        self.glitch_active_until = 0.0
        self.glitch_seed = 0.0

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera
        # The video itself is the spin-loop footage — freezing it on
        # MIDI-quiet (handled inside VideoTexture) IS "the logo's
        # rotation stopping". The plane's own tilt below is a separate,
        # always-on animation and is intentionally NOT gated on MIDI.
        self.video.update(dt, midi)

        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0

        if self.time >= self.next_glitch_time and self.time >= self.glitch_active_until:
            duration = np.random.uniform(0.18, 0.4)
            self.glitch_active_until = self.time + duration
            self.glitch_seed = np.random.uniform(0.0, 1000.0)
            self.next_glitch_time = self.glitch_active_until + np.random.uniform(8.0, 18.0)

    def render(self, target):
        ctx = self.ctx
        target.use()
        cam = self.camera

        self.bg_program["u_time"] = self.time
        self.bg_program["u_hue"] = self.hue
        self.bg_program["u_aspect"] = target.size[0] / target.size[1]
        self.bg_vao.render(moderngl.TRIANGLES)

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
        mvp_col_major = mvp.T.astype("f4").copy()

        self.video.texture.use(location=0)
        self.logo_program["u_logo"] = 0
        self.logo_program["u_mvp"].write(mvp_col_major.tobytes())
        glitch_active = self.time < self.glitch_active_until
        self.logo_program["u_glitch_amount"] = 1.0 if glitch_active else 0.0
        self.logo_program["u_glitch_seed"] = self.glitch_seed

        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.logo_vao.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)

    def teardown(self):
        self.video.release()
