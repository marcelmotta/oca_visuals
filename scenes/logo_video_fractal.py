"""
logo_video_fractal.py
----------------------
A saved checkpoint of scene 4's background experimentation, kept as its
own scene while scene 4 itself (logo_video_pulse.py) goes back to a
simpler state so new ideas can be tried there from a clean slate.

Uses the same spinning-video-driven logo as logo_video_pulse.py, over a
glowing braid background — but here the logo has real (modest) depth
and a translucent refractive glass material (see "Video plane pass"
below): the original flat quad, unchanged, plus several progressively
darker, partially-transparent copies of it stacked behind along Z, so
this scene's existing camera tilt reveals a genuine beveled side/
thickness rather than a flat opaque image. (A first attempt instead
displaced a finely subdivided grid's vertices per-pixel-luminance,
which per feedback came out "distorted, jagged" — vertex displacement
can't line up with a per-pixel alpha cutout at any practical mesh
resolution. The stacked-copies approach keeps every slice exactly as
pixel-precise as the logo always was.) The front-most slice — the
"face" actually being looked through — goes further: the background
is captured to an offscreen texture each frame and re-sampled through
a UV distorted by the letter shapes' own edge gradient (plus
chromatic aberration and a glossy specular highlight), so the
background genuinely warps as seen through the glass letters. Both the
refraction strength and the material's Fresnel-like rim/gloss react to
the plane's own actual tilt animation (a Schlick-like curve normalized
to this scene's real tilt range, not a flat linear ramp — see
FRESNEL_COS_MIN/FRESNEL_F0). (Later attempts tried merging the front
face and back/side slices into one continuously-shaded material, and
adding a backlight + selectively disabling refraction on back slices
to fix a reported "blurry"/aerogel-like look — per feedback, reverted
back to this version, which was the last one that read as acceptable.)
It still carries the source footage's own baked-in spin animation and
the existing glitch effect. (A hollow white-outline version of the
logo, and later a dark contrast outline, were both tried here too —
dropped per feedback once this 3D depth took over the job of
separating the logo from the background.)
The kaleidoscopic folding-fractal bloom that used to sit on top of the
braid here has been removed for now, per feedback, in favor of the
ground-mesh lighting below.

DEPTH: a wobbling wireframe ground mesh (see the "Ground pass" section
below) fills the bottom of the screen — a jittered/Voronoi-like
triangulated grid, rendered as genuine 3D geometry so it converges
toward a real vanishing point at screen center, like a floor or water
surface receding into the distance. It's always present, always gently
flowing via scrolling noise, and fades out — with a hard-guaranteed
cutoff well below the braid's own worst-case extent — before it could
ever visually overlap the braid above it. Beyond the wireframe edges,
every triangle is also filled at all times with a translucent tint
(a first attempt at this was far too subtle to read as any change at
all, per feedback) that's individually shaded from a real surface
normal derived from the wobble height field itself — so slopes/ridges
genuinely catch or lose light relative to their neighbors, giving the
surface actual visible topography rather than one flat color painted
across the whole mesh regardless of its shape. This, together with the
translucent fill, is what gives it a solid, glass-like 3D feel even at
rest, before any MIDI has been received.

MESH LIGHTING (channel 10 / "pads"): any trigger on this channel picks a
new random subset of the ground mesh's triangles on every MIDI-clock-
synced triplet tick — a twinkling effect timed to the tempo. Each
triangle glows brighter and more saturated on top of its always-present
base fill via a smooth attack/release envelope (slow release) driven by
real elapsed time since it was last picked, rather than a hard on/off
strobe (see "Ground-mesh lighting" section below). There's no separate
"ease back to base" step to manage: once channel 10 goes quiet, nothing
gets re-picked, so every triangle's glow simply decays back down to the
base fill on its own.

MIDI mapping:
- "keys" channel CC -> hue (shared by the braid and the ground mesh).
- "drums" channel triggers -> a brief camera "punch" (via the shared
  Camera object) that nudges the logo's tilt.
- "pads" channel (10) triggers -> picks random ground-mesh triangles to
  glow, synced to MIDI clock; eases back to the base fill when quiet.
"""

import math
import os
import numpy as np
import moderngl

from scene_base import Scene
from utils import make_fullscreen_quad_vao
from video_texture import VideoTexture

VIDEO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "oca_spin_loop_v3.mp4",
)

MAX_TEXTURE_DIM = 1024

# --- Background pass: folding fractal + braid -----------------------------

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
uniform float u_aspect;

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

void main() {
    vec2 uv = v_uv * 2.0 - 1.0;
    uv.x *= u_aspect;

    // Dim baseline tint so the background is never pure black.
    vec3 color = hsv2rgb(vec3(u_hue, 0.5, 0.08));

    // --- Braid: thick "pipe" + thin flowing sliver ---
    vec3 braid_color = hsv2rgb(vec3(fract(u_hue + 0.55), 0.45, 1.0));
    vec3 sliver_color = hsv2rgb(vec3(fract(u_hue + 0.05), 0.85, 1.0));
    float braid = 0.0;
    float sliver_glow = 0.0;
    for (int i = 0; i < 3; i++) {
        float phase = float(i) * 2.094395;

        float strand_y = -0.05
            + 0.07 * sin(uv.x * 2.6 + u_time * 0.12 + phase)
            + 0.025 * sin(uv.x * 6.3 - u_time * 0.07 + phase * 1.7);
        float d = abs(uv.y - strand_y);
        float pipe_glow = exp(-d * d * 260.0);
        braid += pipe_glow;

        float wobble = noise(vec2(uv.x * 3.5 + float(i) * 11.0, u_time * 0.35 + phase))
            + 0.5 * noise(vec2(uv.x * 9.0 - float(i) * 5.0, u_time * 0.6));
        float sliver_y = strand_y + 0.035 * (wobble - 0.75);
        float sd = abs(uv.y - sliver_y);
        float sliver_shape = exp(-sd * sd * 2200.0);

        float travel = smoothstep(0.3, 1.0,
            sin(uv.x * 4.0 - u_time * (1.2 + float(i) * 0.3) + phase));
        sliver_glow += sliver_shape * travel;
    }
    color += braid_color * braid * 0.45;
    color += sliver_color * sliver_glow * 0.55;

    f_color = vec4(color, 1.0);
}
"""

# --- Ground pass: wobbling wireframe mesh, bottom of screen ---------------
#
# A jittered grid of points (regular grid + per-point random offset, a
# simple stand-in for a true Voronoi/Delaunay triangulation that avoids
# needing real computational-geometry code) triangulated into a hollow
# wireframe (GL_LINES over the triangle edges, no filled faces), placed
# as real 3D geometry — a flat plane below eye level, receding into the
# screen — and projected with the same perspective math as the logo
# plane below. Unlike the logo, no rotation/model transform is applied:
# the vertices are authored directly in view-ready coordinates (Y below
# the camera, Z increasingly distant), so a flat plane at constant Y
# naturally converges to a single vanishing point at screen center as Z
# grows — genuine perspective convergence, not a faked 2D taper.
#
# Vertices wobble vertically via two octaves of scrolling value-noise in
# the vertex shader (GPU-side, so the static vertex buffer never needs
# re-uploading), giving a flowing, pond/ocean-like undulation.
#
# The fragment shader fades this out (and, as a hard guarantee, discards
# it entirely) above a fixed screen-space Y — computed from the actual
# rendered pixel position via gl_FragCoord, not from the mesh's Z depth
# — so it can never visually overlap the braid above it regardless of
# how the 3D projection happens to be tuned. That threshold (see
# GROUND_FADE_END below) was chosen with margin below the braid's own
# worst-case visible extent (verified numerically: the braid's strand
# wobble + glow falloff can reach y=-0.261 at its most extreme, so the
# ground mesh's hard cutoff sits at -0.35, an ~0.09 safety margin).

GROUND_GRID_COLS = 22
GROUND_GRID_ROWS = 14
GROUND_HALF_WIDTH = 1.8
GROUND_NEAR_Z = 0.5
GROUND_FAR_Z = 5.0
GROUND_JITTER = 0.4
GROUND_Y = -0.55
GROUND_FOV_DEGREES = 60.0
GROUND_FADE_START = -0.65  # fully opaque at/below this screen-space y
GROUND_FADE_END = -0.35    # fully invisible (hard discard) at/above this y


def _build_ground_points(cols, rows, half_width, near_z, far_z, jitter):
    """Builds a jittered grid of (x, z) ground-plane points — a regular
    grid plus a per-point random offset, standing in for a true
    Voronoi/Delaunay triangulation without needing real computational-
    geometry code."""
    xs = np.linspace(-half_width, half_width, cols)
    zs = np.linspace(near_z, far_z, rows)
    cell_w = xs[1] - xs[0]
    cell_d = zs[1] - zs[0]

    points = np.zeros((rows, cols, 2), dtype="f4")
    for row in range(rows):
        for col in range(cols):
            jx = np.random.uniform(-0.5, 0.5) * cell_w * jitter
            jz = np.random.uniform(-0.5, 0.5) * cell_d * jitter
            points[row, col] = [xs[col] + jx, zs[row] + jz]
    return points


def _triangulate(points, rows, cols):
    """2 triangles per grid cell, alternating diagonal direction per
    cell so it doesn't read as a rigid regular grid. Returns a flat
    list of (p0, p1, p2) vertex-position triangles."""
    triangles = []
    for row in range(rows - 1):
        for col in range(cols - 1):
            a, b = points[row, col], points[row, col + 1]
            c, d = points[row + 1, col], points[row + 1, col + 1]
            if np.random.rand() < 0.5:
                triangles.append((a, b, c))
                triangles.append((b, d, c))
            else:
                triangles.append((a, b, d))
                triangles.append((a, d, c))
    return triangles


def _build_wireframe_verts(triangles):
    """Flattens triangles into a (x, z) vertex array for GL_LINES — 2
    vertices per triangle edge. Edges shared between adjacent triangles
    get emitted twice; harmless under alpha blending and far simpler
    than deduplicating for a mesh this small."""
    lines = []
    for p0, p1, p2 in triangles:
        lines.extend([p0, p1, p1, p2, p2, p0])
    return np.array(lines, dtype="f4")


def _build_fill_positions(triangles):
    """Flattens triangles into a (x, z) position array for GL_TRIANGLES
    — 3 vertices per triangle. Positions only; "how recently was this
    triangle lit" is tracked separately as it changes every tick (see
    LogoVideoFractalScene.setup()/update()), unlike these static
    positions."""
    verts = []
    for p0, p1, p2 in triangles:
        for p in (p0, p1, p2):
            verts.append([p[0], p[1]])
    return np.array(verts, dtype="f4")


GROUND_VERTEX = """
#version 330
in vec2 in_xz;
uniform mat4 u_mvp;
uniform float u_time;
uniform float u_wobble_amp;
uniform float u_ground_y;

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

void main() {
    vec2 xz = in_xz;
    float n1 = noise(xz * 0.6 + vec2(u_time * 0.12, u_time * 0.09));
    float n2 = noise(xz * 1.4 - vec2(u_time * 0.07, u_time * 0.11) + 17.0);
    float wobble = (n1 - 0.5) * 0.7 + (n2 - 0.5) * 0.3;
    vec3 pos = vec3(xz.x, u_ground_y + wobble * u_wobble_amp, -xz.y);
    gl_Position = u_mvp * vec4(pos, 1.0);
}
"""

GROUND_FRAGMENT = """
#version 330
out vec4 f_color;

uniform float u_hue;
uniform float u_viewport_height;
uniform float u_fade_start;
uniform float u_fade_end;
uniform float u_base_alpha;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main() {
    // Actual rendered pixel position, not the mesh's 3D depth — this is
    // what makes the "can't overlap the braid" guarantee independent of
    // how the perspective projection happens to be tuned.
    float ndc_y = (gl_FragCoord.y / u_viewport_height) * 2.0 - 1.0;
    if (ndc_y > u_fade_end) discard;
    float fade = 1.0 - smoothstep(u_fade_start, u_fade_end, ndc_y);
    if (fade <= 0.01) discard;
    vec3 color = hsv2rgb(vec3(fract(u_hue + 0.55), 0.55, 0.95));
    f_color = vec4(color, fade * u_base_alpha);
}
"""

# --- Ground-mesh lighting: random glowing triangles, synced to MIDI clock -
#
# Every triangle in the mesh is filled (not just the wireframe edges),
# always, at GROUND_FILL_BASE_ALPHA, individually shaded by a per-vertex
# "how much does this bit of the surface face the light" term (v_light,
# computed in GROUND_FILL_VERTEX from an actual surface normal — see
# that shader's comment) — this shading, not just the fill itself, is
# what gives the mesh a solid, glass-like surface feel with real
# topography even at rest, before any MIDI has been received. Channel
# 10 ("pads") triggers pick a new
# random subset of triangles on every MIDI-clock-synced triplet tick
# (see update()'s tri_last_lit) to brighten further on top of that base
# fill. Rather than a hard on/off strobe, each triangle gets a smooth
# glow envelope — a quick attack then a slow release/decay — driven by
# real elapsed time since it was last picked, so newly-picked triangles
# glow in and previously-picked ones ease back down to the base fill
# smoothly rather than snapping. Because the envelope is purely a
# function of "how long ago was this triangle last picked," there's no
# separate "revert to base" state to manage: once channel 10 goes
# quiet, no triangle gets re-picked, so every envelope simply decays
# back to GROUND_FILL_BASE_ALPHA on its own over GROUND_FILL_RELEASE
# seconds.
#
# This needs real per-triangle timing (not just a stateless hash), so
# — unlike the wireframe pass, whose vertex buffer is fully static —
# each triplet tick, update() randomly picks a new subset of triangle
# indices, stamps them with the current time in a small numpy array,
# and re-uploads a "when was I last picked" value per vertex. That
# buffer is tiny (one float per triangle, repeated 3x) and only
# rewritten on tick boundaries (roughly every 100-300ms depending on
# tempo), so this is a negligible cost.

GROUND_FILL_VERTEX = """
#version 330
in vec2 in_xz;
in float in_last_lit;
out float v_last_lit;
out float v_light;
uniform mat4 u_mvp;
uniform float u_time;
uniform float u_wobble_amp;
uniform float u_ground_y;

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

// Full (both-octave) wobble used for the actual displayed vertex
// height/displacement.
float wobble_at(vec2 xz) {
    float n1 = noise(xz * 0.6 + vec2(u_time * 0.12, u_time * 0.09));
    float n2 = noise(xz * 1.4 - vec2(u_time * 0.07, u_time * 0.11) + 17.0);
    return (n1 - 0.5) * 0.7 + (n2 - 0.5) * 0.3;
}

// Low-frequency-ONLY height (just the dominant, slower-scrolling n1
// octave) used for the shading normal below — deliberately a smoothed/
// coarser version of the terrain, not the full-detail wobble. A first
// version of this shading sampled the FULL wobble (both octaves) at a
// small eps and exaggerated the resulting slope 15x to get visible
// contrast, which per feedback looked like shadows "switching on and
// off suddenly" in "random" places — verified numerically why: the
// finer, faster-scrolling n2 octave contributes high-frequency detail
// that a 15x-exaggerated, small-eps finite difference is extremely
// sensitive to, so adjacent mesh vertices (which sample independently)
// could get quite different normals even though the underlying surface
// is smooth — a noisy per-vertex signal, not a coherent moving
// shadow. Using only the smoother, dominant octave — sampled at a
// wider eps, with less exaggeration (verified numerically together:
// mean difference between ADJACENT vertices dropped from 0.115 to
// 0.040, and frame-to-frame change at a single fixed vertex is only
// ~0.001, while overall contrast stays comparable, shading from ~0.82x
// to ~1.46x brightness) — i.e. a shading pattern that actually varies
// smoothly across the mesh and over time instead of flickering
// vertex-to-vertex.
float shading_height_at(vec2 xz) {
    return noise(xz * 0.6 + vec2(u_time * 0.12, u_time * 0.09)) - 0.5;
}

void main() {
    vec2 xz = in_xz;
    float wobble = wobble_at(xz);
    vec3 pos = vec3(xz.x, u_ground_y + wobble * u_wobble_amp, -xz.y);
    gl_Position = u_mvp * vec4(pos, 1.0);
    v_last_lit = in_last_lit;

    // Real "topography" shading: sample the (smoothed) height field a
    // step away in both ground-plane directions, build the two tangent
    // vectors implied by those height differences, and cross them for
    // an actual surface normal — so triangles on a local slope/ridge
    // genuinely catch or lose light relative to their neighbors, rather
    // than the whole mesh reading as one flat color regardless of its
    // undulation.
    const float SHADE_STEEPNESS = 6.0;
    float eps = 0.4;
    float h = shading_height_at(xz);
    float h_x = shading_height_at(xz + vec2(eps, 0.0));
    float h_z = shading_height_at(xz + vec2(0.0, eps));
    vec3 tangent_x = vec3(eps, (h_x - h) * u_wobble_amp * SHADE_STEEPNESS, 0.0);
    vec3 tangent_z = vec3(0.0, (h_z - h) * u_wobble_amp * SHADE_STEEPNESS, eps);
    vec3 normal = normalize(cross(tangent_z, tangent_x));

    vec3 light_dir = normalize(vec3(0.7, 0.4, 0.3));
    v_light = clamp(dot(normal, light_dir), -1.0, 1.0);
}
"""

GROUND_FILL_FRAGMENT = """
#version 330
in float v_last_lit;
in float v_light;
out vec4 f_color;

uniform float u_hue;
uniform float u_viewport_height;
uniform float u_fade_start;
uniform float u_fade_end;
uniform float u_time;
uniform float u_attack;
uniform float u_release;
uniform float u_max_alpha;
uniform float u_base_alpha;

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main() {
    // Smooth glow envelope: quick linear attack, then exponential
    // release — driven entirely by how long ago this triangle was last
    // picked (v_last_lit), not by whether it's "currently" picked. This
    // is what makes triangles glow in and fade out smoothly instead of
    // strobing on/off, and what lets the whole mesh ease back to its
    // base (unlit) fill on its own once nothing new gets picked.
    float age = u_time - v_last_lit;
    float envelope = age < u_attack
        ? age / u_attack
        : exp(-(age - u_attack) / u_release);

    // Same screen-space fade/cutoff as the wireframe pass, so filled
    // triangles never appear past where the mesh itself would.
    float ndc_y = (gl_FragCoord.y / u_viewport_height) * 2.0 - 1.0;
    if (ndc_y > u_fade_end) discard;
    float fade = 1.0 - smoothstep(u_fade_start, u_fade_end, ndc_y);
    if (fade <= 0.01) discard;

    // Every triangle is filled with a translucent base tint ALWAYS —
    // not just when lit — for a sense of solid, glass-like
    // surface even at rest; the glow envelope brightens and saturates
    // it on top of that base when a triangle gets picked.
    float alpha = u_base_alpha + envelope * (u_max_alpha - u_base_alpha);
    vec3 color = hsv2rgb(vec3(fract(u_hue + 0.55), mix(0.35, 0.6, envelope), mix(0.55, 1.0, envelope)));

    // Real shading from v_light (see GROUND_FILL_VERTEX): ridges/slopes
    // facing the light brighten, ones facing away darken — this is what
    // gives the surface actual topography instead of every triangle
    // reading as the same flat color regardless of the mesh's shape.
    float shade = mix(0.35, 1.5, v_light * 0.5 + 0.5);
    color *= shade;

    f_color = vec4(color, fade * alpha);
}
"""

MESH_LIT_FRACTION = 0.18    # fraction of triangles picked on any given tick
PADS_QUIET_TIMEOUT = 0.4    # seconds of no channel-10 triggers before no new triangles get picked
GROUND_FILL_ATTACK = 0.02   # seconds to glow in — shortened (0.06 -> 0.02) per feedback for a snappier trigger response
GROUND_FILL_RELEASE = 0.9   # seconds to fade back out (slow, per feedback)
GROUND_FILL_MAX_ALPHA = 0.45  # peak opacity when a triangle is freshly lit — lowered (0.75 -> 0.45)
                                # per feedback that the fill was too opaque; still a clear jump over the base
GROUND_FILL_BASE_ALPHA = 0.18  # always-present base fill opacity — lowered (0.3 -> 0.18) alongside
                                 # GROUND_FILL_MAX_ALPHA for an overall more translucent look

# --- Video plane pass: stacked-extrusion 3D, with glitch -----------------
#
# First attempt at "make the logo 3D" subdivided the flat quad into an
# 80x80 grid and displaced each vertex along Z by the video's own
# per-vertex luminance, with a normal-based emboss shading on top. Per
# feedback it came out "completely distorted, jagged" — the fundamental
# problem: vertex displacement can only be as smooth/precise as the mesh
# resolution, but the alpha cutout that actually defines the visible
# silhouette is evaluated per-PIXEL in the fragment shader — there is no
# resolution at which a displaced grid's blocky, linearly-interpolated
# shape reliably lines up with crisp per-pixel letter edges. That
# mismatch between "what's opaque" (pixel-precise) and "what's extruded"
# (grid-resolution-limited) is what read as distortion.
#
# This instead uses the classic "stack of cutouts" technique for faking
# extruded 2D shapes in 3D: keep the ORIGINAL simple flat quad (so the
# visible silhouette is exactly as pixel-precise as it always was — no
# geometry resolution involved at all), and draw several progressively
# darker copies of it stacked behind the front one along Z (see
# render()'s slice loop). Viewed through this scene's existing camera
# tilt, that stack reads as a genuine beveled side/thickness — real
# depth — while every individual slice is still just the same crisp,
# unmodified per-pixel video sampling as before.
#
# Each slice is also given a translucent, "smoked glass" material in
# LOGO_FRAGMENT: desaturated + cool-tinted color, reduced alpha (so it's
# see-through rather than solid — stacking several translucent layers
# is what makes it read as a substantial block of glass rather than a
# single thin pane), and a Fresnel-like rim brightening/opacity boost
# (computed once per frame in render() from the plane's own rotated
# normal, since it's still a flat surface) that grows as the plane
# tilts away from facing the camera dead-on — the classic cue that
# sells a glass/translucent material.
#
# That alone (tint + reduced alpha) read as a faded image, not glass,
# per feedback — real glass REFRACTS what's behind it, it doesn't just
# fade it. So the front-most slice (the "face" the viewer actually
# looks through) uses a different technique (LOGO_FRAGMENT_GLASS): the
# bg braid + ground mesh are first rendered into an offscreen texture
# (see bg_capture_fbo) instead of straight to the screen, then that
# texture is blitted to the real target, and finally the glass face
# samples the SAME background texture again with a distorted UV —
# offset by the local gradient of the letter shape's own alpha mask
# (strongest right at a curved edge, near-zero in flat interior/
# exterior regions, exactly like a real embossed glass letter bends
# light most at its boundary), plus chromatic aberration (sampling each
# color channel at a slightly different offset — the classic "looking
# through thick glass" cue, visible even where the background itself
# is fairly smooth/low-detail) — and mixes that warped sample with the
# character's own tinted color. This is what actually shows the
# background warped through the glass rather than just dimmed under
# it. The back/side slices keep the simpler tint-only material (plus
# their own bump-mapped specular) — they read as depth/shading on the
# extrusion's sides, not the "looking through" face.
#
# Both the refraction strength and the Fresnel-like rim/gloss react to
# the plane's own actual tilt animation each frame (see render() and
# FRESNEL_COS_MIN/FRESNEL_F0 below) via a Schlick-like curve — low near
# dead-on, rising toward however edge-on this scene's yaw/pitch/roll
# animation ever actually gets (verified numerically that raw view-
# angle cosine barely moves across the plane's real tilt range, so it's
# remapped against that real range instead of the textbook 0..1 one).

# A plain copy shader: draws bg_capture_fbo's texture onto `target`
# unmodified (opaque, ignoring its own alpha) before the logo is drawn
# on top — this is what makes "the background so far" available as a
# sampleable texture for the glass face's refraction below, something
# rendering straight to `target` (as every other pass in this project
# does) can't offer.
BLIT_VERTEX = """
#version 330
in vec2 in_position;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""

BLIT_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_tex;
void main() {
    f_color = vec4(texture(u_tex, v_uv).rgb, 1.0);
}
"""

LOGO_VERTEX = """
#version 330
in vec3 in_position;
in vec2 in_uv;
out vec2 v_uv;
uniform mat4 u_mvp;
uniform float u_z_offset;
void main() {
    v_uv = in_uv;
    vec3 pos = in_position + vec3(0.0, 0.0, u_z_offset);
    gl_Position = u_mvp * vec4(pos, 1.0);
}
"""

LOGO_FRAGMENT = """
#version 330
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_logo;
uniform float u_glitch_amount;
uniform float u_glitch_seed;
uniform float u_darken;
uniform float u_glass_alpha;
uniform float u_fresnel;
uniform vec3 u_view_dir;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

vec3 sample_video(vec2 uv) {
    return texture(u_logo, vec2(uv.x, 1.0 - uv.y)).rgb;
}

void main() {
    vec2 uv = v_uv;

    vec3 tex_rgb;
    if (u_glitch_amount > 0.0) {
        float band = floor(v_uv.y * 14.0);
        float band_rand = hash(vec2(band, u_glitch_seed));
        float tear = step(0.55, band_rand) * (band_rand - 0.5) * 2.0;
        uv.x += tear * 0.12 * u_glitch_amount;

        float split = 0.012 * u_glitch_amount;
        float r = texture(u_logo, vec2(uv.x + split, 1.0 - uv.y)).r;
        float g = texture(u_logo, vec2(uv.x, 1.0 - uv.y)).g;
        float b = texture(u_logo, vec2(uv.x - split, 1.0 - uv.y)).b;
        tex_rgb = vec3(r, g, b);
    } else {
        tex_rgb = sample_video(uv);
    }

    float lum = dot(tex_rgb, vec3(0.299, 0.587, 0.114));
    // Anti-aliased cutout: fwidth(lum) sizes the smoothstep band to ~1
    // screen pixel regardless of the logo's on-screen size, instead of
    // a fixed luminance-space band (which reads as jagged small and
    // oddly soft large).
    float edge_soft = fwidth(lum) * 1.5 + 0.01;
    float mask = smoothstep(0.45 - edge_soft, 0.45 + edge_soft, lum);
    // Scaled by u_glass_alpha (< 1.0) rather than left fully opaque —
    // this is what makes each slice translucent rather than solid.
    // Stacking many translucent slices naturally builds up toward a
    // more substantial (but still see-through at the edges) look, the
    // way a thick block of glass reads differently than a thin pane.
    float alpha = mask * u_glass_alpha;
    if (alpha <= 0.01) discard;

    // "Smoked glass" material: desaturate the video's own color toward
    // gray, then multiply by a cool, slightly dim tint — this is what
    // makes it read as something being VIEWED THROUGH tinted glass
    // rather than a solid, fully-saturated printed material.
    vec3 gray = vec3(lum);
    tex_rgb = mix(tex_rgb, gray, 0.45);
    tex_rgb *= vec3(0.72, 0.8, 0.86);

    // Per-slice depth darkening.
    tex_rgb *= u_darken;

    // Glossy sheen: a fake normal built from the local alpha-mask
    // gradient, lit with a fixed key light and this slice's actual
    // view direction (so the highlight moves correctly as the plane
    // tilts through its existing animation, like real light catching a
    // curved glass edge). Scaled by u_fresnel (a Schlick-like curve
    // over the plane's OWN actual tilt range, low near dead-on, rising
    // toward however edge-on this scene's animation ever gets) — real
    // specular reflectance grows with view angle too, so the sheen
    // should visibly strengthen as the plane tilts, not stay constant.
    float eps = 0.008;
    float lum_x = dot(sample_video(uv + vec2(eps, 0.0)), vec3(0.299, 0.587, 0.114));
    float lum_y = dot(sample_video(uv + vec2(0.0, eps)), vec3(0.299, 0.587, 0.114));
    float mask_x = smoothstep(0.45 - edge_soft, 0.45 + edge_soft, lum_x);
    float mask_y = smoothstep(0.45 - edge_soft, 0.45 + edge_soft, lum_y);
    vec2 edge_grad = vec2(mask_x - mask, mask_y - mask);

    vec3 bump_normal = normalize(vec3(-edge_grad * 3.0, 1.0));
    vec3 light_dir = normalize(vec3(0.5, 0.6, 0.7));
    vec3 half_vec = normalize(light_dir + normalize(u_view_dir));
    float spec = pow(clamp(dot(bump_normal, half_vec), 0.0, 1.0), 10.0);
    tex_rgb += spec * mix(0.3, 1.0, u_fresnel) * 0.8;

    // Fresnel-like rim sheen: brighter, slightly more opaque at grazing
    // angles as the plane tilts, the classic glass/translucent-material
    // cue. u_fresnel is uniform across the whole plane (computed once
    // in render() from the plane's own rotated normal) rather than
    // per-pixel, since this is still a flat plane.
    tex_rgb += u_fresnel * 0.3;
    alpha = clamp(alpha + u_fresnel * 0.15, 0.0, 1.0);

    f_color = vec4(tex_rgb, alpha);
}
"""

# The front-most slice only: instead of a flat tint, this samples the
# already-rendered background (bg_capture_fbo, see render()) a second
# time through a distorted UV, so what's behind the logo visibly warps
# through it rather than just dimming — see the "Video plane pass"
# module comment above for the reasoning.
LOGO_FRAGMENT_GLASS = """
#version 330
in vec2 v_uv;
out vec4 f_color;
uniform sampler2D u_logo;
uniform sampler2D u_background;
uniform vec2 u_viewport_size;
uniform float u_glitch_amount;
uniform float u_glitch_seed;
uniform float u_glass_alpha;
uniform float u_fresnel;
uniform float u_density;
uniform vec3 u_view_dir;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

vec3 sample_video(vec2 uv) {
    return texture(u_logo, vec2(uv.x, 1.0 - uv.y)).rgb;
}

void main() {
    vec2 uv = v_uv;

    vec3 tex_rgb;
    if (u_glitch_amount > 0.0) {
        float band = floor(v_uv.y * 14.0);
        float band_rand = hash(vec2(band, u_glitch_seed));
        float tear = step(0.55, band_rand) * (band_rand - 0.5) * 2.0;
        uv.x += tear * 0.12 * u_glitch_amount;

        float split = 0.012 * u_glitch_amount;
        float r = texture(u_logo, vec2(uv.x + split, 1.0 - uv.y)).r;
        float g = texture(u_logo, vec2(uv.x, 1.0 - uv.y)).g;
        float b = texture(u_logo, vec2(uv.x - split, 1.0 - uv.y)).b;
        tex_rgb = vec3(r, g, b);
    } else {
        tex_rgb = sample_video(uv);
    }

    float lum = dot(tex_rgb, vec3(0.299, 0.587, 0.114));
    // Anti-aliased cutout (see LOGO_FRAGMENT for the full reasoning):
    // fwidth(lum) sizes the smoothstep band to ~1 screen pixel instead
    // of a fixed luminance-space band, fixing edges that read as jagged
    // or fake-looking regardless of the logo's on-screen size.
    float edge_soft = fwidth(lum) * 1.5 + 0.01;
    float mask = smoothstep(0.45 - edge_soft, 0.45 + edge_soft, lum);
    float alpha = mask * u_glass_alpha;
    if (alpha <= 0.01) discard;

    // Refraction offset: the LOCAL slope of the letter shape's own
    // alpha mask (finite-difference of the exact same mask used for
    // the cutout above, purely per-pixel — no mesh resolution involved
    // at all, unlike the earlier rejected vertex-displacement attempt)
    // — strongest right at a curved edge, near-zero in flat interior/
    // exterior regions, like a real embossed glass letter bends light
    // most at its boundary and passes it through almost undistorted
    // through the middle.
    //
    // Scaled by u_density, which render() sets dynamically each frame
    // from BOTH the extrusion's depth (thicker glass bends more) AND
    // the current Fresnel/view angle (steeper viewing angle = more
    // effective glass thickness the light crosses, so more bend) —
    // this is what makes the refraction actually react to perspective
    // instead of staying constant regardless of tilt.
    float eps = 0.008;
    float lum_x = dot(sample_video(uv + vec2(eps, 0.0)), vec3(0.299, 0.587, 0.114));
    float lum_y = dot(sample_video(uv + vec2(0.0, eps)), vec3(0.299, 0.587, 0.114));
    float mask_x = smoothstep(0.45 - edge_soft, 0.45 + edge_soft, lum_x);
    float mask_y = smoothstep(0.45 - edge_soft, 0.45 + edge_soft, lum_y);
    vec2 edge_grad = vec2(mask_x - mask, mask_y - mask);

    vec2 refract_offset = edge_grad * 0.09 * u_density;

    // Chromatic aberration: sample the background through each color
    // channel at a slightly different offset scale, concentrated at the
    // same letter edges the refraction itself is (since it's built from
    // the same edge_grad) — this is the single most recognizable
    // "looking through thick glass/a lens" cue, and reads clearly even
    // where the background is fairly smooth/low-detail (a plain warp is
    // only visible where the background already has sharp features to
    // distort; a color-fringed edge is visible regardless).
    vec2 screen_uv = gl_FragCoord.xy / u_viewport_size;
    vec2 uv_r = clamp(screen_uv + refract_offset * 0.85, 0.0, 1.0);
    vec2 uv_g = clamp(screen_uv + refract_offset * 1.0, 0.0, 1.0);
    vec2 uv_b = clamp(screen_uv + refract_offset * 1.15, 0.0, 1.0);
    vec3 bg_sample = vec3(
        texture(u_background, uv_r).r,
        texture(u_background, uv_g).g,
        texture(u_background, uv_b).b
    );

    // Mostly the warped background (the actual "see through" part),
    // with enough of the character's own tinted color mixed in that it
    // still reads as itself rather than just a distorted patch of
    // whatever's behind it. Lighter tint/less desaturation than the
    // back/side slices (LOGO_FRAGMENT) — this is the primary "face"
    // being looked through and needs to read as clear, glossy glass,
    // not the smoked/shadowed material appropriate for the extrusion's
    // hidden sides.
    vec3 gray = vec3(lum);
    vec3 tinted_video = mix(tex_rgb, gray, 0.2) * vec3(0.88, 0.94, 1.0);
    vec3 tinted_bg = bg_sample * vec3(0.92, 0.96, 1.02);
    vec3 color = mix(tinted_bg, tinted_video, 0.3);

    // Glossy sheen: a fake surface normal "bumped" from the same
    // letter-edge gradient used for refraction above (so the highlight
    // sits right on the character's own curves/corners, not somewhere
    // arbitrary), lit with a fixed key light and this slice's actual
    // view direction (computed CPU-side from the plane's own rotation —
    // see render() — so the highlight correctly slides across the
    // surface as the plane tilts through its existing animation,
    // instead of looking painted-on). Intensity scaled by u_fresnel —
    // real specular reflectance grows with view angle, so the sheen
    // should visibly strengthen as the plane tilts toward edge-on
    // rather than staying fixed regardless of perspective.
    vec3 bump_normal = normalize(vec3(-edge_grad * 4.0, 1.0));
    vec3 light_dir = normalize(vec3(0.5, 0.6, 0.7));
    vec3 half_vec = normalize(light_dir + normalize(u_view_dir));
    float spec = pow(clamp(dot(bump_normal, half_vec), 0.0, 1.0), 9.0);
    color += spec * mix(0.4, 1.0, u_fresnel) * 1.1;

    // Fresnel rim: brighter and more opaque toward the plane's own most
    // edge-on pose (see render() — a Schlick-like curve over this
    // scene's ACTUAL tilt range, not raw view-angle cosine, since the
    // animation never reaches a true grazing angle and a textbook
    // Schlick curve would barely move at all across it).
    color += u_fresnel * 0.35;
    alpha = clamp(alpha + u_fresnel * 0.15, 0.0, 1.0);

    f_color = vec4(color, alpha);
}
"""

LOGO_EXTRUDE_SLICES = 14     # how many stacked copies form the extrusion's "side"
LOGO_EXTRUDE_DEPTH = 0.05    # in the same local units as half_h (1.0) — total thickness (halved per feedback)
LOGO_EXTRUDE_MIN_DARKEN = 0.35  # brightness of the farthest-back slice (front slice is always 1.0x)

# Schlick-like Fresnel curve for the glass material (see render()):
# FRESNEL_COS_MIN is how edge-on the plane's own yaw/pitch/roll
# animation ever actually gets (verified numerically by sampling
# abs(normal.z) across the full animation: it never drops below ~0.644,
# i.e. this scene never reaches a true grazing angle), used to remap
# the real tilt range to a full 0..1 curve input. FRESNEL_F0 is the
# reflectivity at dead-on incidence (real glass is ~0.04; kept slightly
# higher here so there's always a bit of visible sheen/rim even facing
# the camera straight on).
FRESNEL_COS_MIN = 0.64
FRESNEL_F0 = 0.05

# Base strength of the glass face's refraction offset (LOGO_FRAGMENT_
# GLASS) — derived from LOGO_EXTRUDE_DEPTH rather than an arbitrary
# constant, so a "denser"/thicker glass block genuinely warps more, the
# way real refraction displaces a ray further the deeper the medium it
# passes through is. 1.0 at zero depth, +20x depth beyond that — 2.0 at
# the current LOGO_EXTRUDE_DEPTH (0.05). render() multiplies this
# further by (1 + fresnel*1.2) each frame — see FRESNEL_COS_MIN/
# FRESNEL_F0 above — so steeper viewing angles bend the background more
# too. Verified numerically together (base density 2.0, worst-case
# dynamic density 4.4 at the plane's own most edge-on real pose): the
# combined worst-case offset (both mask-gradient axes maxed at once,
# plus the chromatic-aberration channel split) reaches ~0.64 screen-uv
# units — large, but only at that rare edge+extreme-tilt combination,
# always clamped in-shader, and NaN/Inf-free; the typical case near
# dead-on stays a modest ~0.045.
LOGO_REFRACT_DENSITY = 1.0 + LOGO_EXTRUDE_DEPTH * 20.0

# Per feedback that an earlier version's front glass face was drowned
# out by the back/side slices (splitting one shared, equally-weighted
# alpha across all LOGO_EXTRUDE_SLICES+1 layers gave the front face
# only ~5-10% of the final pixel's visual weight — the compounded back
# stack and the plain background underneath it dominated instead, which
# is why it still read as "matte"/"smoked" with no visible gloss or
# warping despite those effects being implemented) — the front face and
# the back/side slices use two SEPARATE alpha values instead of one
# shared LOGO_GLASS_ALPHA:
#
# - LOGO_FRONT_ALPHA: a direct, fairly high opacity for the front
#   face — it's the primary material surface the viewer actually looks
#   at/through, so it should dominate the final pixel, not compete
#   equally with 14 other layers.
# - LOGO_BACK_SLICE_ALPHA: solved (compounding-alpha math — 1-(1-a)^n)
#   so the 14 back/side slices ALONE converge to a modest cumulative
#   opacity — just enough to read as a beveled depth/shadow cue at the
#   extrusion's edges when tilted, not a competing "second material."
#
# Verified numerically: with LOGO_FRONT_ALPHA=0.7 and back slices
# compounding to 0.3, the front face carries ~70% of the final pixel's
# color, the back stack ~9%, and the plain (undistorted) background
# still peeking through underneath both ~21% — that last bit is what
# keeps the whole thing reading as translucent rather than a solid
# opaque card, even at the front face's own fairly high alpha.
LOGO_FRONT_ALPHA = 0.7
LOGO_BACK_TARGET_OPACITY = 0.3
LOGO_BACK_SLICE_ALPHA = 1.0 - (1.0 - LOGO_BACK_TARGET_OPACITY) ** (1.0 / LOGO_EXTRUDE_SLICES)


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


class LogoVideoFractalScene(Scene):
    name = "logo_video_fractal"

    def setup(self, ctx):
        self.bg_program = ctx.program(vertex_shader=BG_VERTEX, fragment_shader=BG_FRAGMENT)
        self.bg_vao = make_fullscreen_quad_vao(ctx, self.bg_program)

        ground_points = _build_ground_points(
            GROUND_GRID_COLS, GROUND_GRID_ROWS, GROUND_HALF_WIDTH, GROUND_NEAR_Z, GROUND_FAR_Z, GROUND_JITTER
        )
        ground_triangles = _triangulate(ground_points, GROUND_GRID_ROWS, GROUND_GRID_COLS)

        self.ground_program = ctx.program(vertex_shader=GROUND_VERTEX, fragment_shader=GROUND_FRAGMENT)
        wire_verts = _build_wireframe_verts(ground_triangles)
        wire_vbo = ctx.buffer(wire_verts.tobytes())
        self.ground_vao = ctx.vertex_array(self.ground_program, [(wire_vbo, "2f", "in_xz")])

        self.ground_fill_program = ctx.program(vertex_shader=GROUND_FILL_VERTEX, fragment_shader=GROUND_FILL_FRAGMENT)
        self.num_ground_triangles = len(ground_triangles)
        fill_pos = _build_fill_positions(ground_triangles)
        fill_pos_vbo = ctx.buffer(fill_pos.tobytes())
        # "Last lit" time is per-TRIANGLE but stored per-VERTEX (each
        # triangle's 3 vertices share one value) — rewritten whenever a
        # tick picks new triangles (see update()), unlike the static
        # position buffer above.
        self.tri_last_lit = np.full(self.num_ground_triangles, -9999.0, dtype="f4")
        fill_time_vbo = ctx.buffer(np.repeat(self.tri_last_lit, 3).tobytes(), dynamic=True)
        self.ground_fill_time_vbo = fill_time_vbo
        self.ground_fill_vao = ctx.vertex_array(
            self.ground_fill_program, [(fill_pos_vbo, "2f", "in_xz"), (fill_time_vbo, "1f", "in_last_lit")]
        )

        self.ground_fov = math.radians(GROUND_FOV_DEGREES)
        self.mesh_active = False
        self.last_pads_trigger_time = -9999.0

        self.video = VideoTexture(ctx, VIDEO_PATH, max_dim=MAX_TEXTURE_DIM)

        # Offscreen capture of the bg braid + ground mesh, at the real
        # output resolution (not downscaled like particle_burst.py's
        # work buffers — this is sampled directly by the glass face
        # below, so it needs to stay sharp) — see the "Video plane
        # pass" module comment and resize() for why this exists.
        self.bg_capture_size = (self.output_width, self.output_height)
        self.bg_capture_fbo = self._make_capture_fbo(ctx, self.bg_capture_size)
        self.blit_program = ctx.program(vertex_shader=BLIT_VERTEX, fragment_shader=BLIT_FRAGMENT)
        self.blit_vao = make_fullscreen_quad_vao(ctx, self.blit_program)

        self.logo_program = ctx.program(vertex_shader=LOGO_VERTEX, fragment_shader=LOGO_FRAGMENT)
        half_h = 1.0
        half_w = half_h * self.video.aspect
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

        # Front face only: same geometry, different program/material
        # (see LOGO_FRAGMENT_GLASS) — reuses the same quad VBO since the
        # shape is identical, just bound to a different program's
        # attribute locations.
        self.logo_glass_program = ctx.program(vertex_shader=LOGO_VERTEX, fragment_shader=LOGO_FRAGMENT_GLASS)
        self.logo_glass_vao = ctx.vertex_array(
            self.logo_glass_program, [(logo_vbo, "3f 2f", "in_position", "in_uv")]
        )

        self.fov = math.radians(50)
        self.distance = half_h / math.tan(self.fov / 2.0)

        self.time = 0.0
        self.hue = 0.0
        self.camera = None

        # Random, infrequent, brief glitch.
        self.next_glitch_time = np.random.uniform(10.0, 25.0)
        self.glitch_active_until = 0.0
        self.glitch_seed = 0.0

    def _make_capture_fbo(self, ctx, size):
        tex = ctx.texture(size, 4)
        tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        return ctx.framebuffer(color_attachments=[tex])

    def resize(self, width, height):
        super().resize(width, height)
        new_size = (width, height)
        if new_size != self.bg_capture_size:
            self.bg_capture_size = new_size
            self.bg_capture_fbo = self._make_capture_fbo(self.ctx, new_size)

    def update(self, dt, midi, camera):
        self.time += dt
        self.camera = camera
        # The video itself is the spin-loop footage — freezing it on
        # MIDI-quiet (handled inside VideoTexture) IS "the logo's
        # rotation stopping". The plane's own tilt below is a separate,
        # always-on animation and is intentionally NOT gated on MIDI.
        self.video.update(dt, midi)

        autonomous_hue = (self.time * 0.006) % 1.0
        self.hue = (autonomous_hue + midi.role_cc("keys", "color_shift", 0.0)) % 1.0

        # Ground-mesh lighting: any trigger on channel 10 ("pads") marks
        # the mesh "active"; while active, each MIDI-clock-synced
        # triplet tick picks a new random subset of triangles and stamps
        # them with the current time, which is what the fill shader's
        # glow envelope measures elapsed time against (see
        # GROUND_FILL_FRAGMENT). No separate "revert to hollow" step is
        # needed — once channel 10 goes quiet, no triangle gets
        # re-stamped, so every envelope decays to invisible on its own.
        if midi.role_triggers("pads"):
            self.last_pads_trigger_time = self.time
        self.mesh_active = (self.time - self.last_pads_trigger_time) < PADS_QUIET_TIMEOUT
        if self.mesh_active and midi.triplet_tick_pending:
            n_lit = max(1, round(MESH_LIT_FRACTION * self.num_ground_triangles))
            lit_indices = np.random.choice(self.num_ground_triangles, size=n_lit, replace=False)
            self.tri_last_lit[lit_indices] = self.time
            self.ground_fill_time_vbo.write(np.repeat(self.tri_last_lit, 3).tobytes())

        if self.time >= self.next_glitch_time and self.time >= self.glitch_active_until:
            duration = np.random.uniform(0.18, 0.4)
            self.glitch_active_until = self.time + duration
            self.glitch_seed = np.random.uniform(0.0, 1000.0)
            self.next_glitch_time = self.glitch_active_until + np.random.uniform(8.0, 18.0)

    def render(self, target):
        ctx = self.ctx
        cam = self.camera

        # --- Background capture pass: bg braid + ground mesh render into
        # an offscreen texture first, instead of straight to `target` —
        # this is what lets every logo slice sample "what's actually
        # behind it" for a refraction effect below (see LOGO_FRAGMENT).
        # The bg pass below is a fullscreen quad that always writes
        # alpha=1.0 across the whole capture texture, so no separate
        # clear is needed here.
        self.bg_capture_fbo.use()

        self.bg_program["u_time"] = self.time
        self.bg_program["u_hue"] = self.hue
        self.bg_program["u_aspect"] = target.size[0] / target.size[1]
        self.bg_vao.render(moderngl.TRIANGLES)

        # Wobbling ground mesh: vertices are authored directly in
        # view-ready coordinates (see GROUND_VERTEX/GROUND_FRAGMENT
        # comment above), so mvp is just the projection — no separate
        # model/view transform needed.
        ground_aspect = target.size[0] / target.size[1]
        ground_proj = _perspective_matrix(self.ground_fov, ground_aspect, 0.1, 20.0)
        ground_mvp = ground_proj.T.astype("f4").copy()

        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        self.ground_program["u_mvp"].write(ground_mvp.tobytes())
        self.ground_program["u_time"] = self.time
        self.ground_program["u_wobble_amp"] = 0.18
        self.ground_program["u_ground_y"] = GROUND_Y
        self.ground_program["u_hue"] = self.hue
        self.ground_program["u_viewport_height"] = float(target.size[1])
        self.ground_program["u_fade_start"] = GROUND_FADE_START
        self.ground_program["u_fade_end"] = GROUND_FADE_END
        self.ground_program["u_base_alpha"] = 0.55
        self.ground_vao.render(moderngl.LINES)

        # Filled triangles: always drawn, at a base opacity even with no
        # MIDI (see GROUND_FILL_FRAGMENT) — the glow envelope on
        # top is a function of elapsed time since each triangle was last
        # picked, so it naturally eases back to that base once enough
        # time has passed, no active/hollow toggle needed here.
        self.ground_fill_program["u_mvp"].write(ground_mvp.tobytes())
        self.ground_fill_program["u_time"] = self.time
        self.ground_fill_program["u_wobble_amp"] = 0.18
        self.ground_fill_program["u_ground_y"] = GROUND_Y
        self.ground_fill_program["u_hue"] = self.hue
        self.ground_fill_program["u_viewport_height"] = float(target.size[1])
        self.ground_fill_program["u_fade_start"] = GROUND_FADE_START
        self.ground_fill_program["u_fade_end"] = GROUND_FADE_END
        self.ground_fill_program["u_attack"] = GROUND_FILL_ATTACK
        self.ground_fill_program["u_release"] = GROUND_FILL_RELEASE
        self.ground_fill_program["u_max_alpha"] = GROUND_FILL_MAX_ALPHA
        self.ground_fill_program["u_base_alpha"] = GROUND_FILL_BASE_ALPHA
        self.ground_fill_vao.render(moderngl.TRIANGLES)

        ctx.disable(moderngl.BLEND)

        # Composite the captured background onto the real target, then
        # draw the logo on top of THAT (in the actual output
        # framebuffer) — everything below matches how this scene always
        # rendered, just with an extra copy step in between.
        target.use()
        self.bg_capture_fbo.color_attachments[0].use(location=0)
        self.blit_program["u_tex"] = 0
        self.blit_vao.render(moderngl.TRIANGLES)

        cam_time = cam.time if cam else self.time
        cam_punch = cam.punch if cam else 0.0
        yaw = 0.75 * math.sin(cam_time * 0.15) + cam_punch * 0.12
        pitch = 0.50 * math.sin(cam_time * 0.11 + 1.0)
        roll = 0.40 * math.sin(cam_time * 0.08 + 2.4) + cam_punch * 0.08

        aspect = target.size[0] / target.size[1]
        proj = _perspective_matrix(self.fov, aspect, 0.1, 10.0)
        model = _rotation_z(roll) @ _rotation_x(pitch) @ _rotation_y(yaw)
        view = _translation_z(-self.distance)
        mvp = proj @ view @ model
        mvp_col_major = mvp.T.astype("f4").copy()

        # Fresnel-like rim term for the glass material (see
        # LOGO_FRAGMENT): the plane's own local
        # normal (0,0,1), rotated by the SAME model matrix as the
        # geometry, tells us how edge-on the plane currently is to the
        # camera. A Schlick-like curve (low near dead-on, rising toward
        # edge-on) is more realistic than a flat linear ramp — but
        # normalized against this SCENE's own actual tilt range rather
        # than the textbook 0..1 cosine range: verified numerically that
        # this scene's yaw/pitch/roll animation never tilts the plane
        # more edge-on than abs(normal.z) ~= 0.64, so a raw Schlick
        # curve (which only really moves in the last ~10% near true
        # grazing) would barely react at all across the plane's actual
        # motion. Remapping that real range to a full 0..1 "how edge-on,
        # relative to how edge-on this scene ever gets" first is what
        # makes the material visibly react to perspective during normal
        # playback instead of only at an unreachable extreme.
        normal_world = model @ np.array([0.0, 0.0, 1.0, 0.0], dtype="f4")
        cos_theta = abs(float(normal_world[2]))
        t_edge = float(np.clip((1.0 - cos_theta) / (1.0 - FRESNEL_COS_MIN), 0.0, 1.0))
        fresnel = FRESNEL_F0 + (1.0 - FRESNEL_F0) * (t_edge ** 3)

        # Refraction density scales UP with the same Fresnel/view-angle
        # term — a steeper viewing angle means light crosses more
        # effective glass thickness (the classic reason a windshield
        # looks far more warped at a grazing glance than straight on),
        # so the background should bend more as the plane tilts, not a
        # constant amount regardless of perspective.
        density = LOGO_REFRACT_DENSITY * (1.0 + fresnel * 1.2)

        # View direction in the plane's own LOCAL frame, for the glossy
        # specular highlight (LOGO_FRAGMENT): un-
        # rotate the world "toward camera" direction (0,0,1), the same
        # reference axis normal_world above is measured against, by the
        # inverse of `model` — which for a pure rotation matrix is just
        # its transpose — so the highlight is computed in the same local
        # (u, v, out-of-plane) space the fragment shader's bump normal
        # already lives in, and correctly slides across the surface as
        # the plane tilts through its existing animation.
        view_dir_local = (model.T @ np.array([0.0, 0.0, 1.0, 0.0], dtype="f4"))[:3]

        self.video.texture.use(location=0)
        self.logo_program["u_logo"] = 0
        self.logo_program["u_mvp"].write(mvp_col_major.tobytes())
        self.logo_program["u_glass_alpha"] = LOGO_BACK_SLICE_ALPHA
        self.logo_program["u_fresnel"] = fresnel
        self.logo_program["u_view_dir"] = tuple(view_dir_local.tolist())
        glitch_active = self.time < self.glitch_active_until
        self.logo_program["u_glitch_amount"] = 1.0 if glitch_active else 0.0
        self.logo_program["u_glitch_seed"] = self.glitch_seed

        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        # Stacked-extrusion "3D": draw farthest-back (most negative Z,
        # darkest) first, so simple back-to-front painter's-algorithm
        # overlap looks correct with no depth buffer involved. Every
        # slice is the exact same crisp flat quad + per-pixel video
        # sampling as before — see the "Video plane pass" comment above
        # for why that matters. The very front slice (i=0, Z=0) is
        # handled separately below with the background-refraction glass
        # material instead of this simpler per-slice tint, since it's
        # the "face" the viewer actually looks through.
        for i in range(LOGO_EXTRUDE_SLICES, 0, -1):
            t = i / LOGO_EXTRUDE_SLICES  # 1.0 (farthest back) .. near 0.0
            self.logo_program["u_z_offset"] = -LOGO_EXTRUDE_DEPTH * t
            self.logo_program["u_darken"] = LOGO_EXTRUDE_MIN_DARKEN + (1.0 - LOGO_EXTRUDE_MIN_DARKEN) * (1.0 - t)
            self.logo_vao.render(moderngl.TRIANGLES)

        # Front face: unit 0 stays the video texture (bound above), unit
        # 1 is the captured background so LOGO_FRAGMENT_GLASS can sample
        # it a second time with a refracted UV.
        self.bg_capture_fbo.color_attachments[0].use(location=1)
        self.logo_glass_program["u_logo"] = 0
        self.logo_glass_program["u_background"] = 1
        self.logo_glass_program["u_mvp"].write(mvp_col_major.tobytes())
        self.logo_glass_program["u_z_offset"] = 0.0
        self.logo_glass_program["u_viewport_size"] = (float(target.size[0]), float(target.size[1]))
        self.logo_glass_program["u_glass_alpha"] = LOGO_FRONT_ALPHA
        self.logo_glass_program["u_fresnel"] = fresnel
        self.logo_glass_program["u_density"] = density
        self.logo_glass_program["u_view_dir"] = tuple(view_dir_local.tolist())
        self.logo_glass_program["u_glitch_amount"] = 1.0 if glitch_active else 0.0
        self.logo_glass_program["u_glitch_seed"] = self.glitch_seed
        self.logo_glass_vao.render(moderngl.TRIANGLES)

        ctx.disable(moderngl.BLEND)

    def teardown(self):
        self.video.release()
