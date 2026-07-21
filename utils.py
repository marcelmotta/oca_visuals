"""
utils.py
--------
Small shared helpers. Right now just one: building a fullscreen quad
(two triangles covering the whole screen) which is the standard trick for
running a fragment shader over every pixel — used by feedback_trails.py
and noise_field.py.
"""

import numpy as np


def make_fullscreen_quad_vao(ctx, program):
    """Builds a VAO for a fullscreen quad bound to `program`.

    The quad has position (x, y in range -1..1) and uv (0..1) per vertex,
    matching a vertex shader with `in vec2 in_position; in vec2 in_uv;`.
    """
    # Two triangles making a quad that covers clip space (-1..1 on both axes)
    quad = np.array([
        # x,    y,    u,   v
        -1.0, -1.0,  0.0, 0.0,
         1.0, -1.0,  1.0, 0.0,
        -1.0,  1.0,  0.0, 1.0,
        -1.0,  1.0,  0.0, 1.0,
         1.0, -1.0,  1.0, 0.0,
         1.0,  1.0,  1.0, 1.0,
    ], dtype="f4")

    vbo = ctx.buffer(quad.tobytes())
    vao = ctx.vertex_array(program, [(vbo, "2f 2f", "in_position", "in_uv")])
    return vao


def hsv_to_rgb_np(h, s, v):
    """Vectorized HSV->RGB for numpy arrays, h/s/v each in range 0-1.

    Returns an (N, 3) array of RGB floats in range 0-1. Used to convert a
    single hue value (driven by a MIDI CC) into per-particle color.
    """
    h = np.asarray(h, dtype="f4")
    s = np.asarray(s, dtype="f4")
    v = np.asarray(v, dtype="f4")

    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i.astype(int) % 6

    conditions = [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5]
    r = np.select(conditions, [v, q, p, p, t, v])
    g = np.select(conditions, [t, v, v, q, p, p])
    b = np.select(conditions, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)
