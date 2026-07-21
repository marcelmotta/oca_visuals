"""
kaleidoscope_video.py
----------------------
Scene 6: the spin-loop video (assets/oca_spin_loop_v3.mp4) fed through a
mirrored radial kaleidoscope, dressed with a few Japanese-inspired
visual elements:

- A seigaiha ("blue ocean waves") tiled arc pattern, the classic
  overlapping-fan-of-circles motif, in deep indigo behind everything.
- Drifting cherry blossom (sakura) petals — a simple 5-lobe polar rose
  shape, tinted soft pink/gold, spawned as a gentle particle burst on
  each drum hit (reusing the same ParticleField as other scenes).
- A thin gold mandala-style ring with periodic notches framing the
  kaleidoscope.
- Overall color grading pulled toward a traditional indigo/vermillion
  /gold palette rather than the source video's raw colors.

MIDI mapping (consistent with the rest of the show):
- "keys" channel CC -> hue, and also nudges the number of kaleidoscope
  wedges (segments) for variety.
- "bass" channel CC -> rotation speed.
- "drums" channel triggers -> a burst of drifting petals + a brief
  zoom "snap" on the kaleidoscope (reusing the shared camera's punch).
"""

import math
import os
import numpy as np
import moderngl
import cv2

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from particle_field import ParticleField

VIDEO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "oca_spin_loop_v3.mp4",
)

MAX_TEXTURE_DIM = 1024

VERTEX_SHADER = """
#version 330
in vec2 in_position;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 330
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_video;
uniform float u_time;
uniform float u_aspect;
uniform float u_segments;
uniform float u_rotation;
uniform float u_zoom;
uniform float u_hue;
uniform float u_punch;

#define PI 3.14159265359

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= u_aspect;  // keep the kaleidoscope's symmetry circular, not elliptical

    float radius = length(uv);
    float angle = atan(uv.y, uv.x) + u_rotation;

    // --- Kaleidoscope fold: mirror the angle into repeating wedges ---
    float segment_angle = (2.0 * PI) / u_segments;
    float wedge = mod(angle, segment_angle);
    wedge = abs(wedge - segment_angle * 0.5);  // mirror within each wedge

    vec2 sample_uv = vec2(cos(wedge), sin(wedge)) * radius * u_zoom;
    sample_uv = sample_uv * 0.5 + vec2(0.5);
    sample_uv = clamp(sample_uv, 0.001, 0.999);
    vec3 video_color = texture(u_video, sample_uv).rgb;

    // --- Traditional Japanese-inspired color grading ---
    // Pull the raw video toward indigo/vermillion/gold rather than
    // using its colors directly.
    float lum = dot(video_color, vec3(0.299, 0.587, 0.114));
    vec3 palette = hsv2rgb(vec3(fract(u_hue + lum * 0.12), 0.6, lum));
    vec3 color = mix(video_color * 0.25, palette, 0.85);

    // --- Seigaiha (layered wave/fan) pattern, subtle, behind everything ---
    vec2 grid_uv = uv * 3.2;
    grid_uv.x += mod(floor(grid_uv.y), 2.0) * 0.5;  // offset alternate rows
    vec2 cell = fract(grid_uv) - 0.5;
    float cell_d = length(cell);
    float fan_rings = abs(sin(cell_d * 14.0 - u_time * 0.25));
    float seigaiha_mask = smoothstep(0.5, 0.42, cell_d);
    vec3 indigo = hsv2rgb(vec3(0.62, 0.65, 0.35));
    color = mix(color, indigo, seigaiha_mask * fan_rings * 0.16);

    // --- Thin gold mandala ring with periodic notches, framing the piece ---
    float notch = 0.5 + 0.5 * cos(angle * u_segments * 2.0);
    float ring_radius = 0.92 + notch * 0.02;
    float gold_ring = smoothstep(0.018, 0.0, abs(radius - ring_radius));
    vec3 gold = vec3(0.85, 0.66, 0.20);
    color += gold * gold_ring * (0.5 + u_punch * 0.5);

    // Gentle vignette so the mandala reads as a contained piece rather
    // than an abrupt frame edge.
    float vignette = 1.0 - smoothstep(0.9, 1.5, radius);
    color *= mix(0.4, 1.0, vignette);

    f_color = vec4(color, 1.0);
}
"""


class KaleidoscopeVideoScene(Scene):
    name = "kaleidoscope_video"

    def setup(self, ctx):
        self.cap = cv2.VideoCapture(VIDEO_PATH)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video file: {VIDEO_PATH}")

        self.video_fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        raw_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        raw_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        scale = min(1.0, MAX_TEXTURE_DIM / max(raw_w, raw_h))
        self.frame_w = max(1, int(raw_w * scale))
        self.frame_h = max(1, int(raw_h * scale))

        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("Could not read the first frame of the video")
        self.texture = ctx.texture((self.frame_w, self.frame_h), 4, self._prepare_frame(frame))
        self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        # Repeat wrap: the kaleidoscope's folded sample_uv can land right
        # at the texture edge, and REPEAT avoids a hard black seam there.
        self.texture.repeat_x = True
        self.texture.repeat_y = True

        self.video_time_accum = 0.0
        self.frame_duration = 1.0 / self.video_fps

        self.program = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
        self.vao = make_fullscreen_quad_vao(ctx, self.program)

        # Drifting petal accents on drum hits — gentle, reusing the same
        # particle system as the logo scenes.
        self.petals = ParticleField(ctx, max_particles=1500, edge_fade=True)

        self.time = 0.0
        self.rotation = 0.0
        self.segments = 8.0
        self.camera = None

    def _prepare_frame(self, frame_bgr):
        if (frame_bgr.shape[1], frame_bgr.shape[0]) != (self.frame_w, self.frame_h):
            frame_bgr = cv2.resize(
                frame_bgr, (self.frame_w, self.frame_h), interpolation=cv2.INTER_AREA
            )
        frame_rgba = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
        return np.ascontiguousarray(frame_rgba).tobytes()

    def _advance_video(self, dt):
        self.video_time_accum += dt
        while self.video_time_accum >= self.frame_duration:
            ok, frame = self.cap.read()
            if not ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
            if ok:
                self.texture.write(self._prepare_frame(frame))
            self.video_time_accum -= self.frame_duration

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera
        self._advance_video(dt)

        bass_intensity = midi.role_cc("bass", "intensity", 0.3)
        self.rotation += dt * (0.15 + bass_intensity * 0.5)

        # Segment count nudged by the "keys" channel for variety — kept
        # to even numbers so the mirror-fold stays clean, in the 6-12 range.
        keys_cc = midi.role_cc("keys", "color_shift", 0.0)
        self.segments = 6.0 + 2.0 * round(keys_cc * 3.0)

        autonomous_hue = (self.time * 0.008) % 1.0
        self.hue = (autonomous_hue + keys_cc) % 1.0

        triggered = bool(midi.role_triggers("drums"))
        self.punch = 1.0 if triggered else getattr(self, "punch", 0.0) * 0.9
        if triggered:
            # A handful of drifting petals, spawned from a random point
            # near the edge so they drift inward/across — gentle, not a
            # dramatic burst.
            origin = (np.random.uniform(-0.9, 0.9), np.random.uniform(-0.9, 0.9))
            hue_choice = (self.hue + np.random.choice([0.0, 0.08, 0.5])) % 1.0
            self.petals.spawn_burst(
                origin=origin, hue=hue_choice, n=18,
                speed_range=(0.05, 0.15), life_range=(3.0, 5.0), sat=0.5,
            )
        self.petals.update(dt, drag=0.995)

    def render(self, target):
        target.use()
        cam = self.camera

        self.program["u_video"] = 0
        self.texture.use(location=0)
        self.program["u_time"] = self.time
        self.program["u_aspect"] = target.size[0] / target.size[1]
        self.program["u_segments"] = self.segments
        self.program["u_rotation"] = self.rotation + (cam.rotation * 0.2 if cam else 0.0)
        self.program["u_zoom"] = 1.0 + (cam.zoom - 1.0) * 0.3 if cam else 1.0
        self.program["u_hue"] = self.hue
        self.program["u_punch"] = self.punch
        self.vao.render(moderngl.TRIANGLES)

        self.petals.render()

    def teardown(self):
        if self.cap is not None:
            self.cap.release()
