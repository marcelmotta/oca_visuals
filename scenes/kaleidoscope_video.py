"""
kaleidoscope_video.py
----------------------
Scene 6: the spin-loop video (assets/oca_spin_loop_v3.mp4) fed through a
mirrored radial kaleidoscope, dressed with several Japanese-inspired
visual elements:

- A seigaiha ("blue ocean waves") tiled arc pattern, the classic
  overlapping-fan-of-circles motif, in deep indigo behind everything.
- Drifting cherry blossom (sakura) petals — spawned as a gentle
  particle burst on each drum hit (reusing the same ParticleField as
  other scenes).
- A thin gold mandala-style ring with periodic notches framing the
  kaleidoscope.
- "温泉" (onsen/hot-spring) characters wrapping all the way around the
  kaleidoscope's outer boundary. ALWAYS lit at a legible baseline —
  the MIDI-clock-driven chase is a brighten + slight outward glide
  layered on top of that baseline, not a visibility toggle. Each
  occurrence is its own individually-controllable "slot," using two
  clean single-character glyph textures (assets/onsen1.png / onsen2.png,
  not rendered live from a font, for portability) sampled via the
  standard "unwrap text around a circle" technique so every character
  is correctly, readably oriented by construction.
- A second, independent background kaleidoscope layer — a psychedelic,
  multi-hue-cycling hex-tessellated asanoha (hemp-leaf) lattice plus a
  polar crossing-line/petal motif — that fills in the empty/black areas
  behind the foreground video-kaleidoscope. Only appears while channel
  9 ("synth2") has a note held, eased in/out.
- Overall color grading pulled toward a traditional indigo/vermillion
  /gold palette rather than the source video's raw colors.

MIDI mapping (consistent with the rest of the show):
- "keys" channel CC -> hue, and also nudges the number of kaleidoscope
  wedges (segments) for variety.
- "bass" channel CC -> rotation speed.
- "drums" channel triggers -> a burst of drifting petals + a brief
  zoom "snap" on the kaleidoscope (reusing the shared camera's punch).
- "synth2" (channel 9) held notes -> the background kaleidoscope layer.
- MIDI Clock triplets -> advances the sequential character-pop chase
  around the "温泉" ring (requires clock/sync output enabled at the
  source — see midi_input.py's docstring).
"""

import math
import os
import numpy as np
import moderngl
import cv2
from PIL import Image

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from particle_field import ParticleField

VIDEO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "oca_spin_loop_v3.mp4",
)
GLYPH_PATHS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "onsen1.png"),  # 温
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "onsen2.png"),  # 泉
]

RING_SLOT_COUNT = 32
RING_POP_ORDER = "clockwise"  # or "counter_clockwise" or "random"
RING_RADIUS = 0.97
RING_THICKNESS = 0.16

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
uniform sampler2D u_glyph_a;
uniform sampler2D u_glyph_b;
uniform float u_time;
uniform float u_aspect;
uniform float u_video_aspect;
uniform float u_ring_radius;
uniform float u_ring_thickness;
uniform float u_slot_count;
uniform float u_slot_visible[32];
uniform float u_segments;
uniform float u_rotation;
uniform float u_zoom;
uniform float u_hue;
uniform float u_punch;
uniform float u_bg_active;

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

    vec2 sample_pos = vec2(cos(wedge), sin(wedge)) * radius * u_zoom;
    // The fold above is done in aspect-corrected SCREEN space so the
    // wedges themselves are symmetric — but the video texture being
    // sampled has its own aspect ratio (this source video is portrait,
    // not square). Mapping a symmetric polar position directly into
    // that texture's UV space would stretch anything round in the
    // source (the logo's circles) into an ellipse. Correcting for the
    // texture's own aspect here keeps them round.
    sample_pos.x /= u_video_aspect;
    vec2 sample_uv = sample_pos * 0.5 + vec2(0.5);
    sample_uv = clamp(sample_uv, 0.001, 0.999);
    vec3 video_color = texture(u_video, sample_uv).rgb;

    // --- Traditional Japanese-inspired color grading ---
    float lum = dot(video_color, vec3(0.299, 0.587, 0.114));
    vec3 palette = hsv2rgb(vec3(fract(u_hue + lum * 0.12), 0.6, lum));
    vec3 color = mix(video_color * 0.25, palette, 0.85);

    // --- Background kaleidoscope layer (activated by "synth2" / channel
    // 9 playing) ---
    // A second, independent kaleidoscope filling in wherever the
    // foreground video-kaleidoscope is dark/empty, built from TWO
    // combined Japanese motifs, in a psychedelic, multi-hue-cycling
    // palette that visibly contrasts with the foreground's steadier
    // grading:
    //  1. A polar crossing-line + petal motif, tied to the kaleidoscope's
    //     own fold.
    //  2. A genuine hex-tessellated asanoha (hemp-leaf) lattice — six-
    //     pointed rosettes tiled across a true hexagonal grid,
    //     independent of the polar fold, for a much more recognizable
    //     traditional lattice pattern.
    float bg_segments = u_segments * 1.5;
    float bg_segment_angle = (2.0 * PI) / bg_segments;
    float bg_wedge = mod(angle - u_rotation * 0.6, bg_segment_angle);
    bg_wedge = abs(bg_wedge - bg_segment_angle * 0.5);

    float crossing_lines = abs(sin(radius * 16.0 - bg_wedge * 7.0 - u_time * 0.3));
    float petals = pow(abs(cos(bg_wedge * 3.5)), 4.0);
    float polar_pattern = crossing_lines * 0.4 + petals * 0.6;

    vec2 hex_p = uv * 5.0 + vec2(u_time * 0.05, 0.0);
    vec2 hs = vec2(1.0, 1.7320508);
    vec2 ha = mod(hex_p, hs) - hs * 0.5;
    vec2 hb = mod(hex_p - hs * 0.5, hs) - hs * 0.5;
    vec2 hex_local = dot(ha, ha) < dot(hb, hb) ? ha : hb;
    float hex_r = length(hex_local);
    float hex_theta = atan(hex_local.y, hex_local.x) + u_time * 0.2;
    float asanoha_star = pow(abs(cos(hex_theta * 3.0)), 6.0) * smoothstep(0.55, 0.0, hex_r);
    float asanoha_lines = smoothstep(0.035, 0.0, abs(hex_r - 0.32)) * (0.5 + 0.5 * cos(hex_theta * 6.0));
    float asanoha = clamp(asanoha_star * 1.2 + asanoha_lines, 0.0, 1.0);

    float bg_pattern = clamp(polar_pattern * 0.55 + asanoha * 0.75, 0.0, 1.0);

    // Psychedelic multi-hue cycling: hue drifts with angle, radius, AND
    // time simultaneously, so the background visibly shifts through a
    // rainbow rather than sitting on a single contrasting color.
    float psych_hue = u_hue + 0.5
        + sin(bg_wedge * 4.0 + u_time * 0.6) * 0.18
        + radius * 0.25
        + u_time * 0.04;
    vec3 bg_color = hsv2rgb(vec3(fract(psych_hue), 0.85, 0.18 + bg_pattern * 0.75));

    float fg_presence = smoothstep(0.04, 0.28, lum);
    color = mix(bg_color * u_bg_active, color, fg_presence);

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

    // --- "温泉" text wrapping around the exterior edge of the kaleidoscope ---
    // ALWAYS lit at a baseline (legible at all times) — the MIDI-clock
    // chase is layered ON TOP as an extra brighten + slight outward
    // "glide" per character, not a visibility on/off switch. The
    // angular position within a slot becomes the glyph's own horizontal
    // texture coordinate — the standard "unwrap text around a circle"
    // technique.
    //
    // NOTE: a previous attempt flipped this sign to fix mirroring, but
    // the mirroring persisted — meaning that correction was itself
    // wrong (likely overcorrecting, or the real cause was misdiagnosed).
    // Reverted to the direct mapping (angle increasing -> texture x
    // increasing) here.
    float slot_angle_size = (2.0 * PI) / u_slot_count;
    float raw_slot = angle / slot_angle_size;
    float slot_i = floor(raw_slot);
    float slot_idx = mod(slot_i, u_slot_count);
    float local_angle = fract(raw_slot) - 0.5;

    float pop = u_slot_visible[int(slot_idx)];
    float local_radial = (radius - u_ring_radius - pop * 0.035) / u_ring_thickness;
    vec2 glyph_uv = vec2(local_angle + 0.5, local_radial + 0.5);

    if (glyph_uv.x >= 0.0 && glyph_uv.x <= 1.0 && glyph_uv.y >= 0.0 && glyph_uv.y <= 1.0) {
        vec2 flipped_uv = vec2(glyph_uv.x, 1.0 - glyph_uv.y);
        bool is_first_char = mod(slot_idx, 2.0) < 1.0;
        vec4 glyph = is_first_char ? texture(u_glyph_a, flipped_uv) : texture(u_glyph_b, flipped_uv);
        vec3 text_color = hsv2rgb(vec3(fract(u_hue + 0.5), 0.15, 1.0));
        vec3 popped_color = text_color * (1.0 + pop * 0.6);
        float alpha = clamp(0.82 + pop * 0.18, 0.0, 1.0);
        color = mix(color, popped_color, glyph.a * alpha);
    }

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
        self.texture.repeat_x = True
        self.texture.repeat_y = True

        self.video_time_accum = 0.0
        self.frame_duration = 1.0 / self.video_fps

        self.program = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
        self.vao = make_fullscreen_quad_vao(ctx, self.program)

        self.petals = ParticleField(ctx, max_particles=1500, edge_fade=True)

        self.glyph_textures = []
        for path in GLYPH_PATHS:
            img = Image.open(path).convert("RGBA")
            tex = ctx.texture(img.size, 4, img.tobytes())
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self.glyph_textures.append(tex)

        base_order = list(range(RING_SLOT_COUNT))
        if RING_POP_ORDER == "counter_clockwise":
            base_order = list(reversed(base_order))
        elif RING_POP_ORDER == "random":
            np.random.shuffle(base_order)
        self.slot_order = base_order
        self.slot_pop_time = np.full(RING_SLOT_COUNT, -999.0, dtype="f4")
        self.order_pointer = 0

        self.video_aspect = self.frame_w / self.frame_h

        self.time = 0.0
        self.rotation = 0.0
        self.segments = 8.0
        self.camera = None
        self.bg_active = 0.0

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

        keys_cc = midi.role_cc("keys", "color_shift", 0.0)
        self.segments = 6.0 + 2.0 * round(keys_cc * 3.0)

        # Background kaleidoscope layer: active for as long as channel 9
        # ("synth2") has a note held, eased in/out.
        synth2_playing = bool(midi.role_active_notes("synth2"))
        bg_target = 1.0 if synth2_playing else 0.0
        ease_rate = 3.0 if synth2_playing else 1.5
        self.bg_active += (bg_target - self.bg_active) * min(dt * ease_rate, 1.0)

        autonomous_hue = (self.time * 0.008) % 1.0
        self.hue = (autonomous_hue + keys_cc) % 1.0

        # Sequential character pop, timed to MIDI Clock triplets.
        if midi.triplet_tick_pending:
            slot = self.slot_order[self.order_pointer % RING_SLOT_COUNT]
            self.slot_pop_time[slot] = self.time
            self.order_pointer += 1

        triggered = bool(midi.role_triggers("drums"))
        self.punch = 1.0 if triggered else getattr(self, "punch", 0.0) * 0.9
        if triggered:
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
        self.program["u_glyph_a"] = 1
        self.glyph_textures[0].use(location=1)
        self.program["u_glyph_b"] = 2
        self.glyph_textures[1].use(location=2)
        self.program["u_time"] = self.time
        self.program["u_aspect"] = target.size[0] / target.size[1]
        self.program["u_video_aspect"] = self.video_aspect
        self.program["u_ring_radius"] = RING_RADIUS
        self.program["u_ring_thickness"] = RING_THICKNESS
        self.program["u_slot_count"] = float(RING_SLOT_COUNT)

        age = self.time - self.slot_pop_time
        fade_in = np.clip(age / 0.08, 0.0, 1.0)
        fade_out = np.clip(1.0 - (age - 0.08) / 0.7, 0.0, 1.0)
        visibility = np.clip(fade_in * fade_out, 0.0, 1.0)
        self.program["u_slot_visible"] = [float(v) for v in visibility]

        self.program["u_segments"] = self.segments
        self.program["u_rotation"] = self.rotation + (cam.rotation * 0.2 if cam else 0.0)
        self.program["u_zoom"] = 1.0 + (cam.zoom - 1.0) * 0.3 if cam else 1.0
        self.program["u_hue"] = self.hue
        self.program["u_punch"] = self.punch
        self.program["u_bg_active"] = self.bg_active
        self.vao.render(moderngl.TRIANGLES)

        self.petals.render()

    def teardown(self):
        if self.cap is not None:
            self.cap.release()
