"""
video_texture.py
-----------------
Shared helper for streaming a video file into a GPU texture, one frame
at a time, at the video's own native playback speed (decoupled from the
render loop's frame rate). Used by every scene that displays the
spin-loop video (assets/oca_spin_loop_v3.mp4) — factored out here since
it was getting duplicated across an increasing number of scene files.
"""

import numpy as np
import moderngl
import cv2


class VideoTexture:
    def __init__(self, ctx, path, max_dim=1024):
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video file: {path}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        raw_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        raw_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        scale = min(1.0, max_dim / max(raw_w, raw_h))
        self.width = max(1, int(raw_w * scale))
        self.height = max(1, int(raw_h * scale))
        self.aspect = self.width / self.height

        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("Could not read the first frame of the video")
        self.texture = ctx.texture((self.width, self.height), 4, self._prepare(frame))
        self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        self._accum = 0.0
        self._frame_duration = 1.0 / self.fps

    def _prepare(self, frame_bgr):
        if (frame_bgr.shape[1], frame_bgr.shape[0]) != (self.width, self.height):
            frame_bgr = cv2.resize(
                frame_bgr, (self.width, self.height), interpolation=cv2.INTER_AREA
            )
        frame_rgba = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
        return np.ascontiguousarray(frame_rgba).tobytes()

    def update(self, dt):
        self._accum += dt
        while self._accum >= self._frame_duration:
            ok, frame = self.cap.read()
            if not ok:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
            if ok:
                self.texture.write(self._prepare(frame))
            self._accum -= self._frame_duration

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
