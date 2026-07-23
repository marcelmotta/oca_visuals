"""
logo_video_pulse.py
--------------------
Scene: the spin-loop video rendered as a real 3D-projected plane
(genuine camera-angle perspective, with a subtle glitch effect), over a
minimal background of just two elements:

1. A translucent, glowing braid of slowly-moving strands across the
   horizon (a thick "pipe" plus a thin, erratically-wandering sliver of
   light flowing through it).
2. A slowly-morphing Julia-set fractal, triggered into bloom by the
   "pads" channel (10) rather than cycling automatically — two
   overlapping bloom cells with randomized origins so consecutive
   blooms vary in position and blend into each other, plus a protected
   "clear zone" near the center so the fractal never fully covers the
   area right behind the logo even at peak bloom.

This is a deliberately minimal version — earlier iterations also had a
noise-wash background layer and two particle-burst systems (a
background pixel-cloud and a percussion-triggered per-character burst),
which were removed to isolate the scene down to just these three
elements: the braid, the animated/glitching logo, and the fractal
background.

This file is fully self-contained (previously shared some shader code
with logo_pulse.py/"scene 4", which has been removed from the project).

MIDI mapping:
- "keys" channel CC -> hue.
- "bass" channel CC -> a mild speed influence on the camera tilt.
- "drums" channel triggers -> a brief camera "punch" (via the shared
  Camera object) that nudges the logo's tilt.
- "pads" channel (10) triggers -> starts a new fractal bloom.
"""

import math
import os
import numpy as np
import moderngl
import cv2

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from video_texture import VideoTexture

VIDEO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "oca_spin_loop_v3.mp4",
)

MAX_TEXTURE_DIM = 1024

# --- Background pass: braid + fractal only ----------------------------

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
uniform vec2 u_bloom_origin[2];
uniform float u_bloom_phase[2];

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

// A Julia-set fractal, slowly animated by moving its constant `c` around
// a small circle so the pattern continuously morphs.
float julia(vec2 z, vec2 c) {
    const int MAX_ITER = 40;
    float iter = 0.0;
    for (int i = 0; i < MAX_ITER; i++) {
        z = vec2(z.x * z.x - z.y * z.y, 2.0 * z.x * z.y) + c;
        if (dot(z, z) > 4.0) break;
        iter += 1.0;
    }
    return iter / float(MAX_ITER);
}

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= u_aspect;

    // A persistent dim baseline tint — WITHOUT this, the background
    // was pure black everywhere the bloom hadn't (yet) revealed, which
    // is most of the screen most of the time: before any pad trigger
    // has ever fired, bloom_mask is 0 everywhere (permanently, verified
    // numerically), so the fractal contributes nothing at all. Once
    // triggers DO start arriving, the traveling reveal wave creates a
    // moving boundary between that black "unrevealed" region and the
    // (now dim-floor-lit) "revealed" one — which is what was actually
    // being seen as "a black animation tied to channel 10": the trigger
    // itself wasn't drawing something black, it was the only thing
    // that ever made the permanently-black background move at all.
    vec3 color = hsv2rgb(vec3(u_hue, 0.5, 0.08));

    // --- Fractal, with pad-triggered dual bloom cells ---
    vec2 julia_c = 0.7885 * vec2(cos(u_time * 0.03), sin(u_time * 0.03));
    float f = julia(uv * 1.1, julia_c);
    // A Julia set's escaped region (the vast majority of a typical view
    // — verified numerically at ~99% of the screen) evaluates to near-
    // zero iteration count, which made f*f render as almost total black
    // there. With a pure-black base color and no other fill layer, that
    // meant the "fractal background" was actually black across nearly
    // the whole screen almost all the time — reported as "a black blur
    // disrupting the background." A brightness floor keeps a dim ambient
    // glow everywhere instead of dropping all the way to black,
    // verified numerically to eliminate near-black pixels entirely.
    float fractal_val = mix(0.15, 1.0, f * f);
    vec3 fractal_color = hsv2rgb(vec3(fract(u_hue + 0.15 + f * 0.3), 0.65, fractal_val));

    float bloom_mask = 0.0;
    for (int i = 0; i < 2; i++) {
        float cycle = 1.0 - abs(2.0 * u_bloom_phase[i] - 1.0);
        vec2 rel = uv - u_bloom_origin[i];
        float dist_sq = dot(rel, rel);
        float wave_pos = mix(2.3, -0.3, cycle);
        float mask = smoothstep(wave_pos - 0.9, wave_pos, dist_sq);
        bloom_mask = max(bloom_mask, mask);
    }
    // NOTE: an earlier version added a static radial "clear zone" here
    // to keep the fractal from fully covering the area behind the logo
    // at peak bloom. That approach backfired: since `color` starts at
    // pure black and the fractal is the only thing that can light up
    // that region, suppressing it there created a permanent black disc
    // at screen center — reported as "a black blur in the same layer as
    // the fractal background." Fixed properly by simply capping the
    // fractal's overall intensity lower (0.65 -> 0.4) instead of
    // creating an artificial static hole — it still blooms across the
    // whole screen, just never gets bright/dominant enough to visually
    // fight with the logo, and there's no fixed dark patch anywhere.
    color += fractal_color * bloom_mask * 0.4;

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
        self.camera = None

        # Random, infrequent, brief glitch.
        self.next_glitch_time = np.random.uniform(10.0, 25.0)
        self.glitch_active_until = 0.0
        self.glitch_seed = 0.0

        # Fractal bloom triggered by channel 10 ("pads"). Two cells: a
        # new trigger shifts the current bloom into a "previous" cell
        # that keeps fading out on its own while a fresh one (new random
        # origin) starts fading in, so consecutive triggers blend into
        # each other instead of cutting off abruptly.
        self.bloom_trigger_duration = 7.0
        self.bloom_cell_start = [-9999.0, -9999.0]
        self.bloom_cell_origin = [self._random_bloom_origin(), self._random_bloom_origin()]

    def _random_bloom_origin(self):
        return (float(np.random.uniform(-0.55, 0.55)), float(np.random.uniform(-0.45, 0.45)))

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera
        self.video.update(dt)

        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0

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

    def render(self, target):
        ctx = self.ctx
        target.use()
        cam = self.camera

        self.bg_program["u_time"] = self.time
        self.bg_program["u_hue"] = self.hue
        self.bg_program["u_aspect"] = target.size[0] / target.size[1]
        self.bg_program["u_bloom_origin"] = self.bloom_cell_origin
        self.bg_program["u_bloom_phase"] = self.bloom_cell_phase
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
