"""
logo_pulse.py
--------------
The Oca Collective logo, now with:

1. REAL 3D CAMERA ANGLES on the logo itself. The flat logo image is
   rendered as a textured plane placed in 3D space and viewed through
   an actual perspective projection (not a 2D image-warp trick) — so as
   the virtual camera orbits/tilts, you get genuine perspective
   foreshortening, exactly like tilting a physical printed sign in
   front of a camera. Every pixel of the source artwork is still
   sampled and displayed unmodified — what changes is where in 3D space
   you're viewing it from, which is a real camera effect, not a
   distortion of the artwork's own colors/shape.
2. A gentle burst of particles from each character, triggered by the
   "percussion" MIDI mapping (hi-hats + percussion, channels 4-7 —
   separate from the "drums" mapping used elsewhere, which is now just
   kick/snare/snare2 on channels 1-3). Drawn BEFORE the logo plane, not
   after — the logo's mark is pure white, and additive particles drawn
   on top of already-saturated white clip to white and disappear.
3. A translucent, glowing braid of slowly-moving strands across the
   horizon, and a slowly-morphing Julia-set fractal layered beneath the
   noise wash, both woven into the animated background for depth.

LAYERING: background (fractal + noise wash + braid) is the "far" layer
and barely reacts to camera movement; both particle layers (background
pixel-cloud + per-character letter burst) sit above that; the logo
plane is the tilting 3D "subject" drawn last, occluding whatever falls
behind its opaque shapes.
"""

import math
import os
import numpy as np
import moderngl
from PIL import Image

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from particle_field import ParticleField

ASSET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "oca_logo.png",
)

# --- Background pass (noise wash + braid), fullscreen ----------------------

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
uniform float u_intensity;
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
// a small circle (the classic trick for a continuously morphing Julia
// set) — layered in behind the noise wash for extra depth/detail.
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
    // NOTE: the background (noise wash, fractal, braid) intentionally
    // does NOT read the shared camera's pan/zoom/rotation/punch at all
    // — only the logo plane itself should visibly react to hits. This
    // uses the plain screen uv throughout.
    vec2 uv = v_uv * 2.0 - 1.0;
    // Aspect correction: without this, the fractal bloom, ripples, and
    // braid curves all get stretched into ellipses on any screen that
    // isn't exactly square (i.e. virtually all of them).
    uv.x *= u_aspect;

    float n1 = noise(uv * 1.1 + u_time * u_intensity * 0.06);
    float n2 = noise(uv * 2.3 - u_time * u_intensity * 0.04 + 5.0);
    float hueA = fract(u_hue + n1 * 0.18);
    float hueB = fract(u_hue + 0.4 + n2 * 0.18);
    vec3 colorA = hsv2rgb(vec3(hueA, 0.75, 0.10 + 0.18 * n1));
    vec3 colorB = hsv2rgb(vec3(hueB, 0.65, 0.06 + 0.12 * n2));
    vec3 color = colorA + colorB * 0.6;

    // Fractal layer: sits furthest back, adding fine self-similar detail
    // and a sense of depth beneath the noise wash. `c` drifts slowly
    // around a small circle so the pattern continuously morphs — that
    // rotation speed (u_time * 0.03) is the "bloom speed" and stays
    // unchanged.
    //
    // NOT tiled — a single, connected fractal reads as one entity rather
    // than repeated copies. Scale chosen (verified numerically) so real
    // detail exists broadly across edges/corners/center rather than
    // only in a tiny central patch (a larger scale here makes points
    // escape almost immediately outside the center, which is the bug
    // from the last version).
    vec2 julia_c = 0.7885 * vec2(cos(u_time * 0.03), sin(u_time * 0.03));
    float f = julia(uv * 1.1, julia_c);
    vec3 fractal_color = hsv2rgb(vec3(fract(u_hue + 0.15 + f * 0.3), 0.65, f * f));

    // Reveal wave: TWO overlapping "bloom cells" (not one fixed to
    // screen center) — Python assigns each a randomized origin and its
    // own timing, so consecutive blooms vary in position instead of
    // always sweeping from the same spot, and by staggering the two
    // cells' timing, one is always fading in while the other fades out
    // rather than the whole effect dropping to nothing between cycles.
    //
    // Uses dist-SQUARED (not raw distance) against the wave threshold:
    // screen area grows with r^2, so sweeping raw distance linearly
    // reveals area at a very uneven rate; comparing against r^2 instead
    // makes the reveal advance at a more constant area rate, which
    // reads as a smoother, less sudden transition.
    float bloom_mask = 0.0;
    for (int i = 0; i < 2; i++) {
        float cycle = 1.0 - abs(2.0 * u_bloom_phase[i] - 1.0); // 0->1->0 triangle
        vec2 rel = uv - u_bloom_origin[i];
        float dist_sq = dot(rel, rel);
        float wave_pos = mix(2.3, -0.3, cycle);
        float mask = smoothstep(wave_pos - 0.9, wave_pos, dist_sq);
        bloom_mask = max(bloom_mask, mask);
    }
    color += fractal_color * bloom_mask * 0.65;

    // Translucent, glowing braid across the horizon: three THICK, soft
    // "pipe" strands on a smooth, slow, purely sinusoidal path (restored
    // to their original thickness/trajectory — the erratic wobble and
    // thinness from the last version belonged to the sliver below, not
    // the pipe itself). Inside each pipe, a much THINNER, brighter
    // sliver of contrasting color wanders erratically and travels along
    // the strand over time, like colored light flowing through a
    // transparent tube.
    vec3 braid_color = hsv2rgb(vec3(fract(u_hue + 0.55), 0.45, 1.0));
    vec3 sliver_color = hsv2rgb(vec3(fract(u_hue + 0.05), 0.85, 1.0));
    float braid = 0.0;
    float sliver_glow = 0.0;
    for (int i = 0; i < 3; i++) {
        float phase = float(i) * 2.094395; // 2*pi/3 apart

        // The pipe itself: smooth sine path only, original thickness.
        float strand_y = -0.05
            + 0.07 * sin(uv.x * 2.6 + u_time * 0.12 + phase)
            + 0.025 * sin(uv.x * 6.3 - u_time * 0.07 + phase * 1.7);
        float d = abs(uv.y - strand_y);
        float pipe_glow = exp(-d * d * 260.0); // restored original thickness
        braid += pipe_glow;

        // The sliver: wanders erratically inside the pipe's cross
        // section (small offset from strand_y, driven by noise rather
        // than the pipe's own smooth path), rendered much thinner, and
        // its brightness travels along x over time so it reads as light
        // flowing through the tube rather than a fixed mark.
        float wobble = noise(vec2(uv.x * 3.5 + float(i) * 11.0, u_time * 0.35 + phase))
            + 0.5 * noise(vec2(uv.x * 9.0 - float(i) * 5.0, u_time * 0.6));
        float sliver_y = strand_y + 0.035 * (wobble - 0.75);
        float sd = abs(uv.y - sliver_y);
        float sliver_shape = exp(-sd * sd * 2200.0); // thin sliver, well inside the pipe's width

        float travel = smoothstep(0.3, 1.0,
            sin(uv.x * 4.0 - u_time * (1.2 + float(i) * 0.3) + phase));
        sliver_glow += sliver_shape * travel;
    }
    color += braid_color * braid * 0.45;
    color += sliver_color * sliver_glow * 0.55;

    f_color = vec4(color, 1.0);
}
"""

# --- Logo pass: a real textured plane in 3D, perspective-projected --------

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
uniform float u_glitch_amount;  // 0 = no glitch, >0 = active this frame
uniform float u_glitch_seed;    // changes per glitch event

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

void main() {
    vec2 uv = v_uv;

    // Glitch: for the brief window it's active, a SMALL NUMBER of
    // horizontal bands get a strong horizontal tear (most bands are
    // untouched — sparse-but-strong reads as a much clearer glitch than
    // uniform tiny jitter on every band), plus a noticeable chromatic
    // (RGB) split.
    vec3 tex_rgb;
    if (u_glitch_amount > 0.0) {
        float band = floor(v_uv.y * 14.0);
        float band_rand = hash(vec2(band, u_glitch_seed));
        // Only bands above this threshold tear at all; when they do,
        // the offset is large enough to actually notice.
        float tear = step(0.55, band_rand) * (band_rand - 0.5) * 2.0; // 0, or -1..1
        uv.x += tear * 0.12 * u_glitch_amount;

        float split = 0.012 * u_glitch_amount;  // reduced from 0.02 - less vivid color fringing
        float r = texture(u_logo, vec2(uv.x + split, 1.0 - uv.y)).r;
        float g = texture(u_logo, vec2(uv.x, 1.0 - uv.y)).g;
        float b = texture(u_logo, vec2(uv.x - split, 1.0 - uv.y)).b;
        tex_rgb = vec3(r, g, b);
    } else {
        tex_rgb = texture(u_logo, vec2(uv.x, 1.0 - uv.y)).rgb;
    }

    float lum = dot(tex_rgb, vec3(0.299, 0.587, 0.114));
    // Only the white mark is opaque; the source image's black
    // background is fully transparent so the animated layer behind
    // shows through everywhere except the mark itself.
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


# Object-space (x, y) centers of the logo's three circular characters,
# derived by finding the centroids of the three white shapes in the
# source PNG and converting from pixel coordinates into the same -1..1
# object space the quad geometry uses. Used to spawn a burst directly
# on top of each character rather than from one random point.
CHARACTER_ANCHORS = [(-0.43, 0.0), (0.0, 0.0), (0.43, 0.0)]


class LogoPulseScene(Scene):
    name = "logo_pulse"

    def setup(self, ctx):
        img = Image.open(ASSET_PATH).convert("RGBA")
        self.logo_width, self.logo_height = img.size
        logo_aspect = self.logo_width / self.logo_height

        self.texture = ctx.texture(img.size, 4, img.tobytes())
        self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.texture.build_mipmaps()

        # --- background pass ---
        self.bg_program = ctx.program(vertex_shader=BG_VERTEX, fragment_shader=BG_FRAGMENT)
        self.bg_vao = make_fullscreen_quad_vao(ctx, self.bg_program)

        # --- logo plane pass ---
        self.logo_program = ctx.program(vertex_shader=LOGO_VERTEX, fragment_shader=LOGO_FRAGMENT)
        half_h = 1.0
        half_w = half_h * logo_aspect
        quad = np.array([
            # x, y, z,   u, v
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

        # Camera distance chosen so the plane fills the vertical extent
        # of the frame at zero rotation (see fov/distance relationship).
        self.fov = math.radians(50)
        self.distance = half_h / math.tan(self.fov / 2.0)

        # Background pixel-cloud burst on triggers ("drums" role: kick
        # /snare/snare2, channels 1-3 — unchanged behavior).
        self.particles = ParticleField(ctx, max_particles=3000)

        # Per-character gentle particle burst, triggered by the
        # "percussion" role (hi-hats + percussion, channels 4-7 — kept
        # deliberately separate from "drums"). edge_fade=True so bursts
        # dissolve as they approach the screen edge. Tuned gentle: fewer
        # particles, slower speed, lower saturation than a typical burst.
        self.letter_particles = ParticleField(ctx, max_particles=2000, edge_fade=True)

        self.time = 0.0
        self.pulse = 0.0
        self.camera = None
        self.letter_trigger_pending = False

        # Random, infrequent glitch scheduling: pick a random gap (10-25s)
        # before the next glitch, and a short random duration (0.05-0.15s)
        # for how long it lasts once triggered.
        self.next_glitch_time = np.random.uniform(10.0, 25.0)
        self.glitch_active_until = 0.0
        self.glitch_seed = 0.0

        # Two auto-cycling fractal bloom cells (see BG_FRAGMENT comments):
        # staggered by half the cycle length so one is always fading in
        # while the other fades out, and each gets a fresh random origin
        # whenever its own cycle wraps around.
        self.bloom_cycle_length = 20.0
        self.bloom_cell_start = [0.0, -self.bloom_cycle_length * 0.5]
        self.bloom_cell_origin = [self._random_bloom_origin(), self._random_bloom_origin()]

    def _random_bloom_origin(self):
        return (float(np.random.uniform(-0.55, 0.55)), float(np.random.uniform(-0.45, 0.45)))

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera

        triggered = bool(midi.role_triggers("drums"))
        self.pulse = 1.0 if triggered else self.pulse * 0.95

        # The per-character burst is triggered by "percussion" now, not
        # "drums" — spawning it needs this frame's projection matrix (so
        # it starts exactly on the characters even as the logo tilts),
        # which is only available in render() — so just record that a
        # trigger happened here, and do the actual spawn there.
        self.letter_trigger_pending = bool(midi.role_triggers("percussion"))

        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0
        self.intensity = 0.3 + midi.role_cc("bass", "intensity", 0.0) * 1.5

        self.bloom_cell_phase = []
        for i in range(2):
            elapsed = self.time - self.bloom_cell_start[i]
            if elapsed >= self.bloom_cycle_length:
                self.bloom_cell_start[i] = self.time
                self.bloom_cell_origin[i] = self._random_bloom_origin()
                elapsed = 0.0
            self.bloom_cell_phase.append(elapsed / self.bloom_cycle_length)

        # Random, infrequent, brief glitch: once the scheduled time
        # arrives, activate it for a short random duration, then
        # schedule the next one further out.
        if self.time >= self.next_glitch_time and self.time >= self.glitch_active_until:
            duration = np.random.uniform(0.18, 0.4)
            self.glitch_active_until = self.time + duration
            self.glitch_seed = np.random.uniform(0.0, 1000.0)
            self.next_glitch_time = self.glitch_active_until + np.random.uniform(8.0, 18.0)

        # Background pixel-cloud — unchanged from before.
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

        # 1. Logo plane transform, computed FIRST because the letter-
        # burst spawn below needs it to know where each character
        # currently sits on screen.
        #
        # Continuous sway on all three axes (yaw/pitch/roll) for the
        # ambient tilt; the punch-driven "pulse" on hits itself is kept
        # deliberately small (see below) — a discrete nudge, not a lurch.
        cam_time = cam.time if cam else self.time
        cam_punch = cam.punch if cam else 0.0
        # Punch-driven "pulse" on hits reduced substantially (was 0.55
        # /0.35) — should read as a small, discrete nudge, not a big lurch.
        yaw = 0.75 * math.sin(cam_time * 0.15) + cam_punch * 0.12
        pitch = 0.50 * math.sin(cam_time * 0.11 + 1.0)
        roll = 0.40 * math.sin(cam_time * 0.08 + 2.4) + cam_punch * 0.08

        aspect = target.size[0] / target.size[1]
        proj = _perspective_matrix(self.fov, aspect, 0.1, 10.0)
        model = _rotation_z(roll) @ _rotation_x(pitch) @ _rotation_y(yaw)
        view = _translation_z(-self.distance)
        mvp = proj @ view @ model

        # 2. Gentle letter burst: on a "percussion" trigger, spawn a
        # soft, low-key burst per character, each a different color,
        # positioned exactly where that character currently appears on
        # screen (projected through the same matrix used to draw the
        # tilted logo, so it tracks the camera's rotation correctly).
        if self.letter_trigger_pending:
            anchors = np.array(
                [[x, y, 0.0, 1.0] for x, y in CHARACTER_ANCHORS], dtype="f4"
            )
            clip = (mvp @ anchors.T).T
            ndc = clip[:, :2] / clip[:, 3:4]
            for i, (nx, ny) in enumerate(ndc):
                char_hue = (self.hue + i / 3.0) % 1.0
                self.letter_particles.spawn_burst(
                    origin=(float(nx), float(ny)), hue=char_hue, n=45,
                    speed_range=(0.12, 0.35), life_range=(2.0, 3.5), sat=0.55,
                )
            self.letter_trigger_pending = False

        # 3. Background wash + braid + fractal (fullscreen, full
        # overwrite).
        self.bg_program["u_time"] = self.time
        self.bg_program["u_hue"] = self.hue
        self.bg_program["u_intensity"] = self.intensity
        self.bg_program["u_bloom_origin"] = self.bloom_cell_origin
        self.bg_program["u_bloom_phase"] = self.bloom_cell_phase
        self.bg_program["u_aspect"] = target.size[0] / target.size[1]
        self.bg_vao.render(moderngl.TRIANGLES)

        # 4. Both particle layers drawn BEFORE the logo (additive
        # particles drawn on top of the logo's pure-white pixels would
        # clip invisibly).
        self.particles.render()
        self.letter_particles.render()

        # 5. Logo plane in 3D, using the transform computed above.
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
