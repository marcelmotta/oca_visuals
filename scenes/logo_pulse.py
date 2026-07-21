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
2. A point-cloud burst every time the logo scene gets a drum-channel
   trigger (via the shared, reusable ParticleField). Drawn BEFORE the
   logo plane, not after — the logo's mark is pure white, and additive
   particles drawn on top of already-saturated white clip to white and
   disappear, which was the original bug.
3. A translucent, glowing braid of slowly-moving strands across the
   horizon, and a slowly-morphing Julia-set fractal layered beneath the
   noise wash, both woven into the animated background for depth.

LAYERING: background (fractal + noise wash + braid) is the "far" layer
and barely reacts to camera movement; the particle burst sits above
that; the logo plane is the tilting 3D "subject" drawn last, occluding
whatever falls behind its opaque shapes.
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
uniform vec2 u_cam_offset;
uniform float u_cam_rot;
uniform float u_cam_zoom;

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
    vec2 uv = v_uv * 2.0 - 1.0;

    // Background barely moves with the camera (it's the "far" layer) —
    // only a gentle fraction of the camera's pan/zoom/rotate reaches it.
    float ca = cos(u_cam_rot * 0.3);
    float sa = sin(u_cam_rot * 0.3);
    vec2 cam_uv = mat2(ca, -sa, sa, ca) * uv;
    cam_uv *= mix(1.0, u_cam_zoom, 0.4);
    cam_uv -= u_cam_offset * 0.3;

    float n1 = noise(cam_uv * 1.1 + u_time * u_intensity * 0.06);
    float n2 = noise(cam_uv * 2.3 - u_time * u_intensity * 0.04 + 5.0);
    float hueA = fract(u_hue + n1 * 0.18);
    float hueB = fract(u_hue + 0.4 + n2 * 0.18);
    vec3 colorA = hsv2rgb(vec3(hueA, 0.75, 0.10 + 0.18 * n1));
    vec3 colorB = hsv2rgb(vec3(hueB, 0.65, 0.06 + 0.12 * n2));
    vec3 color = colorA + colorB * 0.6;

    // Fractal layer: sits furthest back, adding fine self-similar detail
    // and a sense of depth beneath the noise wash. `c` drifts slowly
    // around a small circle so the pattern continuously morphs — that
    // rotation speed (u_time * 0.03) is the "bloom speed" and is left
    // unchanged; only the spatial scale/opacity below were increased so
    // the pattern itself is far more visually present.
    vec2 julia_c = 0.7885 * vec2(cos(u_time * 0.03), sin(u_time * 0.03));
    float f = julia(cam_uv * 1.35, julia_c);
    vec3 fractal_color = hsv2rgb(vec3(fract(u_hue + 0.15 + f * 0.3), 0.65, f * f));
    color += fractal_color * 0.55;

    // Translucent, glowing braid across the horizon: three strands
    // weaving slowly, each a soft sine curve offset in phase so they
    // cross over one another like a braid.
    vec3 braid_color = hsv2rgb(vec3(fract(u_hue + 0.55), 0.45, 1.0));
    float braid = 0.0;
    for (int i = 0; i < 3; i++) {
        float phase = float(i) * 2.094395; // 2*pi/3 apart
        float strand_y = -0.05
            + 0.07 * sin(cam_uv.x * 2.6 + u_time * 0.12 + phase)
            + 0.025 * sin(cam_uv.x * 6.3 - u_time * 0.07 + phase * 1.7);
        float d = abs(cam_uv.y - strand_y);
        braid += exp(-d * d * 260.0);
    }
    color += braid_color * braid * 0.45;

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

void main() {
    vec4 tex = texture(u_logo, vec2(v_uv.x, 1.0 - v_uv.y));
    float lum = dot(tex.rgb, vec3(0.299, 0.587, 0.114));
    // Only the white mark is opaque; the source image's black
    // background is fully transparent so the animated layer behind
    // shows through everywhere except the mark itself.
    float alpha = smoothstep(0.35, 0.55, lum);
    if (alpha <= 0.01) discard;
    f_color = vec4(tex.rgb, alpha);
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

        # Particle burst on triggers, layered on top of everything.
        # "particles" is the original background pixel-cloud (unchanged
        # behavior). "letter_particles" is a separate field for bursts
        # that start on each character and dissolve toward the screen
        # edges (edge_fade=True) — kept as its own instance so the
        # original background pixel-cloud's behavior stays exactly as
        # it was.
        self.particles = ParticleField(ctx, max_particles=3000)
        self.letter_particles = ParticleField(ctx, max_particles=3000, edge_fade=True)

        self.time = 0.0
        self.pulse = 0.0
        self.camera = None
        self.letter_trigger_pending = False

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera

        triggered = bool(midi.role_triggers("drums"))
        self.pulse = 1.0 if triggered else self.pulse * 0.95
        # Spawning the letter bursts needs this frame's projection matrix
        # (so bursts start exactly on the characters even as the logo
        # tilts), which is only available in render() — so just record
        # that a trigger happened here, and do the actual spawn there.
        self.letter_trigger_pending = triggered

        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0
        self.intensity = 0.3 + midi.role_cc("bass", "intensity", 0.0) * 1.5

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

        # 1. Background wash + braid (fullscreen, full overwrite).
        self.bg_program["u_time"] = self.time
        self.bg_program["u_hue"] = self.hue
        self.bg_program["u_intensity"] = self.intensity
        self.bg_program["u_cam_offset"] = tuple(cam.offset) if cam else (0.0, 0.0)
        self.bg_program["u_cam_rot"] = cam.rotation if cam else 0.0
        self.bg_program["u_cam_zoom"] = cam.zoom if cam else 1.0
        self.bg_vao.render(moderngl.TRIANGLES)

        # 2. Logo plane transform, computed here (not just at draw time)
        # because the letter-burst spawn below needs it to know where
        # each character currently sits on screen.
        #
        # More aggressive rotation on all three axes than before:
        # yaw/pitch amplitudes roughly doubled, and a new Z-axis roll
        # added (there was no roll at all previously). Drum punches now
        # kick yaw AND roll harder for a snappier per-hit tilt.
        cam_time = cam.time if cam else self.time
        cam_punch = cam.punch if cam else 0.0
        yaw = 0.75 * math.sin(cam_time * 0.15) + cam_punch * 0.55
        pitch = 0.50 * math.sin(cam_time * 0.11 + 1.0)
        roll = 0.40 * math.sin(cam_time * 0.08 + 2.4) + cam_punch * 0.35

        aspect = target.size[0] / target.size[1]
        proj = _perspective_matrix(self.fov, aspect, 0.1, 10.0)
        model = _rotation_z(roll) @ _rotation_x(pitch) @ _rotation_y(yaw)
        view = _translation_z(-self.distance)
        mvp = proj @ view @ model

        # 3. Letter bursts: on a trigger, spawn one burst per character,
        # each a different color, positioned exactly where that
        # character currently appears on screen (projected through the
        # same matrix used to draw the tilted logo, so it tracks the
        # camera's rotation correctly instead of assuming a fixed pose).
        if self.letter_trigger_pending:
            anchors = np.array(
                [[x, y, 0.0, 1.0] for x, y in CHARACTER_ANCHORS], dtype="f4"
            )
            clip = (mvp @ anchors.T).T
            ndc = clip[:, :2] / clip[:, 3:4]
            for i, (nx, ny) in enumerate(ndc):
                char_hue = (self.hue + i / 3.0) % 1.0
                self.letter_particles.spawn_ring_burst(
                    origin=(float(nx), float(ny)), hue=char_hue,
                    n=120, speed=1.0, life=1.6, sat=0.9,
                )
            self.letter_trigger_pending = False

        # 4. Both particle layers drawn BEFORE the logo (see the note in
        # the background pixel-cloud comment above — additive particles
        # drawn on top of the logo's pure-white pixels would clip
        # invisibly).
        self.particles.render()
        self.letter_particles.render()

        # 5. Logo plane in 3D, using the transform computed above.
        mvp_col_major = mvp.T.astype("f4").copy()

        self.texture.use(location=0)
        self.logo_program["u_logo"] = 0
        self.logo_program["u_mvp"].write(mvp_col_major.tobytes())

        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.logo_vao.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)
