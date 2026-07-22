"""
particle_field.py
------------------
A small, self-contained point-cloud burst system that any scene can
embed on top of its own rendering — not a full Scene itself, just a
reusable "spawn a burst of glowing points" object. Currently used by
kaleidoscope_video.py for the drifting sakura petal accents.

(particle_burst.py, the full scene, has its own more elaborate particle
system with persistent trail buffers and depth layers — this is a
lighter-weight version meant to be layered on top of other content.)
"""

import numpy as np
import moderngl

from utils import hsv_to_rgb_np

VERTEX_SHADER = """
#version 330
in vec3 in_position;
in float in_life01;
in vec3 in_color;

out float v_life01;
out vec3 v_color;
out vec2 v_pos;

void main() {
    v_life01 = in_life01;
    v_color = in_color;
    v_pos = in_position.xy;
    gl_Position = vec4(in_position.xy, 0.0, 1.0);
    gl_PointSize = (4.0 + 16.0 * v_life01);
}
"""

FRAGMENT_SHADER = """
#version 330
in float v_life01;
in vec3 v_color;
in vec2 v_pos;
out vec4 f_color;

// When u_edge_fade is 1.0, particles dissolve out as they approach the
// edge of the screen (in addition to their normal life-based fade).
// When 0.0 (the default), behavior is unchanged from before.
uniform float u_edge_fade;

void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float dist = length(centered);
    float shape_alpha = smoothstep(0.5, 0.0, dist);

    float edge = max(abs(v_pos.x), abs(v_pos.y));
    float edge_fade_factor = 1.0 - smoothstep(0.55, 1.0, edge);
    float edge_factor = mix(1.0, edge_fade_factor, u_edge_fade);

    float alpha = shape_alpha * v_life01 * edge_factor;
    if (alpha <= 0.001) discard;
    f_color = vec4(v_color, alpha);
}
"""


class ParticleField:
    def __init__(self, ctx, max_particles=3000, edge_fade=False):
        self.ctx = ctx
        self.max_particles = max_particles
        # edge_fade=True makes particles dissolve as they approach the
        # screen edge (used for the logo scenes' per-character letter
        # bursts); False (default) preserves the original behavior
        # unchanged (used for the existing "background pixel-cloud").
        self.edge_fade = 1.0 if edge_fade else 0.0
        self.program = ctx.program(
            vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER
        )
        self.position = np.zeros((max_particles, 3), dtype="f4")
        self.velocity = np.zeros((max_particles, 3), dtype="f4")
        self.life = np.zeros(max_particles, dtype="f4")
        self.max_life = np.ones(max_particles, dtype="f4")
        self.color = np.zeros((max_particles, 3), dtype="f4")
        self.cursor = 0

        self.vbo = ctx.buffer(reserve=max_particles * 7 * 4, dynamic=True)
        self.vao = ctx.vertex_array(
            self.program,
            [(self.vbo, "3f 1f 3f", "in_position", "in_life01", "in_color")],
        )

    def spawn_burst(self, origin=(0.0, 0.0), hue=0.0, n=150,
                     speed_range=(0.3, 0.9), life_range=(1.5, 3.0), sat=0.85):
        n = min(n, self.max_particles)
        idx = (np.arange(n) + self.cursor) % self.max_particles
        self.cursor = (self.cursor + n) % self.max_particles

        theta = np.random.uniform(0, 2 * np.pi, n)
        phi = np.random.uniform(0, np.pi, n)
        speed = np.random.uniform(speed_range[0], speed_range[1], n)
        dirs = np.stack([
            np.sin(phi) * np.cos(theta),
            np.sin(phi) * np.sin(theta),
            np.cos(phi),
        ], axis=-1)

        self.position[idx] = np.array([origin[0], origin[1], 0.0], dtype="f4")
        self.velocity[idx] = dirs * speed[:, None]
        self.life[idx] = np.random.uniform(life_range[0], life_range[1], n)
        self.max_life[idx] = self.life[idx]
        hues = (hue + np.random.uniform(-0.05, 0.05, n)) % 1.0
        self.color[idx] = hsv_to_rgb_np(hues, sat, 1.0)

    def spawn_ring_burst(self, origin=(0.0, 0.0), hue=0.0, n=90,
                          speed=0.9, life=1.4, sat=0.9):
        """Spawns a coherent expanding RING of particles (all evenly
        spaced in angle, all moving outward at the same speed, all
        sharing the same lifespan) instead of a scattered/directional
        burst — this reads clearly as a single pulsing ring rather than
        a spray of individual points, which is what makes it feel like a
        pulsation rather than an explosion.
        """
        n = min(n, self.max_particles)
        idx = (np.arange(n) + self.cursor) % self.max_particles
        self.cursor = (self.cursor + n) % self.max_particles

        theta = np.linspace(0.0, 2 * np.pi, n, endpoint=False)
        dirs = np.stack([np.cos(theta), np.sin(theta), np.zeros(n)], axis=-1)

        self.position[idx] = np.array([origin[0], origin[1], 0.0], dtype="f4")
        # Same speed and same life for every particle in the ring — this
        # is what keeps them moving together as a single coherent ring
        # instead of spreading into a scattered cloud over time.
        self.velocity[idx] = dirs * speed
        self.life[idx] = life
        self.max_life[idx] = life
        hues = (hue + np.random.uniform(-0.02, 0.02, n)) % 1.0
        self.color[idx] = hsv_to_rgb_np(hues, sat, 1.0)

    def update(self, dt, drag=0.985):
        alive = self.life > 0.0
        self.velocity[alive] *= drag
        self.position[alive] += self.velocity[alive] * dt
        self.life[alive] -= dt
        self.life[~alive] = 0.0

    def render(self):
        """Draws additively into whatever framebuffer is currently bound."""
        ctx = self.ctx
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE
        life01 = np.clip(self.life / np.maximum(self.max_life, 1e-5), 0.0, 1.0)
        data = np.concatenate([self.position, life01[:, None], self.color], axis=1).astype("f4")
        self.vbo.write(data.tobytes())
        self.program["u_edge_fade"] = self.edge_fade
        self.vao.render(moderngl.POINTS, vertices=self.max_particles)
        ctx.disable(moderngl.BLEND)
