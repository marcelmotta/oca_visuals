"""
feedback_trails.py
-------------------
Smoky video-feedback trails, now with:
- Much longer sustain/release (slower decay), so trails linger and pool
  instead of fading quickly.
- Two blobs = two depth layers: a big, slow, soft BACKGROUND wash and a
  smaller, snappier, brighter FOREGROUND blob, in contrasting colors.
- The shared Camera's pan/zoom/rotation is applied to the sampling
  domain each frame, so the accumulated feedback buffer itself drifts,
  zooms and twists over time — feedback loops amplify this beautifully
  over many frames, giving a constantly shifting sense of perspective
  instead of a static frame.
"""

import math
import numpy as np
import moderngl

from scene_base import Scene
from utils import make_fullscreen_quad_vao, hsv_to_rgb_np, compute_work_size

FEEDBACK_VERTEX = """
#version 330
in vec2 in_position;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

FEEDBACK_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_prev_frame;
uniform float u_decay;
uniform float u_zoom;
uniform vec2 u_texel;       // 1/width, 1/height of the work buffer
uniform float u_blur;       // blur radius in texels — bigger = softer

// Background wash (slow, big, soft)
uniform vec2 u_bg_pos;
uniform float u_bg_radius;
uniform vec3 u_bg_color;

// Foreground blob (snappier, brighter, smaller)
uniform vec2 u_fg_pos;
uniform float u_fg_radius;
uniform vec3 u_fg_color;

// Shared camera, applied to the feedback sampling domain.
uniform vec2 u_cam_offset;
uniform float u_cam_rot;
uniform float u_cam_zoom;
uniform float u_aspect;

void main() {
    vec2 centered = v_uv - vec2(0.5);

    // Camera transform: rotate, zoom, pan the domain we sample the
    // previous frame from — this is what makes the whole accumulated
    // image feel like it's being viewed through a slowly moving camera.
    float ca = cos(u_cam_rot);
    float sa = sin(u_cam_rot);
    centered = mat2(ca, -sa, sa, ca) * centered;
    centered -= u_cam_offset * 0.5;
    vec2 sampled_uv = centered * (u_zoom * u_cam_zoom) + vec2(0.5);

    // Soft 5-tap blur on the previous frame — this is what makes each
    // frame blend into a softer version of itself rather than a crisp
    // copy, so detail smooths out and pools together over time.
    vec3 prev = texture(u_prev_frame, sampled_uv).rgb * 0.4;
    prev += texture(u_prev_frame, sampled_uv + vec2(u_texel.x, 0.0) * u_blur).rgb * 0.15;
    prev += texture(u_prev_frame, sampled_uv - vec2(u_texel.x, 0.0) * u_blur).rgb * 0.15;
    prev += texture(u_prev_frame, sampled_uv + vec2(0.0, u_texel.y) * u_blur).rgb * 0.15;
    prev += texture(u_prev_frame, sampled_uv - vec2(0.0, u_texel.y) * u_blur).rgb * 0.15;

    // Aspect correction: without this, the bg/fg blobs (defined via
    // plain UV-space distance) render as ellipses whenever the work
    // buffer isn't square — which it now correctly matches the real
    // output aspect ratio, so this keeps the blobs actually round in
    // that same (correct) proportion.
    float d_bg = length(vec2((v_uv.x - u_bg_pos.x) * u_aspect, v_uv.y - u_bg_pos.y));
    float bg = smoothstep(u_bg_radius, 0.0, d_bg) * 0.5;

    float d_fg = length(vec2((v_uv.x - u_fg_pos.x) * u_aspect, v_uv.y - u_fg_pos.y));
    float fg = smoothstep(u_fg_radius, 0.0, d_fg);

    // This frame's "target" color at this pixel (what the blobs alone
    // would look like, with nothing accumulated).
    vec3 target = u_bg_color * bg + u_fg_color * fg;

    // IMPORTANT: this is a bounded blend toward `target`, NOT an
    // additive accumulation. Previously this was `prev*u_decay + bg +
    // fg`, which — once decay became a genuine slow real-time half-life
    // instead of a fast per-frame multiplier — meant more energy was
    // injected every frame than could ever decay away, so the buffer
    // rocketed to solid white within a second or two. `mix(target,
    // prev, decay)` is mathematically equivalent to `decay*prev +
    // (1-decay)*target`: it still produces the same slow, smeared
    // trailing behavior (decay close to 1 = slow drift toward the new
    // target = long trails), but the result can never exceed the
    // brightest of `target` or `prev`, so it can't blow out to white.
    vec3 result = mix(target, prev, u_decay);
    f_color = vec4(result, 1.0);
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


class FeedbackTrailsScene(Scene):
    name = "feedback_trails"

    def setup(self, ctx):
        self.feedback_program = ctx.program(
            vertex_shader=FEEDBACK_VERTEX, fragment_shader=FEEDBACK_FRAGMENT
        )
        self.blit_program = ctx.program(
            vertex_shader=FEEDBACK_VERTEX, fragment_shader=BLIT_FRAGMENT
        )
        self.feedback_vao = make_fullscreen_quad_vao(ctx, self.feedback_program)
        self.blit_vao = make_fullscreen_quad_vao(ctx, self.blit_program)

        # Sized to match the ACTUAL output aspect ratio (capped for
        # performance), not a hardcoded 16:9 — see particle_burst.py's
        # identical comment for why this matters.
        self.work_size = compute_work_size(self.output_width, self.output_height)
        self.fbo_a = self._make_fbo(ctx)
        self.fbo_b = self._make_fbo(ctx)
        self.reading_from_a = True

        self.time = 0.0
        self.bg_pos = np.array([0.5, 0.5], dtype="f4")
        self.fg_pos = np.array([0.5, 0.5], dtype="f4")
        self.pulse = 0.0
        self.camera = None

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

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera

        intensity = 0.2 + midi.role_cc("bass", "intensity", 0.0) * 0.7

        # Background wash: big, slow, wide orbit — noticeably slower
        # than before for a calmer, more gradual motion.
        self.bg_pos[0] = 0.5 + 0.42 * math.sin(self.time * 0.09 * intensity)
        self.bg_pos[1] = 0.5 + 0.42 * math.cos(self.time * 0.065 * intensity + 0.7)

        # Foreground blob: still the "faster" layer, but slowed down too.
        self.fg_pos[0] = 0.5 + 0.30 * math.sin(self.time * 0.30 * intensity + 2.0)
        self.fg_pos[1] = 0.5 + 0.30 * math.cos(self.time * 0.22 * intensity)

        autonomous_hue = (self.time * 0.01) % 1.0
        hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0
        accent_hue = (hue + 0.5) % 1.0
        self.bg_color = hsv_to_rgb_np(np.array([hue]), np.array([0.55]), np.array([0.8]))[0]
        self.fg_color = hsv_to_rgb_np(np.array([accent_hue]), np.array([0.75]), np.array([1.0]))[0]

        triggered = bool(midi.role_triggers("drums"))
        self.pulse = 1.0 if triggered else getattr(self, "pulse", 0.0) * 0.95

        feedback_cc = midi.role_cc("bass", "feedback_amount", 0.5)
        # Decay was previously applied as a flat per-FRAME multiplier
        # (e.g. 0.95), which compounds with frame rate: at 60fps that's
        # 0.95^60 ≈ 0.05 remaining after just one second — a "slow-
        # looking" number that was actually fading almost everything
        # within a second, which is why it still looked choppy/fast.
        # Fixed: define persistence as a HALF-LIFE IN SECONDS (how long
        # until brightness drops to half), then derive the correct
        # per-frame factor from the actual elapsed time (dt) each frame,
        # so it behaves consistently regardless of frame rate.
        half_life_seconds = 2.0 + feedback_cc * 5.0  # 2s (cc=0) .. 7s (cc=1)
        decay_per_second = 0.5 ** (1.0 / half_life_seconds)
        self.decay = decay_per_second ** dt
        # Blur radius (in texels) applied to the previous frame each pass
        # — bigger = softer, hazier accumulation.
        self.blur_amount = 2.5

    def render(self, target):
        ctx = self.ctx
        src_fbo = self.fbo_a if self.reading_from_a else self.fbo_b
        dst_fbo = self.fbo_b if self.reading_from_a else self.fbo_a

        dst_fbo.use()
        src_fbo.color_attachments[0].use(location=0)
        self.feedback_program["u_prev_frame"] = 0
        self.feedback_program["u_decay"] = float(max(self.decay - self.pulse * 0.05, 0.0))
        self.feedback_program["u_zoom"] = 0.997
        self.feedback_program["u_texel"] = (1.0 / self.work_size[0], 1.0 / self.work_size[1])
        self.feedback_program["u_blur"] = self.blur_amount
        self.feedback_program["u_bg_pos"] = tuple(self.bg_pos)
        self.feedback_program["u_bg_radius"] = 0.30
        self.feedback_program["u_bg_color"] = tuple(float(c) for c in self.bg_color)
        self.feedback_program["u_fg_pos"] = tuple(self.fg_pos)
        self.feedback_program["u_fg_radius"] = 0.09 + self.pulse * 0.04
        self.feedback_program["u_fg_color"] = tuple(float(c) for c in self.fg_color)

        cam = self.camera
        self.feedback_program["u_cam_offset"] = tuple(cam.offset) if cam else (0.0, 0.0)
        self.feedback_program["u_cam_rot"] = cam.rotation * 0.3 if cam else 0.0
        self.feedback_program["u_cam_zoom"] = cam.zoom if cam else 1.0
        self.feedback_program["u_aspect"] = self.work_size[0] / self.work_size[1]
        self.feedback_vao.render(moderngl.TRIANGLES)

        target.use()
        dst_fbo.color_attachments[0].use(location=0)
        self.blit_program["u_tex"] = 0
        self.blit_vao.render(moderngl.TRIANGLES)

        self.reading_from_a = not self.reading_from_a
