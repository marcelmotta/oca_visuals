"""
noise_field.py
--------------
Breathing organic color field, now with:
- Two noise layers = two depth "planes": a slow, large-scale BACKGROUND
  flow and a faster, finer-detail FOREGROUND flow, blended together
  with different hues so they read as distinct layers rather than one
  flat wash.
- Longer sustain on triggered ripples (was ~1.5s, now ~4s) with a softer
  falloff, so hits leave a lasting impression instead of a quick blip.
- The shared Camera's pan/zoom/rotation applied to the sampling domain
  for both layers (background moves less, foreground moves more — real
  parallax), so perspective is always drifting rather than static.
"""

import os
import numpy as np
import moderngl

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from hollow_logo import HollowLogoOverlay

MAX_PULSES = 8

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

uniform float u_time;
uniform float u_speed;
uniform float u_hue;
uniform float u_brightness;
uniform float u_aspect;
uniform vec2 u_pulse_pos[8];
uniform float u_pulse_age[8];

uniform vec2 u_cam_offset;
uniform float u_cam_rot;

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

// Ripple constants shared between the displacement (refraction) and
// the directional shading below.
const float RIPPLE_MAX_AGE = 2.8;
const float RIPPLE_SPEED = 0.35;      // slower expansion (was 0.55)
const float RIPPLE_MAX_RADIUS = 0.5;
const float RIPPLE_WAVE_FREQ = 25.0;  // fewer trailing bands (was 55 -> ~4-5 bands, now ~2)
const float RIPPLE_DECAY_RATE = 10.0; // how fast those bands die out away from the leading edge

// Returns (dx, dy, gradX, gradY): dx/dy is how much to displace the
// SAMPLING coordinate at this pixel (makes the background/foreground
// pattern visibly warp/refract, as if seen through a disturbed water
// surface), and gradX/gradY is the raw (unscaled) directional wave sum,
// used afterward to build a fake surface normal for directional
// lighting — like a parallel light source catching the ripple's slope,
// the way real light refracts/reflects off moving water.
vec4 rippleWarp(vec2 pos) {
    vec2 total_offset = vec2(0.0);
    vec2 raw_grad = vec2(0.0);
    for (int i = 0; i < 8; i++) {
        float age = u_pulse_age[i];
        if (age < RIPPLE_MAX_AGE) {
            vec2 center = vec2(u_pulse_pos[i].x * u_aspect, u_pulse_pos[i].y);
            vec2 delta = pos - center;
            float d = length(delta) + 1e-5;
            vec2 dir = delta / d;
            float leading_edge = age * RIPPLE_SPEED;

            float dist_env = 1.0 - smoothstep(0.0, RIPPLE_MAX_RADIUS, leading_edge);
            float time_env = 1.0 - smoothstep(0.0, RIPPLE_MAX_AGE, age);
            float envelope = dist_env * time_env;

            // A decaying oscillation trailing the leading edge — this is
            // the actual "ripple shape" (now tuned to ~2 bands total:
            // the primary impact ring plus one clear secondary ripple,
            // rather than the 4-5 bands from before).
            float rel = d - leading_edge;
            float wave = sin(rel * RIPPLE_WAVE_FREQ) * exp(-abs(rel) * RIPPLE_DECAY_RATE);

            total_offset += dir * wave * envelope * 0.028;
            raw_grad += dir * wave * envelope;
        }
    }
    return vec4(total_offset, raw_grad);
}

// Applies the shared camera (rotate/pan only — NOT zoom) to a uv,
// scaled by a per-layer parallax factor (0 = distant/background, 1 =
// near/foreground). Zoom is intentionally excluded entirely: it's the
// component tied to drum-hit "punches" and tempo-linked breathing, and
// this scene should never visibly pulsate in reaction to MIDI triggers.
vec2 applyCamera(vec2 uv, float parallax) {
    float ca = cos(u_cam_rot * parallax);
    float sa = sin(u_cam_rot * parallax);
    uv = mat2(ca, -sa, sa, ca) * uv;
    uv -= u_cam_offset * parallax;
    return uv;
}

void main() {
    vec2 base_uv = v_uv * 2.0 - 1.0;
    // Aspect correction: without this, anything meant to look round
    // (noise blobs, ripples) appears stretched into an ellipse on any
    // screen that isn't exactly square (i.e. virtually all of them).
    base_uv.x *= u_aspect;

    // Ripples now WARP the sampling coordinate itself — like looking
    // through a disturbed water surface at the noise pattern underneath
    // — rather than drawing a colored ring on top of it. Applied before
    // the camera transform so the warp stays fixed to screen position
    // regardless of the (subtle) camera pan/rotation.
    vec4 ripple = rippleWarp(base_uv);
    vec2 warped_uv = base_uv + ripple.xy;

    // --- Background layer: slow, large-scale, low parallax ---
    // Time multipliers halved from before (0.06/0.05/0.02 -> 0.03
    // /0.025/0.01) — the back-and-forth flow was moving too fast.
    vec2 bg_uv = applyCamera(warped_uv, 0.35);
    vec2 bg_warp = vec2(
        noise(bg_uv * 0.8 + u_time * u_speed * 0.03),
        noise(bg_uv * 0.8 - u_time * u_speed * 0.025 + 4.2)
    );
    float bg_n = noise(bg_uv * 1.0 + bg_warp * 1.2 + u_time * u_speed * 0.01);
    float bg_hue = fract(u_hue - 0.12 + bg_n * 0.2);
    vec3 bg_color = hsv2rgb(vec3(bg_hue, 0.6, 0.18 + 0.30 * bg_n));

    // --- Foreground layer: faster, finer detail, full parallax ---
    vec2 fg_uv = applyCamera(warped_uv, 1.0);
    vec2 fg_warp = vec2(
        noise(fg_uv * 2.2 + u_time * u_speed * 0.16),
        noise(fg_uv * 2.2 - u_time * u_speed * 0.13 + 1.7)
    );
    float fg_n = noise(fg_uv * 2.6 + fg_warp * 1.6 + u_time * u_speed * 0.06);
    float fg_hue = fract(u_hue + 0.25 + fg_n * 0.25);
    float fg_val = fg_n * fg_n;  // sharper contrast for the "detail" plane
    vec3 fg_color = hsv2rgb(vec3(fg_hue, 0.7, fg_val));

    vec3 color = mix(bg_color, fg_color, 0.5);

    // Directional ("parallel light source") shading: treat the ripple's
    // gradient as a fake surface normal and light it like a bump-mapped
    // surface, rather than a flat brightness bump — this is what
    // actually reads as light refracting/reflecting off the slope of
    // moving water, with a bright side facing the light and a slightly
    // darker side facing away, instead of a uniform glow.
    vec3 lightDir = normalize(vec3(0.45, 0.55, 0.7));
    vec3 normal = normalize(vec3(-ripple.zw * 0.6, 1.0));
    float diffuse = dot(normal, lightDir);
    float flatDiffuse = lightDir.z;  // dot((0,0,1), lightDir)
    float shading = (diffuse - flatDiffuse) * 1.4;
    color += vec3(1.0, 0.98, 0.92) * shading;

    f_color = vec4(color * u_brightness, 1.0);
}
"""


class NoiseFieldScene(Scene):
    name = "noise_field"

    def setup(self, ctx):
        self.program = ctx.program(
            vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER
        )
        self.vao = make_fullscreen_quad_vao(ctx, self.program)
        self.time = 0.0
        self.pulse_pos = np.zeros((MAX_PULSES, 2), dtype="f4")
        self.pulse_age = np.full(MAX_PULSES, 999.0, dtype="f4")
        self.pulse_cursor = 0
        self.camera = None
        # Safe defaults so render() never crashes if called before
        # update() has run even once.
        self.speed = 0.3
        self.hue = 0.0
        self.brightness = 0.8

        # Autonomous "droplets": ripples that pop in on their own at
        # random screen positions, independent of any MIDI trigger —
        # restores the ambient droplet effect from an earlier version.
        # Reuses the same ripple rendering as the MIDI-triggered ones
        # (now toned down/subtle — see the ring/envelope changes above).
        self.next_droplet_time = np.random.uniform(1.0, 3.0)

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logo_overlay = HollowLogoOverlay(ctx, project_root)

    def update(self, dt, midi, camera):
        self.time += dt
        self.pulse_age += dt
        self.camera = camera
        self.logo_overlay.update(dt, midi)

        for note in midi.role_triggers("texture"):
            x = ((note % 12) / 12.0) * 2.0 - 1.0
            y = ((note // 12) % 4) / 4.0 * 2.0 - 1.0
            i = self.pulse_cursor
            self.pulse_pos[i] = [x, y]
            self.pulse_age[i] = 0.0
            self.pulse_cursor = (self.pulse_cursor + 1) % MAX_PULSES

        # Autonomous droplets: random position anywhere on screen, on a
        # random timer, independent of MIDI — subtle ambient life in the
        # background even with no input.
        if self.time >= self.next_droplet_time:
            i = self.pulse_cursor
            self.pulse_pos[i] = [np.random.uniform(-1.0, 1.0), np.random.uniform(-1.0, 1.0)]
            self.pulse_age[i] = 0.0
            self.pulse_cursor = (self.pulse_cursor + 1) % MAX_PULSES
            self.next_droplet_time = self.time + np.random.uniform(1.5, 4.0)

        self.speed = 0.3 + midi.role_cc("bass", "intensity", 0.0) * 2.0
        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0
        self.brightness = 0.75 + midi.role_cc("drums", "master_brightness", 0.8) * 0.5

    def render(self, target):
        target.use()
        self.program["u_time"] = self.time
        self.program["u_speed"] = self.speed
        self.program["u_hue"] = self.hue
        self.program["u_brightness"] = self.brightness
        self.program["u_aspect"] = target.size[0] / target.size[1]
        self.program["u_pulse_pos"] = [tuple(p) for p in self.pulse_pos]
        self.program["u_pulse_age"] = [float(a) for a in self.pulse_age]

        cam = self.camera
        self.program["u_cam_offset"] = tuple(cam.offset) if cam else (0.0, 0.0)
        self.program["u_cam_rot"] = cam.rotation if cam else 0.0
        self.vao.render(moderngl.TRIANGLES)

        self.logo_overlay.render(target)

    def teardown(self):
        self.logo_overlay.release()
