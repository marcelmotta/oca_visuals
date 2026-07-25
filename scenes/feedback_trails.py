"""
feedback_trails.py
-------------------
Scene 2's previous background (a ping-pong feedback/blur buffer with two
drifting blobs) has been replaced with the kaleidoscopic folding
fractal that was originally built for — then removed from —
logo_video_fractal.py (scene 5, after scenes 5/6 were later swapped),
per a change of heart: that scene keeps its current ground-mesh-lighting
direction, and this fractal gets a home here instead rather than being
discarded. The hollow white-outline logo overlay (shared with scenes 1
and 3) is unchanged.

The fractal itself: a kaleidoscopic folding fractal (repeated fold +
rotate + scale of the plane, the technique behind most "Mandelbox"/
kaleidoscope-tunnel shader art) rather than escape-time coloring (like
a Julia/Mandelbrot set), so it doesn't have the "near-total-black"
failure mode escape-time coloring has: color here is a sum across
fold-depths, not a threshold on an iteration count. Fully invisible at
rest (no faint always-on streaks); while channel 10 ("pads"/DX) has a
note held, it blooms in — brighter, more saturated, rotation and
hue-cycling faster — and fades back out to nothing on release. All fold
depths always fade in/out together in lockstep (an earlier version
instead swept a "reveal" through progressively deeper depths, but that
made shallow depths fade far slower than deep ones during release,
leaving an isolated crease-line lingering after everything else had
already faded out). Rotation/hue-cycling phases are pre-accumulated
incrementally each frame rather than derived from elapsed time, since
the latter causes a jump proportional to total elapsed session time
every time bloom changes (verified numerically in earlier development:
a bloom transition 30 minutes into a session spiked to ~675 rad/s vs.
the intended ~0.07 rad/s max).

MIDI mapping:
- "keys" channel CC -> hue.
- "pads" channel (10) held notes -> fractal bloom amount.
"""

import os

import moderngl

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from hollow_logo import HollowLogoOverlay

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

uniform float u_hue;
uniform float u_aspect;
uniform float u_bloom;
uniform float u_fractal_rot_phase;
uniform float u_fractal_hue_phase;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

#define FOLD_ITER 8

vec2 rot2(vec2 p, float a) {
    float c = cos(a), s = sin(a);
    return vec2(p.x * c - p.y * s, p.x * s + p.y * c);
}

// Kaleidoscopic folding fractal: each iteration folds the plane
// (abs(p) - offset, a mirror-reflection fold), rotates it, then scales
// it up — the standard "Kaleidoscopic IFS" construction behind most
// Mandelbox/kaleidoscope-tunnel shader art. Because fold+rotate+scale
// is applied to BOUNDED coordinates (unlike escape-time squaring, which
// diverges), this stays numerically calm with no escape threshold at
// all — color is a weighted sum of a color per fold-depth, decaying by
// the same scale factor the geometry shrinks by, so brightness is a
// smooth gradient by construction rather than a threshold.
//
// `bloom` (0..1) scales saturation and (via update()'s rot/hue phase
// rates) rotation/color-cycling speed. All FOLD_ITER fold depths always
// contribute equally, fading in/out together in lockstep with bloom.
vec3 kaleido_fractal(vec2 uv, float bloom, float hue_base, float rot_phase, float hue_phase) {
    const float scale = 1.6;
    const float offset = 0.6;

    vec2 p = uv;
    vec3 col = vec3(0.0);
    float amp = 1.0;
    for (int i = 0; i < FOLD_ITER; i++) {
        p = abs(p) - offset;
        p = rot2(p, rot_phase + float(i) * 0.4);
        p *= scale;
        amp /= scale;

        // This level's actual contribution to the image: pixels near a
        // fold crease (p close to either axis) glow. Without this, the
        // color/amp terms below are the same for every pixel and the
        // whole layer would just be a flat wash — this is what makes
        // the self-similar crease/line structure (the part that
        // actually reads as "fractal") visible at all. The pow()
        // sharpens the crease lines beyond the raw exponential falloff.
        float d = min(abs(p.x), abs(p.y));
        float glow = pow(exp(-d * d * 35.0), 1.5);

        float hue = fract(hue_base + hue_phase + float(i) * 0.09);
        vec3 layer_color = hsv2rgb(vec3(hue, mix(0.25, 0.9, bloom), 1.0));
        col += layer_color * amp * glow;
    }
    return col;
}

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= u_aspect;

    // Dim baseline tint so the background is never pure black.
    vec3 color = hsv2rgb(vec3(u_hue, 0.5, 0.08));

    // Fully invisible at rest (u_bloom == 0 contributes nothing at
    // all); a note held on the pads channel blooms it in — brighter,
    // more saturated, faster-turning — and it fades back out
    // completely, all fold depths together in lockstep, on release
    // (see update()'s u_bloom).
    vec3 fractal = kaleido_fractal(uv, u_bloom, u_hue, u_fractal_rot_phase, u_fractal_hue_phase);
    color += fractal * u_bloom;

    f_color = vec4(color, 1.0);
}
"""


class FeedbackTrailsScene(Scene):
    name = "feedback_trails"

    def setup(self, ctx):
        self.bg_program = ctx.program(vertex_shader=BG_VERTEX, fragment_shader=BG_FRAGMENT)
        self.bg_vao = make_fullscreen_quad_vao(ctx, self.bg_program)

        self.time = 0.0
        self.hue = 0.0
        self.camera = None
        self.bloom = 0.0
        self.fractal_rot_phase = 0.0
        self.fractal_hue_phase = 0.0

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logo_overlay = HollowLogoOverlay(ctx, project_root)

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera
        self.logo_overlay.update(dt, midi)

        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0

        # Fractal bloom: eases toward 1 while channel 10 ("pads") has a
        # note held, and back toward 0 (slower) on release — same
        # asymmetric ease-in/out shape as the kaleidoscope scene's
        # synth2 background layer.
        pads_playing = bool(midi.role_active_notes("pads"))
        bloom_target = 1.0 if pads_playing else 0.0
        ease_rate = 3.0 if pads_playing else 0.3
        self.bloom += (bloom_target - self.bloom) * min(dt * ease_rate, 1.0)

        # Accumulate the fractal's rotation/hue phases incrementally
        # (phase += dt * rate) rather than deriving them from
        # elapsed_time * rate in the shader — see module docstring.
        # Speeds kept low so even at full bloom this reads as a slow,
        # evolving motion rather than a fast spin.
        rot_speed = 0.015 + (0.07 - 0.015) * self.bloom
        self.fractal_rot_phase += dt * rot_speed
        hue_speed = 0.006 + (0.018 - 0.006) * self.bloom
        self.fractal_hue_phase += dt * hue_speed

    def render(self, target):
        target.use()

        self.bg_program["u_hue"] = self.hue
        self.bg_program["u_aspect"] = target.size[0] / target.size[1]
        self.bg_program["u_bloom"] = self.bloom
        self.bg_program["u_fractal_rot_phase"] = self.fractal_rot_phase
        self.bg_program["u_fractal_hue_phase"] = self.fractal_hue_phase
        self.bg_vao.render(moderngl.TRIANGLES)

        self.logo_overlay.render(target)

    def teardown(self):
        self.logo_overlay.release()
