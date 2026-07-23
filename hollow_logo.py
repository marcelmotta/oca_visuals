"""
hollow_logo.py
---------------
A centered, white OUTLINE-ONLY rendering of the spin-loop video logo —
just the edges of the shapes, not filled — meant as a light overlay on
top of scenes that are already busy with their own content (particles,
feedback trails, noise), rather than the full solid/3D treatment used
in scenes 4 and 5.

TECHNIQUE: at each pixel, sample a binary inside/outside mask (video
luminance thresholded) at the pixel itself and at a ring of points
around it at radius OUTLINE_THICKNESS. If any of those ring samples
disagree with the center sample, this pixel is within OUTLINE_THICKNESS
of a shape boundary, so it's part of the outline and drawn white;
everything else is discarded (fully transparent), letting the scene
underneath show through.
"""

import moderngl

from utils import make_fullscreen_quad_vao
from video_texture import VideoTexture

VIDEO_PATH_SUFFIX = ("assets", "oca_spin_loop_v3.mp4")

# How big the logo appears on screen: half-height in the same aspect-
# corrected uv units the rest of the project uses (screen spans roughly
# -1..1 vertically). 0.55 leaves a visible margin around it.
DISPLAY_HALF_HEIGHT = 0.55

# Outline thickness in the same uv units. Kept small for a crisp,
# visible-but-not-heavy line — tune this if it looks too thick/thin.
# (Reduced 30% from the original 0.012 per feedback that it read too thick.)
OUTLINE_THICKNESS = 0.0084

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
uniform float u_aspect;
uniform float u_video_aspect;
uniform float u_display_half_height;
uniform float u_outline_thickness;

float sampleMask(vec2 screen_uv) {
    vec2 box = screen_uv / vec2(u_display_half_height * u_video_aspect, u_display_half_height);
    if (box.x < -1.0 || box.x > 1.0 || box.y < -1.0 || box.y > 1.0) return 0.0;
    vec2 sample_uv = box * 0.5 + 0.5;
    vec3 c = texture(u_video, vec2(sample_uv.x, 1.0 - sample_uv.y)).rgb;
    float lum = dot(c, vec3(0.299, 0.587, 0.114));
    return step(0.5, lum);
}

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= u_aspect;

    float center = sampleMask(uv);
    float edge = 0.0;
    const int SAMPLES = 12;
    for (int i = 0; i < SAMPLES; i++) {
        float a = 6.2831853 * float(i) / float(SAMPLES);
        vec2 offset = vec2(cos(a), sin(a)) * u_outline_thickness;
        if (sampleMask(uv + offset) != center) {
            edge = 1.0;
        }
    }
    if (edge < 0.5) discard;
    f_color = vec4(1.0, 1.0, 1.0, 1.0);
}
"""


class HollowLogoOverlay:
    """Drop into any scene: create in setup(), call update(dt) each
    frame, call render(target) as a final pass after your own content."""

    def __init__(self, ctx, project_root):
        import os
        video_path = os.path.join(project_root, *VIDEO_PATH_SUFFIX)
        self.video = VideoTexture(ctx, video_path)
        self.program = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
        self.vao = make_fullscreen_quad_vao(ctx, self.program)
        self.ctx = ctx

    def update(self, dt, midi):
        self.video.update(dt, midi)

    def render(self, target):
        target.use()
        self.video.texture.use(location=0)
        self.program["u_video"] = 0
        self.program["u_aspect"] = target.size[0] / target.size[1]
        self.program["u_video_aspect"] = self.video.aspect
        self.program["u_display_half_height"] = DISPLAY_HALF_HEIGHT
        self.program["u_outline_thickness"] = OUTLINE_THICKNESS

        ctx = self.ctx
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.vao.render(moderngl.TRIANGLES)
        ctx.disable(moderngl.BLEND)

    def release(self):
        self.video.release()
