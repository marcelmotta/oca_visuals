"""
particle_burst.py
------------------
A constantly-alive field of points with:
- Longer sustain/release: particles live much longer and fade slowly,
  and the trail buffer decays slowly too, so motion lingers instead of
  popping.
- Richer, evolving color: hue drifts continuously on its own, plus
  foreground bursts use a complementary accent color against the
  ambient background for real color contrast (not just one hue knob).
- Two depth layers: dim, slow "background" ambient particles further
  from camera (z < 0), and bright, larger "foreground" particles from
  triggers (z > 0) closer to camera — each layer moves at a different
  rate under the shared camera for a genuine parallax depth cue.
- Automated perspective: the shared Camera's pan/zoom/rotation is
  applied per-vertex, scaled by each particle's depth (parallax), so
  the whole field visibly shifts perspective over time and punches on
  drum hits — this is on top of, not instead of, the particles' own
  motion.
"""

import math
import os
import numpy as np
import moderngl

from scene_base import Scene
from utils import make_fullscreen_quad_vao, hsv_to_rgb_np, compute_work_size
from config import TRIGGER_NOTE_LOW, TRIGGER_NOTE_HIGH
from hollow_logo import HollowLogoOverlay

MAX_PARTICLES = 36000

# Every SEQTRAK/Ableton instrument channel gets its own color and burst
# character — a rough rainbow spread from warm/percussive to
# cool/melodic, so a hit's color tells you which instrument fired it.
# "hue" is 0-1 (0=red, 0.33=green, 0.66=blue). "mode": "burst" spawns a
# directional radial burst at a screen position; "ambient" adds a few
# particles into the slow-drifting background field instead (used for
# the sampler, which tends to carry one-shot texture/atmosphere hits
# rather than rhythmic ones). "position": "note" maps note pitch to a
# screen x position (good for anything played melodically); "random"
# just picks a random x (good for fixed-pitch drum channels).
CHANNEL_VISUAL_STYLE = {
    "kick":    dict(hue=0.00, mode="burst", position="random", n=500,
                     speed=(0.35, 1.10), life=(3.0, 5.5), sat=0.95),  # red
    "snare":   dict(hue=0.09, mode="burst", position="random", n=350,
                     speed=(0.35, 0.95), life=(2.5, 4.5), sat=0.90),  # orange
    "hihat":   dict(hue=0.55, mode="burst", position="random", n=120,
                     speed=(0.55, 0.95), life=(1.3, 2.2), sat=0.70),  # cyan sparkle
    "perc":    dict(hue=0.33, mode="burst", position="random", n=220,
                     speed=(0.40, 0.85), life=(2.0, 3.5), sat=0.85),  # green
    "bass":    dict(hue=0.72, mode="burst", position="note", n=300,
                     speed=(0.20, 0.55), life=(3.0, 6.0), sat=0.90),  # deep blue/purple
    "synth2":  dict(hue=0.85, mode="burst", position="note", n=200,
                     speed=(0.45, 0.55), life=(2.0, 3.5), sat=0.65),  # magenta ring
    "pads":    dict(hue=0.93, mode="burst", position="note", n=150,
                     speed=(0.18, 0.35), life=(3.0, 5.0), sat=0.55),  # pink, slow drift
    "sampler": dict(hue=0.14, mode="ambient", position="random", n=30,
                     speed=(0, 0), life=(0, 0), sat=0.4),             # amber twinkle
}

POINT_VERTEX = """
#version 330
in vec3 in_position;
in float in_life01;
in vec3 in_color;

out float v_life01;
out vec3 v_color;

uniform vec2 u_cam_offset;
uniform float u_cam_zoom;
uniform float u_cam_rot;
uniform float u_aspect;

void main() {
    v_life01 = in_life01;
    v_color = in_color;

    // Depth (z, -1..1) drives BOTH how strongly the camera affects this
    // particle (parallax) and its rendered size/brightness — this is
    // what makes background vs foreground actually read as layers.
    float depth01 = (in_position.z + 1.0) * 0.5;       // 0 = far bg, 1 = near fg
    float parallax = mix(0.35, 1.15, depth01);

    vec2 p = in_position.xy;
    float angle = u_cam_rot * parallax;
    float ca = cos(angle);
    float sa = sin(angle);
    p = mat2(ca, -sa, sa, ca) * p;
    p *= mix(1.0, u_cam_zoom, parallax);
    p -= u_cam_offset * parallax;

    // Aspect correction, applied LAST (after the simulation/camera
    // transform above, which assumes a symmetric x/y world and should
    // stay that way): without this, the swirl and radial bursts — which
    // move equally in x and y in world space — render as ellipses on
    // any screen that isn't exactly square.
    p.x /= u_aspect;

    gl_Position = vec4(p, 0.0, 1.0);

    float depth_scale = mix(0.6, 2.0, depth01);
    // Notably bigger baseline than before — the field should read as
    // dense and unmistakable, not a scatter of faint dots.
    gl_PointSize = (14.0 + 42.0 * v_life01) * depth_scale;
}
"""

POINT_FRAGMENT = """
#version 330
in float v_life01;
in vec3 v_color;
out vec4 f_color;

void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float dist = length(centered);
    float alpha = smoothstep(0.5, 0.0, dist) * v_life01;
    if (alpha <= 0.001) discard;
    f_color = vec4(v_color, alpha);
}
"""

FULLSCREEN_VERTEX = """
#version 330
in vec2 in_position;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

DECAY_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_tex;
uniform float u_decay;
void main() {
    f_color = texture(u_tex, v_uv) * u_decay;
}
"""

BLIT_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_tex;
void main() {
    f_color = texture(u_tex, v_uv);
}
"""


class ParticleBurstScene(Scene):
    name = "particle_burst"

    def setup(self, ctx):
        self.point_program = ctx.program(
            vertex_shader=POINT_VERTEX, fragment_shader=POINT_FRAGMENT
        )
        self.decay_program = ctx.program(
            vertex_shader=FULLSCREEN_VERTEX, fragment_shader=DECAY_FRAGMENT
        )
        self.blit_program = ctx.program(
            vertex_shader=FULLSCREEN_VERTEX, fragment_shader=BLIT_FRAGMENT
        )
        self.decay_vao = make_fullscreen_quad_vao(ctx, self.decay_program)
        self.blit_vao = make_fullscreen_quad_vao(ctx, self.blit_program)

        self.position = np.zeros((MAX_PARTICLES, 3), dtype="f4")
        self.velocity = np.zeros((MAX_PARTICLES, 3), dtype="f4")
        self.life = np.zeros(MAX_PARTICLES, dtype="f4")
        self.max_life = np.ones(MAX_PARTICLES, dtype="f4")
        self.color = np.zeros((MAX_PARTICLES, 3), dtype="f4")
        self.cursor = 0

        self.vbo = ctx.buffer(reserve=MAX_PARTICLES * 7 * 4, dynamic=True)
        self.vao = ctx.vertex_array(
            self.point_program,
            [(self.vbo, "3f 1f 3f", "in_position", "in_life01", "in_color")],
        )

        # Sized to match the ACTUAL output aspect ratio (capped for
        # performance), not a hardcoded 16:9 — otherwise this buffer
        # gets stretched non-uniformly the moment the real display
        # isn't exactly 16:9, which squashes/distorts everything in it.
        self.work_size = compute_work_size(self.output_width, self.output_height)
        self.fbo_a = self._make_fbo(ctx)
        self.fbo_b = self._make_fbo(ctx)
        self.reading_from_a = True

        self.emit_accum = 0.0
        self.time = 0.0
        self.camera = None

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.logo_overlay = HollowLogoOverlay(ctx, project_root)

    def _make_fbo(self, ctx):
        tex = ctx.texture(self.work_size, 4)
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        fbo = ctx.framebuffer(color_attachments=[tex])
        fbo.use()
        ctx.clear(0.0, 0.0, 0.0, 1.0)
        return fbo

    def resize(self, width, height):
        super().resize(width, height)
        new_work_size = compute_work_size(width, height)
        if new_work_size != self.work_size:
            self.work_size = new_work_size
            self.fbo_a = self._make_fbo(self.ctx)
            self.fbo_b = self._make_fbo(self.ctx)

    def _next_indices(self, n):
        idx = (np.arange(n) + self.cursor) % MAX_PARTICLES
        self.cursor = (self.cursor + n) % MAX_PARTICLES
        return idx

    def _spawn_ambient(self, n, hue):
        """Background layer: dim, slow, always-on — sits behind bursts."""
        idx = self._next_indices(n)
        self.position[idx] = np.stack([
            np.random.uniform(-1.0, 1.0, n),
            np.random.uniform(-1.0, 1.0, n),
            np.random.uniform(-1.0, -0.2, n),  # background depth range
        ], axis=-1)
        theta = np.random.uniform(0, 2 * np.pi, n)
        speed = np.random.uniform(0.02, 0.09, n)
        self.velocity[idx] = np.stack([
            np.cos(theta) * speed, np.sin(theta) * speed,
            np.random.uniform(-0.02, 0.02, n),
        ], axis=-1)
        # Much longer sustain: ambient particles now live 6-12 seconds.
        self.life[idx] = np.random.uniform(6.0, 12.0, n)
        self.max_life[idx] = self.life[idx]
        hues = (hue + np.random.uniform(-0.10, 0.10, n)) % 1.0
        self.color[idx] = hsv_to_rgb_np(hues, 0.45, 0.85)

    def _spawn_burst(self, origin, hue, n, speed_low, speed_high,
                      life_low, life_high, sat=0.85):
        """Foreground layer: bright, larger, closer to camera.

        `origin` is a full (x, y, z) tuple — each pop's starting point is
        now randomized across all three axes (previously y was always
        pinned to 0 and z only varied per-particle around a fixed
        band), so successive pops visibly start from different places
        in the field rather than always the same horizontal line.
        """
        idx = self._next_indices(n)
        theta = np.random.uniform(0, 2 * np.pi, n)
        phi = np.random.uniform(0, np.pi, n)
        speed = np.random.uniform(speed_low, speed_high, n)
        dirs = np.stack([
            np.sin(phi) * np.cos(theta),
            np.sin(phi) * np.sin(theta),
            np.cos(phi),
        ], axis=-1)
        ox, oy, oz = origin
        # Individual particles in the pop jitter slightly around the
        # pop's own (x, y, z) origin before diffusing outward, so the
        # burst has a little volume at birth rather than starting from
        # one infinitesimal point.
        jitter = np.random.uniform(-0.05, 0.05, (n, 3)).astype("f4")
        self.position[idx] = np.array([ox, oy, oz], dtype="f4") + jitter
        np.clip(self.position[idx, 2], -1.0, 1.0, out=self.position[idx, 2])
        self.velocity[idx] = dirs * speed[:, None]
        # Longer sustain: bursts now live 2.5-5 seconds instead of ~2s.
        self.life[idx] = np.random.uniform(life_low, life_high, n)
        self.max_life[idx] = self.life[idx]
        hues = (hue + np.random.uniform(-0.04, 0.04, n)) % 1.0
        self.color[idx] = hsv_to_rgb_np(hues, sat, 1.0)

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera
        self.logo_overlay.update(dt)

        bass_intensity = midi.role_cc("bass", "intensity", 0.5)
        flow_speed = 0.5 + bass_intensity * 1.8

        # Color keeps evolving on its own even with no hands on a knob —
        # the "keys" CC shifts it further on top of a slow, continuous
        # autonomous drift, so the palette is always alive.
        autonomous_hue = (self.time * 0.008) % 1.0
        keys_hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0

        # 1. Continuous ambient background stream — higher base rate for
        # a noticeably denser field than before.
        base_rate = 45.0 + 90.0 * bass_intensity
        self.emit_accum += dt * base_rate
        spawn_n = int(self.emit_accum)
        if spawn_n > 0:
            self._spawn_ambient(min(spawn_n, 400), keys_hue)
            self.emit_accum -= spawn_n

        # 2. Each instrument channel gets its OWN color and burst
        # character, so you can visually tell what triggered a burst
        # instead of everything sharing one or two hues. Roughly a
        # rainbow spread across the SEQTRAK's 11 channels, ordered by
        # pitch (low/percussive -> warm, high/melodic -> cool):
        for role, style in CHANNEL_VISUAL_STYLE.items():
            for note in midi.role_triggers(role):
                if style["mode"] == "ambient":
                    self._spawn_ambient(style["n"], style["hue"])
                    continue
                if style["position"] == "note":
                    span = max(TRIGGER_NOTE_HIGH - TRIGGER_NOTE_LOW, 1)
                    frac = np.clip((note - TRIGGER_NOTE_LOW) / span, 0.0, 1.0)
                    origin_x = (frac * 2.0 - 1.0) * 0.95
                else:
                    origin_x = np.random.uniform(-0.95, 0.95)
                # Y and Z are now randomized per pop too (previously Y
                # was always 0 and Z only varied per-particle around a
                # fixed band) — each pop now genuinely starts from a
                # different point across all three axes. Widened toward
                # the screen edges (was +-0.6) so bursts reach further
                # out instead of clustering toward the center.
                origin_y = np.random.uniform(-0.85, 0.85)
                origin_z = np.random.uniform(-0.2, 1.0)
                self._spawn_burst(
                    (origin_x, origin_y, origin_z), style["hue"], n=style["n"],
                    speed_low=style["speed"][0], speed_high=style["speed"][1],
                    life_low=style["life"][0], life_high=style["life"][1],
                    sat=style["sat"],
                )

        # Integrate motion: drag + gentle swirl + light gravity to center.
        alive = self.life > 0.0
        angle = np.arctan2(self.position[:, 1], self.position[:, 0] + 1e-6) + math.pi / 2
        swirl_dir = np.stack([np.cos(angle), np.sin(angle), np.zeros_like(angle)], axis=-1)
        swirl_strength = 0.15 * bass_intensity

        self.velocity[alive] += swirl_dir[alive] * swirl_strength * dt
        self.velocity[alive] += (-self.position[alive]) * 0.04 * dt

        # Erratic jitter during the fade-out: as a particle nears the end
        # of its life, it gets an increasingly chaotic random kick each
        # frame instead of just smoothly dying out — it darts around
        # right before it disappears rather than calmly fading in place.
        life01_now = np.divide(self.life, np.maximum(self.max_life, 1e-5))
        near_death = np.clip(1.0 - life01_now, 0.0, 1.0) ** 3  # only kicks in near the very end
        jitter = np.random.uniform(-1.0, 1.0, self.position.shape).astype("f4")
        self.velocity[alive] += jitter[alive] * near_death[alive, None] * 2.5 * dt

        self.velocity[alive] *= 0.988
        self.position[alive] += self.velocity[alive] * dt * flow_speed
        np.clip(self.position[:, 2], -1.0, 1.0, out=self.position[:, 2])
        self.life[alive] -= dt
        self.life[~alive] = 0.0

    def render(self, target):
        ctx = self.ctx
        src = self.fbo_a if self.reading_from_a else self.fbo_b
        dst = self.fbo_b if self.reading_from_a else self.fbo_a

        dst.use()
        src.color_attachments[0].use(location=0)
        self.decay_program["u_tex"] = 0
        # Slower decay than before (0.86 -> 0.93): trails linger much
        # longer, giving a real "release" instead of a quick pop-out.
        self.decay_program["u_decay"] = 0.93
        self.decay_vao.render(moderngl.TRIANGLES)

        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
        life01 = np.clip(self.life / np.maximum(self.max_life, 1e-5), 0.0, 1.0)
        # Erratic flicker during the last ~30% of life: instead of a
        # smooth linear fade, brightness stutters randomly frame to
        # frame right before a particle disappears.
        near_death_mask = life01 < 0.3
        flicker = np.random.uniform(0.25, 1.0, life01.shape).astype("f4")
        life01_render = np.where(near_death_mask, life01 * flicker, life01)
        data = np.concatenate([self.position, life01_render[:, None], self.color], axis=1).astype("f4")
        self.vbo.write(data.tobytes())

        cam = self.camera
        self.point_program["u_cam_offset"] = tuple(cam.offset) if cam else (0.0, 0.0)
        self.point_program["u_cam_zoom"] = cam.zoom if cam else 1.0
        self.point_program["u_cam_rot"] = cam.rotation if cam else 0.0
        self.point_program["u_aspect"] = self.work_size[0] / self.work_size[1]
        self.vao.render(moderngl.POINTS, vertices=MAX_PARTICLES)
        ctx.disable(moderngl.BLEND)

        target.use()
        dst.color_attachments[0].use(location=0)
        self.blit_program["u_tex"] = 0
        self.blit_vao.render(moderngl.TRIANGLES)

        self.reading_from_a = not self.reading_from_a

        # Centered white hollow-outline logo, drawn last so it sits on
        # top of the particle field.
        self.logo_overlay.render(target)

    def teardown(self):
        self.logo_overlay.release()
