"""
logo_video_pulse.py
--------------------
Scene 5: an exact copy of scene 4 (logo_pulse.py) — same 3D camera-angle
plane, same background pixel-cloud + per-character particle burst
(triggered by the "percussion" mapping), same fractal/noise/braid
background — except the flat PNG logo is replaced with the attached
spin-loop video (assets/oca_spin_loop_v3.mp4) playing on the plane
instead.

VIDEO PLAYBACK APPROACH:
The video is decoded frame-by-frame with OpenCV and streamed into ONE
GPU texture that gets overwritten each video frame (`texture.write(...)`)
— we never hold more than one decoded frame in memory. Frames are read
in strict sequential order (matching how video codecs are meant to be
read) and looped by seeking back to frame 0, rather than doing random
seeks, which keeps playback both correct and cheap.

Frame timing is decoupled from render framerate: we accumulate elapsed
time and only pull a new video frame when a full 1/video_fps has passed,
so the video plays at its own native speed regardless of the render
loop's frame rate.

The video's source frames are the same flat black-background / white
-mark artwork as the PNG (just animated/spinning), so the same
luminance-based transparency mask from logo_pulse.py works unchanged.
"""

import math
import os
import numpy as np
import moderngl
import cv2

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from particle_field import ParticleField

# Reuse the exact same background (fractal + noise + braid) and logo-
# plane shaders as logo_pulse.py, so both scenes share one visual
# language and only the source imagery differs.
from scenes.logo_pulse import (
    BG_VERTEX, BG_FRAGMENT, LOGO_VERTEX, LOGO_FRAGMENT,
    _perspective_matrix, _rotation_x, _rotation_y, _rotation_z, _translation_z,
)

VIDEO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "oca_spin_loop_v3.mp4",
)

# Downscale decoded frames to at most this many pixels on the long edge
# before uploading to the GPU — the source video is quite large
# (1920x2432), and re-uploading a full-resolution frame ~30 times a
# second is unnecessary bandwidth for a background visual element.
# Raise this if you want full source sharpness and your GPU/PCIe can
# keep up; lower it if playback stutters.
MAX_TEXTURE_DIM = 1024

# Object-space (x, y) centers of the three characters, derived by
# locating their centroids in the video's own frames (checked across
# several points in the loop — the three shapes stay in a fixed layout
# throughout; only detail within them animates) and converting into the
# same -1..1 object space the quad geometry uses for this plane's aspect
# ratio (different from the static PNG's, since the video isn't square).
CHARACTER_ANCHORS = [(-0.420, 0.0), (-0.007, 0.0), (0.416, 0.0)]


class LogoVideoPulseScene(Scene):
    name = "logo_video_pulse"

    def setup(self, ctx):
        self.cap = cv2.VideoCapture(VIDEO_PATH)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video file: {VIDEO_PATH}")

        self.video_fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        raw_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        raw_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.logo_aspect = raw_w / raw_h

        scale = min(1.0, MAX_TEXTURE_DIM / max(raw_w, raw_h))
        self.frame_w = max(1, int(raw_w * scale))
        self.frame_h = max(1, int(raw_h * scale))

        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("Could not read the first frame of the video")
        self.texture = ctx.texture((self.frame_w, self.frame_h), 4, self._prepare_frame(frame))
        self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        self.video_time_accum = 0.0
        self.frame_duration = 1.0 / self.video_fps

        # --- background pass (identical to logo_pulse.py) ---
        self.bg_program = ctx.program(vertex_shader=BG_VERTEX, fragment_shader=BG_FRAGMENT)
        self.bg_vao = make_fullscreen_quad_vao(ctx, self.bg_program)

        # --- video plane pass (same shader as the logo plane) ---
        self.logo_program = ctx.program(vertex_shader=LOGO_VERTEX, fragment_shader=LOGO_FRAGMENT)
        half_h = 1.0
        half_w = half_h * self.logo_aspect
        quad = np.array([
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

        self.fov = math.radians(50)
        self.distance = half_h / math.tan(self.fov / 2.0)

        self.particles = ParticleField(ctx, max_particles=3000)
        self.letter_particles = ParticleField(ctx, max_particles=2000, edge_fade=True)

        self.time = 0.0
        self.pulse = 0.0
        self.camera = None
        self.letter_trigger_pending = False

        self.next_glitch_time = np.random.uniform(10.0, 25.0)
        self.glitch_active_until = 0.0
        self.glitch_seed = 0.0

    def _prepare_frame(self, frame_bgr):
        """Resizes a decoded BGR frame and converts it to RGBA bytes."""
        if (frame_bgr.shape[1], frame_bgr.shape[0]) != (self.frame_w, self.frame_h):
            frame_bgr = cv2.resize(
                frame_bgr, (self.frame_w, self.frame_h), interpolation=cv2.INTER_AREA
            )
        frame_rgba = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
        return np.ascontiguousarray(frame_rgba).tobytes()

    def _advance_video(self, dt):
        """Pulls exactly as many new video frames as real time has passed,
        looping back to the start when the video ends."""
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

        triggered = bool(midi.role_triggers("drums"))
        self.pulse = 1.0 if triggered else self.pulse * 0.95
        self.letter_trigger_pending = bool(midi.role_triggers("percussion"))

        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0
        self.intensity = 0.3 + midi.role_cc("bass", "intensity", 0.0) * 1.5

        if self.time >= self.next_glitch_time and self.time >= self.glitch_active_until:
            duration = np.random.uniform(0.18, 0.4)
            self.glitch_active_until = self.time + duration
            self.glitch_seed = np.random.uniform(0.0, 1000.0)
            self.next_glitch_time = self.glitch_active_until + np.random.uniform(8.0, 18.0)

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

        # Plane transform, computed FIRST because the glow-pulse spawn
        # below needs it to know where each character currently sits on
        # screen, and the background pass needs the resulting pulse data.
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

        self.bg_program["u_time"] = self.time
        self.bg_program["u_hue"] = self.hue
        self.bg_program["u_intensity"] = self.intensity
        self.bg_vao.render(moderngl.TRIANGLES)

        self.particles.render()
        self.letter_particles.render()

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

    def teardown(self):
        if self.cap is not None:
            self.cap.release()
