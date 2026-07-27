# Changelog

This tracks tagged versions of the visual rig so we can always see what
changed and roll back if a change doesn't work out. Each version is both
a git tag and a section below in plain language (no need to read code to
know what a version contains).

## How to use this (see also README.md "Version control" section)

- See what version you're on: `git describe --tags`
- Go back to an earlier version: `git checkout v1` (or v2, v3, ...)
- Go back to the latest: `git checkout main`
- Compare two versions: `git diff v1 v2`

## v59 — 2026-07-28 — Fixed window freeze when quitting out of fullscreen

- **Fixed a freeze/hang on exit**: quitting (ESC) while running in
  fullscreen (`FULLSCREEN = True` in config.py) could leave the window
  stuck on screen, unresponsive to any further input, instead of
  actually closing. Root cause: the app called `glfw.terminate()`
  directly on a window still attached to a monitor (true GLFW
  fullscreen) — destroying/terminating in that state asks the OS to
  tear down the fullscreen presentation and destroy the window in the
  same breath, and on macOS that teardown can race with the process
  exiting, leaving the WindowServer stuck mid-transition with a half-
  destroyed window that never finishes closing.
- Fixed by explicitly switching the window back to windowed mode
  (`glfw.set_window_monitor(window, None, ...)`) and polling a few
  frames to let that settle BEFORE destroying the window — the
  standard GLFW-recommended pattern for a clean fullscreen exit. This
  only runs if the window is actually in true fullscreen
  (`glfw.get_window_monitor` returns non-null); it's a no-op for the
  normal windowed case, so this doesn't change behavior for anyone not
  running `FULLSCREEN = True`.
- Also fixed a related gap found while debugging this: nothing ever
  released scene resources (video decoders, extra framebuffers — see
  `Scene.teardown()`), closed the MIDI port, or released the moderngl
  context on exit — the app just let the process die out from under
  them. Added `SceneManager.teardown()` (calls every scene's own
  `teardown()`) and explicit MIDI-port/context cleanup, run before the
  window is destroyed.
- Verified: confirmed via a stashed A/B comparison that an unrelated
  early-exit quirk seen while testing in this sandboxed environment
  (a scene auto-switching a few seconds after launch, then the process
  ending) reproduces IDENTICALLY on the pre-fix code, so it's a
  pre-existing artifact of running an interactive GUI app through this
  particular background-process setup, not something this change
  caused. Could not interactively verify the actual ESC-while-
  fullscreen repro live in this environment (no persistent GUI/keyboard
  session) — recommend confirming on the real show machine, especially
  with `FULLSCREEN = True` on the actual projector/output display.

## v58 — 2026-07-25 — Scene 5's logo: reverted to v53

- **Reverted the logo material to its v53 state** per feedback — v54's
  transparency push, v55's opacity/rounded-profile changes, v56's
  single-unified-shader rewrite, and v57's backlight + blur-reduction
  branch are all undone. None of v54-v57 had been committed (still on
  git tag v45), so this was a manual reconstruction back to v53's
  actual code rather than a `git checkout`: two separate fragment
  shaders again (`LOGO_FRAGMENT` for the back/side slices,
  `LOGO_FRAGMENT_GLASS` for the front face), `LOGO_FRONT_ALPHA=0.7` /
  `LOGO_BACK_TARGET_OPACITY=0.3` (compounding to ~9% back-stack weight,
  ~70% front, ~21% plain background), a straight linear Z-offset/darken
  ramp (not v55's rounded quarter-circle profile), and no backlight/
  depth_t/refraction-branch code.
- Verified by compiling both shaders against a standalone ModernGL
  context and running the full scene's update()/render() over 30
  frames with large time steps (to sweep the tilt range quickly),
  including through a resize() — output matches v53's documented alpha
  values exactly (front 0.7, back per-slice ~0.0252).

## v57 — 2026-07-25 — Scene 5's logo: backlight, fixed "aerogel"-looking blur

- **Added a backlight**, a light source positioned behind the screen
  shining toward the viewer through the glass, per feedback specifically
  requesting this. A light in front only produces a reflection-style
  highlight (already had one — the existing key-light specular); a
  light from behind needs a different technique since the standard
  Blinn-Phong half-vector trick degenerates when light and view
  direction are nearly opposite. Used the classic transmission/rim-glow
  approach for backlit translucent materials instead: a warm-tinted glow
  wherever the letter shape's own edge gradient is large (concentrated
  right at curved edges — the same geometry the refraction is keyed to)
  plus a global rim contribution from the existing Fresnel term, so
  light visibly rims more of the silhouette as the plane tilts.
- **Fixed the "looks like aerogel"/blurry complaint**: root cause was
  ALL 15 stacked slices independently warping + chromatic-aberration-
  splitting the background — under alpha blending, that many near-
  duplicate, slightly-offset samples average out into a soft milky wash
  (the same way a long exposure blurs a moving subject), which reads as
  diffuse frosted foam rather than clear glass. Full chromatic
  refraction is now applied only to the ~8 slices closest to the true
  front face (`u_depth_t < 0.35`); the remaining back/side slices take
  one plain, unwarped background sample instead — a uniform (per-draw-
  call) branch, not a per-pixel one, so it's free on any GPU.
- Verified numerically: typical local edge-glow contribution ~0.5-0.65
  at real edge gradients (clamped to 1.0 at the theoretical extreme);
  refraction offset worst-case ~0.56 screen-uv units (down from ~0.67,
  since the branch also removes the old depth-based upscaling that no
  longer serves a purpose once back slices skip refraction entirely),
  typical case unchanged ~0.045; 8 of 15 slices now do the expensive
  chromatic sampling instead of all 15.
- Verified by compiling the shader against a standalone ModernGL
  context and running the full scene's update()/render() over 30
  frames with large time steps (to sweep the tilt range quickly),
  including through a resize().

## v56 — 2026-07-25 — Scene 5's logo: rewritten as one unified glass material

- **Full rewrite of the logo's material**, per feedback that it looked
  like three separately-textured layers (the front "surface", the
  rounded "radius", and the flat "side/back") rather than one coherent
  piece of glass. Root cause: the front face and the back/side slices
  were two ENTIRELY DIFFERENT fragment shaders (`LOGO_FRAGMENT_GLASS`
  did background refraction + chromatic aberration + gloss; the plain
  `LOGO_FRAGMENT` back/side slices only did a flat tint + darken) —
  structurally two different materials, not one.
- **Merged into a single fragment shader** (`LOGO_FRAGMENT`) used by
  every slice of the extrusion, front and back alike. Each slice is
  fed one continuous parameter, `u_depth_t` (0 at the front face, 1 at
  the farthest-back slice, from the same rounded/quarter-circle profile
  that already shaped the Z-spacing) that smoothly reshapes:
  - **opacity** — per-slice alpha scales with depth (front thinner/
    clearer, back slices ~4x more opaque), replacing the old two
    unrelated alpha constants;
  - **video-tint vs. refracted-background mix** — deeper slices lean
    more toward the character's own tinted color (a Beer-Lambert-ish
    "light picks up more of the medium's color the further it
    travels" cue), shallower slices lean more toward the clear
    refracted background;
  - **refraction strength** — scales up slightly with depth on top of
    the existing Fresnel/view-angle scaling, so deeper "glass" bends
    the background more, same idea as a thicker window warping a
    grazing view more.
  - Every slice — not just the front — now does full background
    refraction + chromatic aberration, so the sides read as genuine
    glass too instead of a flat shaded chamfer.
- **Glossier, more light-responsive**: added a second, tight Blinn-Phong
  specular lobe on top of the existing broad sheen (a "glint" on top of
  a "sheen" — the combination that actually reads as glossy/slick
  rather than one dull highlight), both lobes scaled by the existing
  Schlick-like Fresnel term so the material visibly reacts more
  strongly to light as the plane tilts.
- Verified numerically before implementing: per-slice alpha curve
  (`LOGO_BASE_ALPHA=0.07`, `LOGO_ALPHA_FRONT_RATIO=0.25`) gives a
  front-slice alpha of ~0.018 and a back-slice alpha of ~0.07, with the
  whole 15-slice stack compounding to ~0.43 cumulative opacity at rest
  and ~0.78 at the plane's most edge-on real pose — translucent
  throughout, never pinned near fully opaque. Refraction offset
  worst-case ~0.67-0.77 screen-uv units (clamped in-shader, NaN/Inf-
  free), typical case ~0.045.
- Verified by compiling the unified shader against a standalone
  ModernGL context and running the full scene's update()/render() over
  30 frames with large time steps (to sweep the tilt range quickly),
  including through a resize().

## v55 — 2026-07-25 — Scene 5's logo: reverted transparency push, more opaque + rounded back/side slices

- **Reverted v54's "as transparent as possible" pass** — `LOGO_FRONT_
  ALPHA` back to 0.7 (from 0.22).
- **Back/side slices made more opaque than even the original baseline**
  per feedback: `LOGO_BACK_TARGET_OPACITY` 0.3 -> 0.6 (not just
  reverted — pushed further). Verified numerically: the back/side stack
  now carries ~18% of the final pixel's color (up from ~9% at the
  original 0.3 baseline), front face still ~70%, plain background ~12%.
- **Smoother/rounded bevel profile**: the back/side slices' Z-spacing
  and darkening used to follow a straight linear ramp (constant rate
  the whole way), which kinks sharply where it meets the flat front
  face and again where it meets the side — a mitered corner, not a
  rounded one. Both now follow a quarter-circle profile instead
  (`cos`/`sin` of the slice parameter over 0..pi/2) — zero slope at the
  front (tangent to the flat face, so slices near the front barely
  change from one to the next) and maximum slope at the back (tangent
  to the side, changing fastest right at the edge) — reads as a genuine
  rounded fillet rather than a hard chamfer. Verified numerically: the
  slope ratio between the back and front ends of the profile is
  ~13000:1, vs. a flat 1:1 for the old linear ramp.
- Verified by compiling both logo shaders against a standalone ModernGL
  context and running the full scene's update()/render() over several
  frames, including through a resize().

## v54 — 2026-07-25 — Scene 5's logo: pushed as transparent as possible

- **`LOGO_FRONT_ALPHA` 0.7 -> 0.22, `LOGO_BACK_TARGET_OPACITY` 0.3 ->
  0.08** per feedback to make it as transparent as possible. Verified
  numerically: the front face now carries only ~22% of the final
  pixel's color (down from ~70%), the back/side stack ~6% (down from
  ~9%), and the plain undistorted background dominates at ~72% (up from
  ~21%).
- The alpha-cutout discard (`if (alpha <= 0.01) discard;`, unchanged)
  still fully skips drawing anywhere the letter shapes aren't, so the
  logo stays a legible silhouette rather than fading to nothing — at
  this opacity it reads mainly through its edges (Fresnel rim +
  specular gloss, both left at full strength) rather than flat fill
  color, which is consistent with how thin/clear glass actually looks.
- Verified by compiling both logo shaders against a standalone ModernGL
  context and running the full scene's update()/render() over several
  frames.

## v53 — 2026-07-25 — Scene 5's logo: fixed blur, angle-reactive light, anti-aliased edges

- **Fixed "blurry texture"**: the sinusoidal "shimmer" term (added in
  v51) applied a rapidly-varying warp offset across the ENTIRE letter
  surface, not just its edges — under linear texture filtering this
  smeared the background sample into visual noise rather than a
  deliberate distortion. Dropped it entirely; refraction is now driven
  purely by the letter shape's own edge gradient, which is near-zero in
  flat interior regions — those now sample the background cleanly, with
  all the bending concentrated at the actual geometry (edges/curves).
- **Material now reacts to viewing angle** (perspective), not just a
  flat rim brighten: the Fresnel term is now a Schlick-like curve
  (`FRESNEL_F0` at dead-on, rising toward 1.0) instead of the old linear
  ramp — but remapped against this scene's own actual tilt range
  (verified numerically: the plane's yaw/pitch/roll animation never
  gets more edge-on than `abs(normal.z) ~= 0.64`, so a textbook Schlick
  curve over the full 0..1 range would barely move at all in practice).
  Both the refraction density and the specular sheen's intensity now
  scale with this same term each frame — steeper viewing angle bends
  the background more (more effective glass thickness the light
  crosses, same reason a windshield warps more at a grazing glance) and
  the highlight brightens, instead of staying constant regardless of
  tilt.
- **Smoothed the "fake"-looking edges**: the alpha cutout now sizes its
  smoothstep transition band from `fwidth(lum)` (how fast luminance
  changes between screen-space neighbor pixels) instead of a fixed
  luminance-space band — this keeps the edge anti-aliased to
  approximately one screen pixel regardless of the logo's on-screen
  size, fixing jagged/fake-looking edges without the earlier fixed band
  being too soft or too sharp depending on scale.
- Verified numerically: worst-case combined refraction offset (both
  mask-gradient axes maxed, chromatic split, dynamic density at the
  plane's most edge-on real pose) ~0.64 screen-uv units — large, but
  only at that rare edge+extreme-tilt combination, always clamped
  in-shader, NaN/Inf-free; typical case near dead-on stays ~0.045.
  Verified by compiling both logo shaders against a standalone ModernGL
  context and running the full scene's update()/render() over 30
  frames with large time steps (to sweep the tilt range quickly),
  including through a resize().

## v52 — 2026-07-25 — Scene 5's logo: front glass face now actually dominates (v51's effects were invisible)

- **Root cause of v51's gloss/warp being invisible**: the front glass
  face and the 14 back/side slices were all sharing one alpha value
  solved so their *combined* stack read as translucent — but that
  meant the front face (the one with all the new gloss/refraction
  work) only carried ~5-10% of the final pixel's color. The rest was
  the plain matte back-stack tint and the undistorted background
  showing through underneath — so the glossy/warped material was
  technically rendering, just drowned out.
- **Split into two separate alphas**: `LOGO_FRONT_ALPHA` (0.7, a direct
  opacity — the front face is the primary surface being looked at/
  through, so it should dominate) and `LOGO_BACK_SLICE_ALPHA` (solved
  the same compounding-alpha way as before, but only across the 14
  back/side slices, targeting a modest 0.3 cumulative — just a subtle
  bevel/depth cue). Verified numerically: front face now carries ~70%
  of the final pixel, the back stack ~9%, plain background peeking
  through underneath ~21% (which is what keeps it reading as
  translucent rather than a solid card despite the front's own fairly
  high alpha).
- **Chromatic aberration** added to the front face's background
  sampling (R/G/B channels read through slightly different refraction-
  offset scales) — the classic, always-visible "looking through thick
  glass/a lens" cue. This matters because the plain per-pixel warp
  offset (v49/v51) is only visible where the background already has
  sharp detail to distort; a color-fringed edge reads as glass
  regardless of what's behind it.
- **Front face lightened**: less desaturation (0.45 -> 0.2) and a
  lighter tint (was darkening ~20%, now ~5-8%) than the back/side
  slices, which keep the darker "smoked"/shadowed look appropriate for
  an extrusion's hidden sides — this is what was reading as uniformly
  "too smoked" before.
- **Specular broadened and brightened** on the front face (shininess
  24 -> 9, intensity 0.6 -> 1.1) and back/side slices (24 -> 10, 0.5 ->
  0.8) so the glossy sheen is clearly visible rather than a near-
  invisible pinpoint highlight.
- **Refraction density raised** (`LOGO_REFRACT_DENSITY` formula's depth
  multiplier 12 -> 20, ~1.6 -> 2.0 at the current extrusion depth).
- Verified numerically: worst-case combined refraction offset (incl.
  the chromatic split) ~0.22 screen-uv units, still explicitly clamped
  in-shader and NaN/Inf-free. Verified by compiling both logo shaders
  against a standalone ModernGL context and running the full scene's
  update()/render() for several frames, including through a resize().

## v51 — 2026-07-25 — Scene 5's logo: glossy specular sheen, denser refraction

- **Glossy specular highlight**, on both the front glass face and the
  extrusion's back/side slices: a fake surface normal is "bumped" from
  the same per-pixel letter-edge gradient already used for refraction
  (strongest at curves/corners, flat elsewhere), lit with a fixed key
  light via a Blinn-Phong highlight. The view direction feeding it is
  computed CPU-side from the plane's own rotation (un-rotating the
  world "toward camera" axis by the model matrix's transpose, same
  trick as the existing Fresnel term), so the highlight actually slides
  across the surface as the plane tilts through its existing animation
  instead of looking painted on.
- **Denser refraction**: the background-warp offset (from v49) is now
  scaled by `LOGO_REFRACT_DENSITY`, derived from `LOGO_EXTRUDE_DEPTH`
  itself (1.0 + depth*12 ≈ 1.6 at the current depth) rather than a bare
  constant — a thicker glass block now genuinely bends the background
  more, tying the warp strength to both the logo's actual geometry
  (edge gradient + extrusion depth) and its material (the density
  multiplier), per feedback asking for exactly that connection. Base
  gradient sampling width and shimmer amplitude were also widened for a
  broader, more visible "bending zone" around each letter's edges.
- Verified numerically before tuning: worst-case combined refraction
  offset ~0.15 screen-uv units (up from ~0.048), typical case ~0.08,
  still bounded/NaN-free and still explicitly clamped in-shader;
  specular contribution ranges 0 to ~0.55 across sampled view angles,
  also NaN/Inf-free. Verified by compiling both logo shaders against a
  standalone ModernGL context and running the full scene's update()/
  render() for several frames, including through a resize() call.

## v50 — 2026-07-25 — Scene 5's logo: fixed opaque-looking glass (alpha compounding bug)

- **Fixed the stacked-extrusion glass reading as "completely opaque"**
  per feedback, despite each individual slice's alpha being tuned for
  translucency. Root cause: `LOGO_GLASS_ALPHA` was applied directly as
  each of the 15 stacked slices' own alpha, but standard "over" alpha
  blending compounds across layers — `1-(1-a)^n` — so 15 layers at
  alpha 0.5 each converges to ~99.997% opaque no matter how
  translucent any single slice looks alone (verified numerically).
- `LOGO_GLASS_ALPHA` is now solved so the FULL 15-layer stack converges
  to a target *cumulative* opacity (`LOGO_TARGET_OPACITY = 0.5`)
  instead: ~0.045 per-slice alpha, verified numerically to produce
  ~0.50 cumulative opacity at rest, rising to ~0.79 at the most extreme
  Fresnel-boosted grazing angle (the correct direction — real glass
  gets more reflective/opaque at grazing angles too). No other logic
  changed.
- Verified by compiling every shader against a standalone ModernGL
  context and running update()/render() for several frames.

## v49 — 2026-07-25 — Scene 5's logo: actual background refraction, not just tint

- **Real "seen through glass" refraction**, per feedback that v48's
  tint + reduced alpha still read as a faded image, not glass. The
  scene's bg braid + ground mesh now render into an offscreen texture
  (`bg_capture_fbo`, a new FBO sized to the real output resolution,
  recreated on resize) before being copied onto the actual `target`
  via a plain blit pass — this makes "what's currently behind the
  logo" available as a texture the logo itself can sample a second
  time.
- The extrusion's front-most slice (the "face" actually being looked
  through) now uses a new fragment shader, `LOGO_FRAGMENT_GLASS`,
  instead of the flat-tint material the back/side slices still use:
  it samples the captured background at a UV offset by (1) the local
  gradient of the letter shape's own alpha mask — strongest right at
  a curved edge, near-zero in flat interior/exterior regions, so it
  behaves like a real embossed glass letter bending light most at its
  boundary — plus (2) a slow sinusoidal shimmer so flat interior areas
  aren't perfectly optically flat either. The warped sample is mixed
  mostly-background/some-video-tint so the character still reads as
  itself.
- Verified numerically before writing the GLSL: worst-case combined
  refraction offset ~0.048 in screen-uv units, typical single-edge
  contribution ~0.007, no NaN/Inf — bounded enough to always sample
  nearby background rather than an unrelated part of the screen; UV is
  also explicitly clamped to [0,1] in the shader regardless. Verified
  by compiling every shader in the file against a standalone ModernGL
  context, then instantiating the actual scene, running update()/
  render() for several frames (including through a resize() call) into
  an offscreen framebuffer, all without errors.

## v48 — 2026-07-25 — Scene 5's logo: shallower depth, smoked-glass material

- **Extrusion depth halved** (`LOGO_EXTRUDE_DEPTH` 0.1 -> 0.05) per
  feedback.
- **Logo material changed to translucent "smoked glass"**: each stacked
  slice's color is now desaturated and cool-tinted, and its opacity is
  scaled down (`LOGO_GLASS_ALPHA` = 0.5) rather than fully opaque — see-
  through rather than solid, with stacked translucent layers building
  up into a more substantial look, the way a thick block of glass reads
  differently than a single thin pane. Also added a Fresnel-like rim
  term (brighter, slightly more opaque at grazing angles), computed
  once per frame from the plane's own rotated normal (it's still a flat
  surface, so this is uniform across it rather than per-pixel) — the
  classic visual cue that sells a glass/translucent material as the
  plane tilts through its existing animation.
- Verified numerically before implementing the Fresnel term: sampled it
  across the scene's actual yaw/pitch/roll ranges and confirmed a sane,
  bounded 0.0 (facing the camera dead-on) to ~0.36 (at the most extreme
  tilt combinations) with no instability. Also verified by launching
  the app and confirming the shader still compiles and runs with no GL
  errors.

## v47 — 2026-07-25 — Scene 5's logo now has real depth (stacked-extrusion technique)

- **Dropped the dark contrast outline in scene 5** (`logo_video_fractal.py`)
  per feedback — superseded by the 3D depth below, which does the job
  of separating the logo from the background on its own.
- **First attempt at "make the logo 3D" discarded**: subdividing the
  quad into an 80x80 grid and displacing each vertex along Z by the
  video's own per-vertex luminance, with normal-based emboss shading on
  top, shipped "completely distorted, jagged" per feedback. Root cause:
  vertex displacement can only be as smooth/precise as the mesh
  resolution, but the alpha cutout that actually defines the visible
  silhouette is evaluated per-PIXEL — there's no practical grid
  resolution at which a displaced, linearly-interpolated shape reliably
  lines up with crisp per-pixel letter edges. That mismatch between
  "what's opaque" and "what's extruded" is what read as distortion.
- **Replaced with the classic "stack of cutouts" technique** for faking
  extruded 2D shapes in 3D: kept the ORIGINAL simple flat quad exactly
  as it always was (so the visible silhouette is exactly as
  pixel-precise as before — no mesh resolution involved at all), and
  draw 15 progressively darker copies of it stacked behind the front
  one along Z (farthest/darkest first, nearest/original-brightness
  last, correct back-to-front order with no depth buffer needed).
  Viewed through the scene's existing camera tilt, that stack reads as
  a genuine beveled side/thickness. Every individual slice is still
  just the same crisp, unmodified per-pixel video sampling as always —
  the video's own animation, the glitch effect, and the camera tilt are
  all otherwise unchanged.
- Verified numerically: the darken/Z-offset progression across all 15
  slices lands exactly on the intended range (darkest/farthest at
  -0.1 depth/0.35 brightness, front slice at 0 depth/1.0 brightness,
  evenly spaced in between). Also verified by launching the app and
  confirming the shader still compiles and runs with no GL errors.

## v46 — 2026-07-24 — Thinner logo outline; scenes 5 and 6 swapped

- **Logo contrast outline (scenes 4 and 6 — see below for the renumber)
  thinned slightly** (`OUTLINE_THICKNESS` 0.004 -> 0.003).
- **Swapped scene positions 5 and 6**: `kaleidoscope_video.py` is now
  reached via program 5 / key `6` (was key `5`), and `logo_video_fractal.py`
  is now program 4 / key `5` (was key `6`) — just `config.py`'s
  `SCENE_PROGRAM_MAP`, no change to either scene's own behavior. Updated
  every "scene 5"/"scene 6" reference across the docs and scene files
  to match the new numbering (`kaleidoscope_video.py`'s own header
  comment, `feedback_trails.py`'s docstring, `hollow_logo.py`'s docstring,
  and README.md) — CHANGELOG.md entries below this one are left as-is
  since they're a historical record of what was true at the time.

## v45 — 2026-07-24 — Scene 6: ground mesh triangles now actually shaded (real topography), snappier trigger, more translucent

- **Real per-vertex shading, not a flat color** — per feedback that
  every triangle showing the same color value "disrupts the 3D feel."
  The fill vertex shader now derives an actual surface normal from the
  wobble height field (samples the same height noise a small step away
  in both ground-plane directions, builds the two implied tangent
  vectors, crosses them) and computes simple directional lighting from
  it, so ridges/slopes now genuinely catch or lose light relative to
  their neighbors — visible shadows and highlights that track the
  mesh's actual undulation, not a uniform wash.
- **Caught and fixed a real problem while building this**: the first
  version used the wobble's true (gentle) slope with a near-overhead
  light direction, which verified numerically to cluster all normals
  within a ~0.02-wide band — i.e., shading so subtle it would have
  looked completely flat again, the same complaint as before. Fixed
  with two changes verified together: exaggerating the slope used for
  the normal calculation only (`SHADE_STEEPNESS`, the displayed geometry
  itself is untouched) and switching to a grazing, mostly-sideways
  light direction, which is far more sensitive to slope than an
  overhead one.
- **That fix then shipped with a second real problem** — per feedback,
  the shadows "switch on and off suddenly" and looked "randomly
  placed." Root cause, verified numerically: the shading sampled the
  FULL wobble height field (both noise octaves) at a small step and
  exaggerated the resulting slope 15x. The finer, faster-scrolling
  octave contributes high-frequency detail a 15x-exaggerated, small-step
  finite difference is extremely sensitive to, so neighboring mesh
  vertices (which each sample independently) could land on quite
  different normals even though the underlying surface itself is
  smooth — a noisy per-vertex signal rather than a coherent moving
  shadow. Fixed by basing the shading normal on only the smoother,
  dominant octave, sampled at a wider step, with less exaggeration.
  Verified numerically: mean difference between ADJACENT vertices
  dropped from 0.115 to 0.040 (a real jump would be a smooth gradient
  across many vertices, not a large swing between neighbors), and
  frame-to-frame change at a single fixed vertex is only ~0.001 over
  1/60s — while overall contrast stays comparable (shading from ~0.82x
  to ~1.46x brightness), so the visible range didn't shrink, only the
  incoherent flicker did.
- **Snappier trigger response**: attack shortened 0.06s -> 0.02s per
  feedback ("decrease the attack").
- **More translucent overall**: base opacity 0.3 -> 0.18 and peak
  opacity 0.75 -> 0.45 (kept proportional, so the trigger-glow jump
  stays clearly visible) per feedback that the fill was too opaque.

## v44 — 2026-07-24 — Scene 6: ground mesh triangles now always filled (3D surface feel at rest)

- **Every triangle in scene 6's ground mesh is now filled at all
  times**, not just the wireframe edges — an always-present translucent
  base tint so the mesh reads as a solid, glass-like surface even at
  rest, before any MIDI has been received, per feedback wanting a better
  3D feel in the initial state.
- The MIDI-triggered glow (channel 10 / "pads") now brightens AND
  saturates a triangle on top of that base fill, rather than fading in
  from nothing — same smooth attack/release envelope as before, just
  rebased so it eases between the base tint and a brighter peak glow
  instead of between invisible and the glow.
- **First attempt at this shipped with values too subtle to read as any
  visible change at all** (per direct feedback: "still hollow") — base
  opacity 0.06 was imperceptible against the background. Corrected with
  a deliberately bold jump rather than a marginal tweak: base opacity
  0.06 -> 0.3, peak opacity 0.4 -> 0.75 (raised together so the
  MIDI-triggered brightening stays clearly distinguishable from the new,
  much-more-visible resting state), plus brighter/more saturated base
  color values.
- Verified numerically: alpha now stays correctly bounded between the
  base (0.3) and peak (0.75) values across the full envelope range —
  a 2.5x jump on trigger, clearly perceptible in both states — with
  saturation/brightness increasing smoothly alongside it; verified
  syntax and that the shader still compiles.

## v43 — 2026-07-24 — Ground-mesh lighting now glows smoothly; kaleidoscopic fractal moved to scene 2

- **Ground-mesh lighting (scene 6) redesigned around a smooth per-
  triangle glow envelope** instead of a hard per-tick on/off strobe, per
  feedback wanting the triangles more translucent with a slower release.
  Each triangle now tracks (CPU-side) the real time it was last picked;
  a fragment-shader envelope (quick attack, ~0.06s; slow exponential
  release, ~0.9s, decaying below visibility by ~4.2s) reads elapsed time
  since that pick to compute its glow brightness, rather than a binary
  "is this triangle selected on this exact tick" hash check. Peak
  opacity also lowered (0.75 -> 0.4) for the requested translucency.
  Because the glow is purely a function of elapsed time, there's no
  separate "revert to hollow" step anymore — once channel 10 goes
  quiet, nothing new gets picked, so every triangle's glow simply decays
  away on its own, which also means the hollow/lit transition itself is
  now smooth rather than an abrupt cutoff.
- Implementation note: this needed real per-triangle timing, which a
  stateless GPU hash (the previous approach) can't provide — each
  triplet tick, Python now picks a new random subset of triangle
  indices, stamps them with the current time in a small numpy array,
  and rewrites a small dynamic vertex buffer (one float per triangle,
  repeated per vertex). Only happens on tick boundaries (~100-300ms
  apart), so the cost is negligible.
- **Change of heart on where the kaleidoscopic folding fractal
  belongs**: rather than keep it (or its removal) confined to scene 6,
  it's been moved to become scene 2's new background, replacing that
  scene's previous ping-pong feedback/blur buffer with two drifting
  blobs entirely. Scene 2 keeps its hollow-outline logo overlay
  (shared with scenes 1 and 3, unchanged) but the accumulation buffers,
  camera-driven domain warp, and blob motion are all gone. Scene 6
  itself is unaffected by this — it keeps the ground-mesh lighting
  above and no fractal.
- Verified numerically: simulated the new glow envelope across a range
  of elapsed times, confirming the attack ramps smoothly to peak
  opacity 0.4 by 0.06s, and decays below the visibility threshold by
  ~4.2s; also confirmed the "never picked" initial state (a very large
  elapsed time) evaluates cleanly to 0 with no NaN/Inf risk. Verified
  both scenes' shaders compile and run by launching the app normally
  (default scene left unchanged).

## v42 — 2026-07-24 — Scene 6: removed the folding fractal, ground mesh now lights up on MIDI clock

- **Removed the kaleidoscopic folding-fractal bloom from scene 6**
  (`logo_video_fractal.py`) — channel 10 ("pads") no longer drives it;
  the background is back to just the braid. All the fractal's shader
  code, uniforms, and Python-side bloom/phase state were removed
  outright rather than left dormant.
- **Channel 10 now drives the ground mesh instead**: any trigger on
  that channel lights up a random subset of the mesh's triangles
  (filled, not wireframe), and which subset is lit changes on every
  MIDI-clock-synced triplet tick — a strobing/twinkling effect timed to
  the tempo. Reverts to the fully hollow wireframe (no filled triangles
  at all) once channel 10 has gone quiet for a moment (0.4s).
- **Implemented with zero per-tick CPU-side buffer rebuilding**: every
  triangle already carries a random seed baked in at mesh-build time
  (a new, separate `GL_TRIANGLES` vertex buffer alongside the existing
  wireframe `GL_LINES` one, sharing the same underlying jittered grid
  and wobble motion); a fragment-shader hash of that seed combined with
  a tick counter decides whether THIS triangle happens to be lit on
  THIS tick. Only the tick counter (a single uniform) changes per tick.
- Verified numerically: across simulated ticks, the lit fraction tracks
  the configured target (~16-19% actual vs. 18% target) and the actual
  set of lit triangles overlaps only ~15-20% between consecutive ticks
  — confirming a real, visibly-changing random subset each tick rather
  than a frozen or degenerate pattern.

## v41 — 2026-07-24 — Scene 6: wobbling wireframe ground mesh for depth

- **Added a wobbling wireframe ground mesh to scene 6**
  (`logo_video_fractal.py`), filling the bottom of the screen — a
  jittered grid of points (regular grid + per-point random offset, a
  simple stand-in for a true Voronoi/Delaunay triangulation), split into
  triangles and rendered hollow (edges only, `GL_LINES`, no filled
  faces), like a pond or ocean surface viewed at an angle.
- **Built as genuine 3D geometry with real perspective projection**
  (reusing the same `_perspective_matrix` helper the logo plane already
  uses), not a faked 2D taper — vertices are authored directly in
  view-ready coordinates (a flat plane below eye level, receding into
  the screen), so it naturally converges to a single vanishing point at
  screen center as depth increases, exactly the "expanding toward the
  center" sense of depth asked for.
- **Wobbles via two octaves of scrolling value-noise in the vertex
  shader** (GPU-side, so the static vertex buffer never needs
  re-uploading per frame) for a flowing, liquid undulation rather than a
  rigid grid.
- **Guaranteed not to overlap the braid**: verified numerically first
  that the braid's own strand-wobble + glow falloff can reach as low as
  y=-0.261 (screen-space) at its most extreme, then set the ground
  mesh's fade-out (and a hard discard, computed from the actual
  rendered pixel position via `gl_FragCoord` rather than the mesh's 3D
  depth) at y=-0.35 — a margin of ~0.09, independent of exactly how the
  3D projection ends up tuned.
- **Caught a real bug before it ever shipped**: the first version of the
  vertex shader computed the wobble displacement but never actually
  added the below-eye-level `GROUND_Y` offset the perspective math was
  designed around — meaning the mesh would have sat near screen center
  instead of filling the bottom of the screen as intended, silently
  invalidating all the numeric verification done beforehand (which had
  assumed `GROUND_Y` was applied). Caught by re-reading the shader
  against its own design comment, not by seeing it render wrong — fixed
  by adding a `u_ground_y` uniform and actually using it.
- Verified numerically: the mesh-building function produces the
  expected vertex count with no NaN/Inf; also verified by launching the
  app (default scene left unchanged, per earlier feedback) — since
  `SceneManager` builds every scene's shaders at startup regardless of
  which is active, this caught any shader compile errors, though the
  render-time behavior itself (only exercised while a scene is active)
  still needs a live look with scene 6 selected.

## v40 — 2026-07-24 — Dark contrast outline on the logo (scenes 4 and 6)

- **Added a thin dark rim around the video-plane logo's own silhouette**
  in both `logo_video_pulse.py` (scene 4) and `logo_video_fractal.py`
  (scene 6), so the logo stays visually separated from its background
  even when the background's current color happens to closely match the
  logo's — previously they could blend into each other with no visible
  boundary.
- Implemented in `LOGO_FRAGMENT` itself (not the background), reusing
  the same ring-sample edge-detection technique `hollow_logo.py` already
  uses: for each visible logo pixel, sample 8 points in a small ring
  around it and check whether any disagree with this pixel's own
  inside/outside classification (the same luminance threshold that
  already defines the logo's alpha cutout) — if so, it's near the
  boundary, so blend toward black. Black was chosen deliberately over a
  hue-matched or light rim, since the braid background is generally
  bright/glowing and a dark rim reads as contrast against nearly
  anything, whereas a rim closer to the background's own tonal range
  risks the same blending problem it's meant to fix.
- Verified numerically with a synthetic circular test pattern before
  touching the shader: confirmed the edge only triggers in a thin band
  right at the true boundary (within the outline-thickness parameter)
  and stays off both well inside and well outside the shape. Also
  verified by launching the app (default scene unchanged) and
  confirming both scenes' shaders still compile and run with no GL
  errors.
- Per feedback that the outline was too thick, halved
  `OUTLINE_THICKNESS` (0.008 -> 0.004) in both scenes.

## v39 — 2026-07-23 — Saved scene 4's fractal background as its own scene, scene 4 back to logo + braid (no fractal)

- **Not convinced the folding-fractal background (v38) is the right
  look for scene 4** — rather than keep iterating in place, saved the
  current working version as a new 6th scene, `scenes/logo_video_fractal.py`
  (registered in `scene_manager.py`/`config.py` as program 5, key `6`),
  so that work isn't lost while scene 4 goes back to trying new ideas.
  Both scenes use the same 3D-projected video-plane logo + glitch effect
  — a hollow white-outline version (like scenes 1-3) was tried briefly
  in the new scene, but per feedback it worsened the logo/braid color-
  matching-blend issue (a thin outline has far less opaque area than a
  filled logo to create contrast against the background), so it was
  reverted back to the filled 3D plane.
- **Scene 4 (`logo_video_pulse.py`) reverted to logo + braid, no
  fractal** — the braid background predates this round's fractal
  experimentation entirely, so only the fractal/bloom addition was
  removed; the video plane, glitch, and braid are all unchanged from
  before any of this round's background work started.
- **Caught a real bug while first stripping scene 4's background down
  to nothing** (before realizing the braid needed to stay):
  `scene_manager.py` never clears its per-scene framebuffers itself —
  every other scene fills every pixel via its own background shader, so
  this was never needed before. A scene with no background pass at all
  would have left stale/ghosted pixels from previous frames showing
  through wherever the logo plane doesn't cover it (moderngl
  framebuffers aren't auto-cleared between frames) — moot now that the
  braid fills every pixel again, but worth remembering for any future
  scene that ends up with no full-screen background layer.
- Verified by launching the app on the (unchanged) default scene:
  `SceneManager` instantiates every registered scene up front regardless
  of which is active, so this alone exercises both the new scene's and
  scene 4's shader compilation without needing to switch away from the
  default scene.

## v38 — 2026-07-23 — Scene 4's background bloom: fractal, then flowers, then a folding fractal (third design this round)

- **Two earlier attempts within this same round were discarded on
  look**: an escape-time Julia set (even after fixing its rendering
  bug, the look itself didn't read well), then a garden of procedural
  rose-curve flowers (also didn't read well). Neither had shipped, so
  no rollback was needed — just replaced in place.
- **Landed on a kaleidoscopic folding fractal** — repeated fold
  (mirror-reflect) + rotate + scale of the plane, the construction
  behind most "Mandelbox"/kaleidoscope-tunnel shader art, and a
  genuinely different fractal family from the discarded Julia set (real
  recursive, self-similar detail, per feedback wanting that back after
  the flower detour). Its coloring is a sum of a color per fold-depth,
  weighted by how far that depth has been "revealed" — not an
  escape-time threshold — so it doesn't share the earlier near-total-
  black failure mode.
- **Caught and fixed a real bug during development, before it ever
  rendered**: the first version of this computed each fold-depth's
  color from only (depth index, time, bloom) — never actually reading
  the folded position — which would have made the whole layer a flat,
  spatially-uniform color wash rather than showing any fractal
  structure. Fixed by weighting each depth's contribution by proximity
  to that depth's fold-crease lines (`min(|p.x|, |p.y|)`), which is what
  actually produces the self-similar line/crease pattern that reads as
  "fractal." Caught by numerically checking spatial variance across a
  sampled grid, not just that the numbers were in a safe range — an
  earlier check on this same feature had wrongly measured variance
  across R/G/B channels of a single (spatially-uniform) output instead
  of variance across pixels, and would have passed a shader that looked
  completely flat.
- **Always present at a shallow, muted, slowly-turning fold-depth**;
  while channel 10 ("pads"/DX) has a note held, a "reveal" sweeps
  through progressively deeper fold levels — real recursive detail
  phasing in — while rotation speeds up and color saturates/cycles
  faster, easing back to the shallow resting depth on release (same
  asymmetric ease-in/out as scene 5's synth2 background layer).
- Verified numerically: no NaN/Inf despite coordinates growing across
  8 fold iterations; tuned the crease-glow sharpness so bloomed-state
  screen coverage sits around 46% (vs. an initial version that covered
  90%+ and would have looked like a washed-out blob) while resting-state
  coverage is 0% above the same brightness threshold — a real, visible
  contrast between the two states. Also verified by temporarily running
  the app with this scene as the default and confirming the shader
  compiles and runs with no GL errors.
- **Found and fixed a real bug per feedback that the pattern kept
  spinning faster after every trigger, eventually unreasonably fast**:
  the shader computed rotation/hue angle as `elapsed_time * rate(bloom)`
  — since `rate` changes with bloom and `elapsed_time` only grows, every
  bloom transition caused an angle jump proportional to how long the
  scene had already been running. Verified numerically: a trigger 30
  minutes into a session spiked to an effective ~675 rad/s versus the
  intended ~0.15 rad/s max, and it got worse the longer the show ran —
  exactly the reported symptom. Fixed by accumulating an actual phase
  incrementally each frame (`phase += dt * rate`, computed in `update()`
  and passed in as `u_fractal_rot_phase`/`u_fractal_hue_phase`) instead
  of deriving it from elapsed time in the shader — the same pattern
  `camera.py` already uses correctly elsewhere in this project. Verified
  the fix with a simulated 40-minute session of continuous rapid on/off
  triggering: the per-frame phase step never exceeds its intended bound,
  regardless of how long the session has run.
- **Slowed down the rotation/hue-cycling speeds themselves** (max
  rotation ~0.07 rad/s, down from ~0.15; max hue-cycle rate similarly
  roughly halved) per feedback to emphasize the blooming/evolving
  quality over a fast spin.
- **Increased crease-line sharpness** per feedback (glow falloff
  steepened, plus an added contrast curve) — bloomed-state screen
  coverage above the same threshold dropped from ~46% to ~5%, i.e.
  noticeably thinner, crisper lines rather than a broad soft glow.
- Per feedback, stopped temporarily switching `config.py`'s
  `DEFAULT_SCENE` to visually smoke-test this scene — verification for
  this round is numerical (ported shader math) plus confirming the app
  still launches normally on the real default scene.
- **Made the rest state fully silent** per feedback that faint streaks
  were visible with no MIDI trigger at all: the background was adding
  `fractal * mix(0.14, 1.0, u_bloom)`, so even at bloom=0 there was a
  0.14 floor — that floor was exactly the reported streaks. Changed to
  `fractal * u_bloom` (no floor), so rest contributes exactly `0.0`.
- **Doubled the release decay time again** (0.6 -> 0.3, ~10s to fade
  below 5% now vs ~5s) per feedback that it was still fading too fast.
- **Found and fixed a second real bug this decay lengthening exposed**:
  per feedback that "faint lines reappear instead of fading to black,"
  the fractal's per-depth "reveal sweep" (deeper fold levels only
  contributing once bloom was high enough) meant shallow depths
  saturated to "fully revealed" at almost any bloom above ~0.125 and
  then only faded via the single outer bloom multiplier — so during
  release, the dense multi-depth bloom would collapse quickly down to
  one lonely shallow crease-line that then lingered, fading extremely
  slowly, for most of the (now much longer) decay tail. Fixed by
  dropping the per-depth reveal sweep entirely — every fold depth now
  fades in lockstep with the same `u_bloom` value. Verified numerically:
  simulated a full release and confirmed mean on-screen brightness
  decreases strictly monotonically from bloom=1 down to ~0, with no
  plateau or brightness increase anywhere in the curve (i.e. no
  resurging/lingering line).

## v37 — 2026-07-23 — Fixed what "stop the logo rotation" actually meant, one shared MIDI-activity signal for all scenes

- **Clarified what v36 got wrong**: "the logo's rotation" refers to the
  spin-loop video's own footage (it's a loop of the logo spinning), not
  the 3D plane transform scene 4 applies on top. v36 had frozen the
  entire yaw/pitch/roll tilt of scene 4's plane whenever MIDI went
  quiet — that tilt was never what was meant by "rotation," and per
  feedback should keep animating regardless of MIDI, exactly as it did
  before v33. Reverted scene 4's tilt to the pre-v33 always-on
  cam-time-driven sines; removed the now-unneeded `spin_phase`/
  `spinning`/`stop_at_phase` machinery entirely.
- **The video's own playback now starts static and only finishes its
  current loop before stopping** — it does not loop at all until MIDI
  is first received (previously it started looping immediately on
  launch regardless of MIDI, which was never right), and once playing,
  going quiet lets the CURRENT loop finish all the way to its last
  frame — same as always — then holds there until MIDI activity
  returns, at which point it resumes from the start. (Two earlier passes
  within this same round got this wrong: the first froze on whatever
  frame happened to be showing the instant MIDI went quiet, mid-loop;
  fixing that surfaced the startup issue.)
- **Moved "is MIDI recently active" out of individual scenes entirely,
  into one shared signal**: `MidiState.recently_active()`
  (`midi_input.py`), backed by a genuine app-wide clock advanced once
  per frame in `main.py`'s main loop — not any single scene's own
  elapsed time, which only ticks while that scene happens to be the one
  showing. Every scene/helper that needs this now reads the same
  signal instead of keeping its own `last_midi_time`/timeout pair, so
  new scenes get correct, consistent behavior automatically.
- **Scene 5 (`kaleidoscope_video.py`) now uses the shared
  `VideoTexture` helper** (`video_texture.py`) instead of its own
  duplicated OpenCV capture/frame-advance code — the same helper scenes
  1-4 already used. This means the finish-loop-then-hold behavior above
  now applies identically across all 5 scenes from one implementation,
  rather than being reimplemented per scene. Scene 5's own kaleidoscope
  rotation and its character-pop chase (which also now reads
  `recently_active()` directly) are otherwise unchanged.
- Verified numerically (using the real `MidiState.recently_active()`
  logic, not a stand-in): stays static on frame 0 through 3 simulated
  seconds of silence at launch, starts playing on the first MIDI
  message, finishes the current loop and freezes on exactly the last
  frame (not mid-loop) when MIDI goes quiet partway through, stays
  frozen for as long as MIDI stays quiet, and wraps to frame 0 and
  resumes the instant MIDI returns. Also verified by running the app
  with a real MIDI device connected — no errors across the refactor.

## v36 — 2026-07-22 — Reverted global freeze feature, replaced with per-scene MIDI-awareness

- **Removed the global "freeze until MIDI" feature entirely** (main.py's
  3-phase state machine, scene_manager's freeze parameter,
  `Scene.reset_to_static()` hook, and config's `WAIT_FOR_MIDI_BEFORE_
  ANIMATING`/`MIDI_ACTIVITY_TIMEOUT_SECONDS`/`MIDI_SETTLE_DURATION_
  SECONDS`) per feedback that it wasn't working well. Scenes 1-3 go
  back to always animating unconditionally, matching pre-v33 behavior.
- **Scene 4 — logo rotation now only advances while MIDI is being
  received from any of the 16 channels**, and does NOT freeze mid-tilt
  when it stops. Redesigned the rotation math: yaw/pitch/roll are now
  integer harmonics (1x/2x/3x) of one shared `spin_phase` instead of
  three independently-timed sine waves — integer harmonics of a common
  phase all share its period, so "one full rotation loop" is well-
  defined as exactly one turn of that phase, instead of being ambiguous
  across three differently-timed axes. When MIDI goes quiet, the
  current loop is allowed to complete (verified numerically: always
  lands back at exactly phase 0, the neutral/untilted pose, regardless
  of when in the loop MIDI stopped) before halting — worst-case wait is
  one full loop period (~7.9s), verified both for stopping early and
  almost immediately in a loop.
- **Scene 5 — the sequential character-pop chase now also only runs
  while channel-based MIDI is recently active.** Previously it was
  driven purely by MIDI Clock triplet ticks, but MIDI Clock is a
  separate real-time message stream from notes/CC — a sequencer can
  keep sending clock continuously with nothing else being played, which
  would have kept the chase animating with "no MIDI triggers" in the
  everyday sense. Now gated on the same "any of the 16 channels
  recently active" check used in scene 4.

## v35 — 2026-07-22 — Faster freeze reaction + settle-then-reset instead of freezing mid-motion

- **Freeze reaction sped up**: `MIDI_ACTIVITY_TIMEOUT_SECONDS` cut from
  5s to 0.3s, so pausing MIDI reads as an almost-immediate reaction.
- **Freezing mid-animation replaced with a proper settle-then-reset.**
  Previously, stopping MIDI would freeze every scene at whatever
  arbitrary instant the timeout elapsed — including the logo plane
  stuck at a random mid-tilt angle. Now there's a brief settle window
  (`MIDI_SETTLE_DURATION_SECONDS`, default 1.5s) where everything keeps
  animating normally so anything genuinely in motion (a burst
  mid-flight, a crossfade) finishes/settles on its own, and only after
  that does every scene reset ONCE to a defined neutral pose — the
  logo's rotation returns to its initial untilted orientation,
  particles/ripples/petals are cleared, trail buffers wiped — and holds
  there until MIDI resumes. New `Scene.reset_to_static()` hook
  (default no-op) implemented for all 5 scenes.
- Verified the full state machine numerically across multiple simulated
  on/off/on/off cycles: correct fast reaction, correct settle window,
  and the reset firing exactly once per quiet period (not repeatedly).
- Re-ran the render-before-update safety audit after these changes;
  still clean.

## v34 — 2026-07-22 — Static-until-MIDI reworked: repeatable toggle + scene-switching always works

- **Found that the previous version's fix had never actually been
  shipped.** The v33 zip that was sent only had the original one-way
  latch (freezes once at launch, never re-freezes) — a proper rework
  was already sitting in the project as uncommitted changes, never
  packaged. This version finishes and ships that work, verified before
  committing rather than assumed correct.
- **Freeze now toggles repeatedly, not a one-way switch.** Tracks time
  since the last channel-based MIDI message; if none arrives for
  `MIDI_ACTIVITY_TIMEOUT_SECONDS` (default 5s), the show freezes again,
  and un-freezes the moment MIDI resumes — verified numerically across
  a simulated multi-cycle on/off/on/off sequence.
- **Scene switching (keyboard or MIDI program-change) now always works
  immediately, even while frozen.** The crossfade timer advances
  unconditionally regardless of freeze state — only each scene's own
  animated content (particle motion, hue drift, etc.) freezes, never
  the ability to change which scene is showing.
- Re-ran the earlier static-analysis safety check (render() depending
  on update()-only attributes) against the current state to confirm
  nothing regressed.

## v33 — 2026-07-22 — Fractal removed from scene 4 entirely, static-until-MIDI feature added

- **Scene 4 — fractal background removed completely**, per feedback
  that the "black animation tied to channel 10" persisted despite
  several fix attempts (brightness floor, removing an artifact-
  introducing clear zone, a persistent baseline tint). Rather than
  patch the same system again, it's been pulled out entirely — the
  scene is now just the logo (3D plane + glitch) and the braid, as a
  clean foundation to rebuild the fractal from scratch on.
- **New feature: stay on a static frame until MIDI arrives.** By
  default, every scene (and the shared camera's own autonomous drift)
  now stays completely still from launch until MIDI is actually
  received from a connected device — a one-way latch, so ordinary gaps
  /silence between notes afterward don't re-freeze the show. Toggle via
  `WAIT_FOR_MIDI_BEFORE_ANIMATING` in `config.py`. While implementing
  this, a static-analysis pass caught a real crash risk: `render()` in
  three scenes (`feedback_trails`, `kaleidoscope_video`, `noise_field`)
  depended on attributes only ever set inside `update()` — since the
  new feature can call `render()` before `update()` has run even once,
  this would have crashed on the very first frame. Fixed by giving all
  of them safe defaults in `setup()`, verified with the same static
  analysis afterward.

## v32 — 2026-07-22 — Denser/stronger wind gust, real cause of "black animation" found

- **Scene 1 — wind gust made denser and more cohesive.** Ambient
  particle spawn rate now boosts substantially while wind is active
  (up to +220/sec on top of the base rate), so there's enough material
  in the air for the gust to read as a moving mass rather than a few
  sparse points getting nudged. Overall push strength increased (~1.7x)
  and per-particle jitter increased for more visible dispersion, while
  the shared directional term still keeps it reading as one gust.
- **Scene 4 — audited every use of channel 11 ("texture"/"sampler") in
  the project as requested**: it's referenced only in scenes 1 and 3
  (unrelated files) — not anywhere in scene 4's code. That check led to
  the actual mechanism, though: verified numerically that without any
  pad (channel 10) trigger ever firing, the fractal's bloom stays
  permanently at zero — the background is pure black (except the
  braid) the entire time, by construction. Channel 10 triggers are the
  ONLY thing that ever makes that permanently-black background move at
  all (via the traveling reveal wave), which is what was actually being
  seen as "a black animation tied to channel 10" — not something drawn
  by the trigger, but the only thing that ever animates an otherwise
  permanently-black background. Fixed with a persistent dim baseline
  tint so the background is never pure black in the first place,
  whether the bloom is dormant or actively cycling — verified the
  baseline is always above zero brightness.

## v31 — 2026-07-22 — Actually fixed the black blur (brightness floor), added wind effect to scene 1

- **Scene 4 — found the REAL cause of the black blur this time.**
  Verified numerically: a Julia set's escaped region (the vast majority
  of a typical view) evaluates to near-zero iteration count — measured
  at ~99% of the screen rendering as near-total black with the previous
  `f*f` brightness formula. With a pure-black base and the fractal as
  the only fill layer, that meant the "fractal background" was
  genuinely black across nearly the whole screen almost all the time —
  not a rare edge case, the norm. Fixed with a brightness floor
  (`mix(0.15, 1.0, f*f)`), verified numerically to bring the near-black
  fraction from 99% down to exactly 0%.
- **Scene 1 — new erratic "wind" effect, triggered by "synth2" (channel
  9).** While that channel has a note held (eased in/out), particles
  get pushed by a gusting force — direction and strength built from
  several non-harmonically-related sine waves (verified numerically to
  have multiple distinct frequency components, not simple periodic
  motion) plus per-particle random jitter, so particles scatter
  individually like debris in wind rather than drifting in unison.

## v30 — 2026-07-22 — Fixed real aspect-ratio bug (scene 1), removed black-disc artifact (scene 4)

- **Scene 1 — found the actual cause of "confined to a square region."**
  The vertex shader divides the final x position by `u_aspect` (to keep
  swirl/burst motion circular rather than elliptical) — but particle
  spawn positions were chosen in a plain -1..1 range without accounting
  for that division, so everything ended up confined to a square-
  looking region in the middle of any widescreen output, exactly as
  reported. Verified numerically: a spawn position that should reach
  the true screen edge was only reaching 53% of the way there. Fixed by
  scaling spawn x-ranges (both ambient particles and burst origins) by
  the actual aspect ratio, so they correctly reach ~95% of true screen
  width after the shader's correction — confirmed numerically.
- **Scene 4 — found and removed the actual cause of the "black blur."**
  The v28 fix added a static radial "clear zone" to keep the fractal
  from covering the logo at peak bloom — but since the background
  starts at pure black and the fractal is the only thing that can light
  that area up, suppressing it there created a PERMANENT black disc at
  screen center, in the fractal's own layer specifically (which is
  exactly what was reported: present in the background/fractal layer,
  not affecting the braid or logo, since those are computed/drawn
  separately). Removed the artificial zone entirely and replaced it
  with a simple, non-artifact-introducing intensity cap (0.65 -> 0.4)
  — verified numerically that the fractal's contribution is now uniform
  at every radius during full bloom, with no fixed dark patch anywhere.

## v29 — 2026-07-22 — Scene 4 removed, scene 5 stripped down to 3 elements, wider particle bursts

- **Scene 1 — burst origins widened toward the screen edges.** Bursts
  were clustering toward the center (origin ranges were only ±0.6/±0.8
  out of the full ±1.0 screen extent); widened to ±0.85-0.95 for a
  fuller "landscape" spread. Note: the continuous ambient background
  particles already used the full range — this only affects the
  discrete per-hit bursts.
- **Scene 4 ("logo_pulse") removed entirely.** Scenes renumbered to
  close the gap: what was scene 5 (`logo_video_pulse`) is now scene 4,
  and what was scene 6 (`kaleidoscope_video`) is now scene 5.
  Program-change/key mappings updated accordingly (0-4 instead of 0-5).
- **Scene 5 (formerly 6... see above, formerly "scene 5" in
  conversation, `logo_video_pulse.py`) isolated down to exactly 3
  elements**, per feedback that a persistent "triggered blur" issue
  remained even after the v28 fix: 1) the braid (thick pipe + thin
  flowing sliver), 2) the animated video plane with its glitch effect,
  and 3) the fractal background (pad-triggered, with the v28 center
  -clear fix retained). Removed: the noise-wash background layer, the
  background pixel-cloud particle burst, and the percussion-triggered
  per-character letter burst. The file is now fully self-contained
  (previously shared shader code with the now-deleted logo_pulse.py).
  This was as much a simplification as a targeted fix — with fewer
  simultaneous effects, whatever was still causing the residual blur
  no longer has as many places to hide.

## v28 — 2026-07-22 — Fixed fractal bloom obscuring the logo's center (scenes 4 & 5)

- **Found the actual cause of the reported "blur blocking the center"
  on channel 10.** At full bloom, the fractal's reveal mask saturates
  to 1.0 across the ENTIRE screen (it's based on `dist_sq >= 0`, which
  is always true) — meaning at peak bloom the fractal fully covers
  every part of the frame where the video's black background is
  transparent, i.e. everywhere except the mark's own white shapes,
  including right behind/around the logo. Channel 10 (pads) is what
  triggers scene 5's bloom, which is why it looked tied to that channel
  specifically; the same mechanism exists in scene 4 too (shared code),
  just less obviously since that bloom cycles automatically rather
  than from an obvious user action.
- **Fixed with a protected "clear zone"**: the fractal's contribution
  now ramps from zero at the exact center up to full strength by radius
  0.45, so the area immediately around the logo/video plane always
  stays clear regardless of bloom state, while the fractal still blooms
  fully everywhere further out. Verified numerically before/after.
- Note: scene 6 doesn't have this fractal-bloom mechanism at all (it's
  specific to scenes 4/5's shared background shader) — if scene 6 has a
  separate issue, it needs its own description since this fix doesn't
  touch it.

## v27 — 2026-07-22 — MIDI hot-plug, less vivid glitch, scene 3 ripple tuning + directional shading

- **MIDI hot-plug support.** Previously the MIDI port was only opened
  once at startup — plugging the SEQTRAK in after launch did nothing
  until restart. Now retries opening a port every 3 seconds in the
  background if none is connected (or one disconnects mid-show), via a
  cheap OS port-list check — negligible CPU cost since it's done every
  few seconds, not every frame.
- **Scenes 4 & 5 — glitch color toned down.** Reduced the chromatic
  (RGB) split amount by 40% (0.02 -> 0.012) for less vivid fringing
  during the glitch. (Scene 6 doesn't currently have a glitch effect —
  see note below.)
- **Scene 3 — fewer secondary ripples, slower expansion.** Retuned the
  ripple's wave frequency/decay (verified numerically) so it now shows
  about 2 visible bands (the primary impact + one clear secondary)
  instead of 4-5, and slowed the expansion speed noticeably (0.55 ->
  0.35).
- **Scene 3 — real directional shading added**, replacing the flat
  brightness bump: the ripple's gradient now builds a fake surface
  normal, lit by a fixed "parallel light source" direction, giving a
  genuine bright/dark sheen depending on slope direction (verified
  numerically: flat areas shade to exactly zero, and different slope
  directions produce both brighter and darker results, not just a
  uniform glow) — much closer to real light catching moving water.

## v26 — 2026-07-22 — Scene 3: ripples now refract the background instead of drawing a ring on top

- **Reworked ripples into a genuine refraction effect.** Instead of an
  additive colored ring drawn over the noise field, each ripple now
  computes a small displacement (a decaying oscillation trailing the
  leading edge — several bands, like real water) that WARPS the
  sampling coordinate used for the background/foreground noise layers
  themselves. The underlying pattern visibly distorts as a ripple
  passes through it, as if seen through a disturbed water surface with
  the noise field as the bottom surface beneath it, plus a subtle
  bright/dark sheen at the ripple's steepest point rather than a flat
  colored ring. Verified numerically: displacement peaks at a modest
  ~2% of screen half-width right at the leading edge, decaying over
  several oscillations behind it — a real warp, not an extreme one.

## v25 — 2026-07-22 — Scene 3: no more MIDI-linked pulsation, slower background, droplet-style ripples

- **Camera zoom removed entirely from scene 3's background/foreground
  layers** (was damped to 40% in v24, evidently still noticeable) —
  only rotate/pan remain, so the scene no longer visibly reacts to
  drum-hit "punches" or tempo-linked breathing at all.
- **Background layer flow speed halved** — the back-and-forth noise
  animation was moving too fast; time multipliers cut from
  0.06/0.05/0.02 to 0.03/0.025/0.01.
- **Ripples redesigned to look like an actual droplet impact**: a
  primary ring plus two smaller, fainter trailing rings behind it
  (rather than one plain ring), faster decay (max age cut from 4s to
  1.8s), and — the main mechanism now — a genuine distance-based
  falloff, so the ripple visibly dissipates once it's spread about
  half the screen's width, rather than fading on a fixed timer
  regardless of size. Verified numerically: the ripple is fully faded
  by ~0.9s via the distance falloff, well inside the old 4s duration.

## v24 — 2026-07-22 — Scene 3: smoother/subtler pulse, restored autonomous droplets

- **Smoothed several sources of "pulse" in scene 3**: the shared
  camera's zoom punch (from drum hits) is now damped to 40% of its
  previous influence here; the ripple ring itself is wider/softer and
  dimmer (0.7 -> 0.4 weight); the "drums" channel's brightness CC now
  swings a much narrower 0.75-1.25 range instead of 0.5-1.5.
- **Restored autonomous droplets/ripples** that pop in on their own at
  random screen positions on a random timer (independent of any MIDI
  input), reusing the same (now subtler) ripple rendering — ambient
  background life even with no input.

## v23 — 2026-07-22 — Thinner hollow logo outline

- **Reduced `OUTLINE_THICKNESS`** in `hollow_logo.py` by 30% (0.012 ->
  0.0084) per feedback that the outline on scenes 1-3 read too thick.

## v22 — 2026-07-22 — White hollow-outline logo added to scenes 1-3

- **Factored out shared `video_texture.py`** — the video-frame-streaming
  logic (open capture, decode/resize frames, advance at native
  playback speed) was duplicated across scenes 5 and 6; now shared by
  all five scenes that use the video.
- **New `hollow_logo.py`**: a centered, white OUTLINE-ONLY rendering of
  the spin-loop video logo (edges only, not filled) — samples a binary
  inside/outside mask at each pixel plus a ring of samples around it at
  a small radius; if any disagree with the center, that pixel is near a
  boundary and drawn white, everything else discarded. Verified
  numerically on an actual video frame that this produces a thin,
  non-degenerate boundary (not solid, not empty).
- **Added to scenes 1-3** (`particle_burst`, `feedback_trails`,
  `noise_field`) as a final overlay pass on top of each scene's own
  content — kept deliberately simple (flat, centered, no 3D tilt),
  unlike the full solid/3D treatment in scenes 4 and 5, so it doesn't
  compete with what's already a busy scene. Outline thickness and
  display size are tunable constants in `hollow_logo.py`.

## v21 — 2026-07-22 — Fixed a second, distinct bug: rotation made all characters vanish

- **The v20 fix introduced a real regression**: `theta_center` is
  computed in the ring's ROTATED frame (`u_rotation` already added into
  `angle` before this point), but was then used directly to place
  `slot_center_pos` in raw screen space — a mismatch that grows with
  `u_rotation` and, once the ring is spinning at all, pushes every
  character's valid sampling region outside [0,1] simultaneously. That
  produced exactly what was reported: characters completely gone.
  Traced to the exact line via direct numeric tracing (not guessing) —
  confirmed valid pixel coverage dropped to exactly zero the moment
  rotation was nonzero, at every tested resolution.
- **Fixed by converting back to the screen-space angle**
  (`theta_center - u_rotation`) before using it for position/
  decomposition. Verified numerically: valid coverage now stays
  constant (~12.9%) across rotation values from -10 to +6.5, and the
  v20 mirroring fix still holds correctly in combination with this
  (re-ran the upright/orientation check across 4 rotation values × 12
  angles = 48 cases, all passing).

## v20 — 2026-07-22 — Actually found and fixed the ring-text mirroring root cause

- **Root cause identified via rigorous numeric verification** (built a
  synthetic reference texture with known left/right and top/bottom
  markers, and tested exact coordinate math point-by-point — not just
  guessing signs): the ring-text mapping was taking (angle, radius)
  offsets straight to (glyph_uv.x, glyph_uv.y) without ever rotating
  into each slot's own tangent frame. That's only a valid approximation
  directly at the top of the ring, where the tangent happens to align
  with the screen's x-axis — at every other position around the ring
  it's an increasingly transposed mapping, and a coordinate transpose
  is mathematically a reflection. That's what was producing the
  mirroring, and why it persisted across multiple sign-flip attempts
  that were treating the symptom rather than this cause.
- **Fixed by properly decomposing each slot's local offset into genuine
  radial (outward) and tangential (reading-direction) components via
  an actual rotation matrix**, then mapping those (not raw angle/radius)
  to the glyph's texture coordinates. Verified correct at 24 angles
  spaced around the full circle, combined with multiple ring-rotation
  values, using exact deterministic point-sampling (not statistical
  correlation, which turned out to give misleading results for
  off-axis slots during earlier verification attempts).

## v19 — 2026-07-21 — Scene 7 removed

- **Removed `hollow_chars_pulse.py`** (scene 7) and its asset
  (`assets/hollow_chars.png`) entirely, along with all registrations
  in `config.py`, `scene_manager.py`, and `main.py`. Back to 6 scenes
  (program-change 0-5). The hollow-character identification from v18
  wasn't confirmed as correct before being asked to remove it.

## v18 — 2026-07-21 — New scene 7: hollow-character sequence from client artwork

- **New scene 7 — `hollow_chars_pulse.py`**, a structural copy of scene
  5 (same 3D camera-angle plane, background pixel-cloud, per-character
  particle burst, fractal/noise/braid background, glitch effect,
  pad-triggered fractal bloom) but displaying a STATIC image instead of
  the spin-loop video.
- **Source asset extracted from the client's `OCA_clientversion.ai`**
  (page 2): identified three large connected hollow-outline text
  shapes via connected-component analysis on the rendered page, cross-
  checked against the PDF's actual glyph position data (which showed
  fragmented per-letter runs consistent with "RHYTHM GATHERING" /
  "SOUND FLOWING" arranged in a circular layout) — isolated just those
  three shapes (excluding surrounding poster text like artist names,
  date, and venue info) into a clean transparent PNG
  (`assets/hollow_chars.png`).
- **Flagged for confirmation**: this identification was done
  programmatically (OCR did not work on the stylized connected font),
  so the extracted asset was shared for a visual sanity check before
  being wired in. The letter-burst positions in this new scene use a
  single placeholder center anchor rather than mapped per-character
  positions, since this artwork's internal layout hasn't been analyzed
  the way the OCA logo's three circles were.

## v18 — 2026-07-21 — Fixed horizontally mirrored ring characters

- **Scene 6 — fixed character mirroring.** The "unwrap text around a
  circle" technique mapped the angular sweep direction straight to the
  glyph texture's horizontal coordinate — this is equivalent to
  wrapping a printed strip around a cylinder with the printed side
  facing inward instead of outward, so every character came out
  mirrored left-right from the normal outside viewpoint. Fixed by
  flipping the within-slot horizontal sampling direction; which slot
  each character occupies (and the MIDI-clock pop-chase ordering) is
  unaffected — only the read direction within each character's own
  glyph changed.

## v17 — 2026-07-21 — Recovery: v12-v15 work restored after silent data loss

**What happened:** while implementing the v16 cursor fix, discovered
that all code changes from v12 through v15 had silently disappeared
from the project files — the container's working state had reverted to
v11 at some point without any visible error, and everything reported
as "done" in those four rounds never actually persisted. Git history
confirms this: v16 was built directly on top of the v11 commit.

**What this version restores** (rebuilt from scratch to match what
v12-v15 were meant to contain):
- MIDI Clock support in `midi_input.py` (`triplet_tick_pending`, fired
  every 8 pulses / a musical triplet)
- The dual randomized bloom-cell fractal system in `logo_pulse.py` and
  `logo_video_pulse.py` (varied origins, staggered/overlapping timing,
  area-uniform reveal metric)
- Full rebuild of `kaleidoscope_video.py`: the video-texture-aspect fix,
  the synth2-gated psychedelic asanoha background layer, and the
  always-lit glyph-based "温泉" ring with the MIDI-clock-driven pop
  chase
- Regenerated `assets/onsen1.png` / `assets/onsen2.png`

Re-verified numerically after rebuilding: the dual bloom cells still
never drop combined brightness below ~50-60%, and the fractal
detail-distribution and glyph-ring math all check out the same as
originally validated. Everything from v1-v11 and the v16 cursor fix
was confirmed still intact and unaffected throughout this.

## v16 — 2026-07-21 — Auto-hiding mouse cursor

- **Mouse cursor now auto-hides after ~2 seconds of no movement**
  (like a video player or any other fullscreen visual app), and
  reappears instantly the moment the mouse moves again. Configurable
  via `CURSOR_IDLE_HIDE_SECONDS` in `config.py` (set to `None` to
  disable and always show the cursor).

## v15 — 2026-07-21 — Fractal bloom variety + smoother blend, scene 6 always-lit characters

- **Scenes 4 & 5 — fractal bloom no longer always starts from the same
  spot.** Replaced the single sweep fixed to screen center with TWO
  overlapping "bloom cells," each with its own randomized origin.
  Scene 4 (auto mode): the two cells are staggered by half the cycle
  length, so one is always fading in while the other fades out —
  verified numerically that combined brightness never drops below 60%
  of full. Scene 5 (triggered mode): a new pad trigger shifts the
  current bloom into a "previous" cell that keeps fading out on its
  own while a fresh one starts fading in, so consecutive triggers
  blend into each other instead of cutting off abruptly.
- **Scenes 4 & 5 — smoother-feeling transition.** Switched the reveal
  comparison from raw distance to distance-squared, since screen area
  grows with r² and sweeping raw distance reveals area unevenly.
- **Scene 6 — characters are now always lit** at a legible baseline;
  the MIDI-clock chase is a brighten + slight outward glide layered on
  top, not a visibility toggle.

## v14 — 2026-07-21 — Fixed mirrored text, rebuilt as per-character MIDI-clock-driven pop chase

- **Found the actual cause of the mirrored/wrong-order characters** —
  the previous baked-ring + counter-flip approach was mathematically a
  no-op, not a fix; the real issue was in how per-character rotation
  was baked into the source image.
- **Redesigned around two individual glyph textures** ("温"/"泉",
  unrotated), each ring position its own controllable "slot," using the
  angular position as the glyph's own texture coordinate directly —
  correct orientation by construction.
- **Real MIDI Clock support added** (`midi_input.py`) — tracks the
  standard 24-pulses-per-quarter-note sync signal and fires a
  `triplet_tick_pending` event every 8 pulses. Requires clock/sync
  output enabled at the source (off by default on most gear/DAWs).
- **Sequential per-character pop, timed to that clock**, order
  configurable via `RING_POP_ORDER` (clockwise / counter-clockwise /
  random).

## v13 — 2026-07-21 — Scene 6 psychedelic background + text ring, scene 5 pad-triggered fractal

- **Scene 6 background layer made genuinely psychedelic and more
  Japanese**: a real hex-tessellated asanoha (hemp-leaf) lattice
  layered with the polar crossing-line/petal motif, and a hue that
  cycles with angle, radius, and time simultaneously.
- **Scene 6 — "温泉" text ring added**, pre-rendered via the Noto Sans
  CJK font for portability (not rendered live from a font at runtime).
- **Scene 5 — fractal bloom triggered by channel 10 ("pads")** instead
  of cycling automatically; scene 4 keeps its automatic cycle.

## v12 — 2026-07-21 — Scene 6: contrasting background layer + fixed elliptical logo mirroring

- **Fixed elliptical mirrored logo elements**: the kaleidoscope's fold
  was aspect-corrected for screen space, but the resulting sample
  position wasn't corrected for the video texture's OWN aspect ratio
  (the source is portrait) — added `u_video_aspect` to fix this
  separately.
- **New background kaleidoscope layer, gated by channel 9 ("synth2")**:
  a procedural asanoha-inspired motif fills the empty/black areas
  behind the foreground video-kaleidoscope while that channel has a
  note held, eased in/out.

## v11 — 2026-07-21 — Scenes 1/2 aspect-ratio fix, validated across all scenes, new kaleidoscope scene

- **Root cause of scenes 1 & 2 looking "sparse and close": found and
  fixed.** Both had an internal trail-accumulation buffer hardcoded to
  1280x720 (16:9), decoupled from the actual output resolution. That
  buffer gets blitted onto whatever the real output is via a simple
  full-screen stretch — if the real display isn't exactly 16:9 (very
  common; many laptop/external displays aren't), that stretch is
  non-uniform, squashing/compressing content along whichever axis is
  proportionally smaller. Fixed by computing that buffer's size from
  the ACTUAL output aspect ratio instead of a hardcoded one (new
  `compute_work_size()` in `utils.py`), and added a proper
  `Scene.resize()` hook (called by `SceneManager` whenever the window
  size changes) so this stays correct if the output size changes later,
  not just at startup.
- **Validated the same class of bug across scenes 3-5**
  (`noise_field`, `logo_pulse`, `logo_video_pulse`): confirmed none of
  them have a fixed-resolution internal buffer like scenes 1 & 2 did.
- **Found and fixed a related but distinct issue while checking:**
  circular patterns (the fractal bloom, noise ripples, feedback blobs,
  the particle field's swirl/burst motion) were all computed in raw
  normalized coordinates without correcting for the screen's actual
  aspect ratio, which stretches anything meant to look round into an
  ellipse on any non-square display. Added proper aspect correction to
  all five scenes.
- **New scene 6 — `kaleidoscope_video.py`.** The spin-loop video fed
  through a mirrored radial kaleidoscope (6-12 wedges, count nudged by
  the "keys" channel), dressed with a few Japanese-inspired elements: a
  seigaiha (layered wave/fan) pattern in indigo behind everything,
  drifting sakura (cherry blossom) petals spawned gently on drum hits,
  a thin gold mandala ring with periodic notches, and color grading
  pulled toward a traditional indigo/vermillion/gold palette rather
  than the source video's raw colors. Rotation speed follows the
  "bass" channel; program-change 5 switches to it.

## v10 — 2026-07-21 — Fractal bloom: smooth in/out, much longer cycle

- **Scenes 4 & 5 — fixed the actual cause of "fades suddenly."** The
  reveal wave used `fract(time)`, a sawtooth: it ramped up smoothly but
  then snapped back to empty instantly at the end of every cycle.
  Verified numerically (sampled the center-screen mask across a cycle):
  it held at full brightness then dropped to zero within ~0.25s out of
  a 6.3s cycle — a highly asymmetric slow-rise/instant-fall shape,
  which reads exactly as "fades suddenly." Replaced with a continuous
  triangle wave (smooth ramp up, smooth ramp down, no jump at the
  wrap point) and roughly tripled the period (was ~6.3s round trip,
  now ~20s), so there's real time for it to fully bloom before it
  recedes again, and the recede itself is now gradual.

## v9 — 2026-07-21 — Fractal is one connected entity (not tiled), real window-resize handling

- **Scenes 4 & 5 — removed the fractal tiling.** The v8 fix solved the
  "only visible near center" bug but did so by repeating small tiles,
  which read as copy-pasted thumbnails rather than one fractal. Now a
  single, non-tiled fractal at a scale verified numerically to spread
  real detail across edges, corners, and center (not just the middle) —
  so the edge-to-center reveal wave now blooms an actual connected
  shape inward, the way a real fractal zoom feels, rather than either
  a mostly-empty field (v7) or repeated copies (v8).
- **Fixed a real window-resize bug.** The app had no framebuffer-resize
  handling at all — if the window changed size any way other than our
  own startup fullscreen path (dragging an edge, the OS's native
  maximize/fullscreen button, an external display change), rendering
  stayed pinned to whatever size it started at, and the OS just
  stretched those old pixels to fit — which is exactly what "stuck at
  the original aspect ratio" looks like. Added a proper
  framebuffer-size callback that keeps the GL viewport and the scene
  manager's internal buffers (and anything reading `target.size`, like
  the logo scenes' aspect ratio) in sync with the actual current size
  at all times, plus a per-frame viewport safeguard against moderngl's
  own framebuffer-switching resetting it mid-frame.

## v8 — 2026-07-21 — Fixed the actual fractal bug, calmer pulse, visible glitch

- **Scenes 4 & 5 — found and fixed the real fractal bug.** Every prior
  "increase frequency" request was implemented by zooming the Julia
  set's input coordinates further OUT — but for this kind of fractal,
  points far from the origin escape almost immediately, so a larger
  multiplier actually SHRINKS the area with any visible detail down to
  a small patch near the screen center, with everywhere else reading
  as flat/empty. That's why it looked like it bloomed from the center
  regardless of the reveal-wave mask — there was nothing outside the
  center for the mask to reveal. Verified numerically: the old approach
  had visible detail in only 1 of 9 screen regions; the fix (tiling the
  fractal into a repeating grid instead of zooming out) spreads it
  evenly across all 9. Also sped up the reveal-wave cycle substantially
  (was ~20s, now ~6.3s).
- **Scenes 4 & 5 — logo pulse toned down.** The drum-punch contribution
  to the logo's yaw/roll tilt cut roughly 4-5x (was 0.55/0.35, now
  0.12/0.08) — should read as a small, discrete nudge per hit rather
  than a big lurch.
- **Scenes 4 & 5 — glitch made much more noticeable.** Switched from
  uniform tiny jitter on every band to a sparser-but-much-stronger tear
  (only some horizontal bands shift, and when they do it's a real
  displacement), tripled the chromatic split, and roughly tripled the
  duration (was 0.05-0.15s, now 0.18-0.4s) so there's actually time to
  perceive it.

## v7 — 2026-07-21 — Camera decoupled from background, edge-to-center fractal bloom, logo glitch, fullscreen native resolution

- **Scenes 4 & 5 — braid confirmed final, kept as-is** (thick pipe +
  thin flowing sliver from v6).
- **Scenes 4 & 5 — fractal/braid no longer pulsate with the logo.**
  Removed the background shader's camera coupling entirely (it was
  reading the shared camera's zoom/pan/rotation, including its
  drum-triggered "punch," at reduced strength) — now only the logo/video
  plane itself reacts to hits; the background is fully independent.
- **Scenes 4 & 5 — fractal frequency increased again**, and it now
  blooms in cyclically from the edges toward the center (a sweeping
  reveal wave) rather than being uniformly visible everywhere at once.
- **Scenes 4 & 5 — subtle glitch effect added to the logo/video plane.**
  Rare (roughly every 10-25s), brief (0.05-0.15s), combining a small
  horizontal slice-tear with a slight chromatic (RGB) channel split —
  kept deliberately minor so it reads as a quick flicker, not a
  dramatic effect.
- **Fullscreen now auto-fits the display's native resolution/refresh
  rate** (including 4K, if that's what the screen/projector reports)
  instead of a hardcoded size.
- **(b) Percussion-triggered burst:** re-audited the full trigger →
  spawn → render path again and it continues to check out logically;
  still unresolved without the `MIDI_DEBUG` output requested in v6 to
  confirm whether channels 4-7 are actually arriving as separate
  channels from the SEQTRAK/Ableton setup.

## v6 — 2026-07-21 — Braid restored + thin flowing sliver, MIDI debug tool

- **Scenes 4 & 5 — braid separated into two distinct elements.** The
  previous version had conflated "make the streak thin/erratic" into
  the braid's own shape, making the whole pipe thin. Restored: the
  braid "pipe" itself is back to its original thickness and smooth
  sine-only path; a NEW, separate thin sliver of contrasting color now
  wanders erratically and travels along the strand, flowing inside the
  pipe's width — like colored light moving through a transparent tube,
  rather than the tube itself being thin.
- **MIDI debug tool.** Added `MIDI_DEBUG` in `config.py` — when set to
  `True`, every incoming MIDI message is printed to the terminal
  (type, channel as 1-16, note/CC value), to help confirm whether
  gear/DAW routing is actually sending distinct channels per part.
  Added after repeated reports that the percussion-triggered particle
  burst "isn't working" despite the trigger logic checking out
  end-to-end in code review — this is the fastest way to see what's
  actually arriving at the channel level.

## v5 — 2026-07-21 — Split drums/percussion mapping, letter effect reworked as gentle particles

- **New MIDI mapping split.** "Mapping 1" (the `drums` role) now covers
  only channels 1-3 (kick, snare, snare2/clap) — channels 4-7 (hi-hat
  1/2, perc 1/2) were moved out into a brand new `percussion` mapping,
  kept completely separate. This changes what channels 4-7 drive
  everywhere `drums` was previously read (camera tempo/punch detection,
  scene 2's pulse, scene 3's brightness CC) — they no longer contribute
  to those, only channels 1-3 do now.
- **Scenes 4 & 5 — glow pulse concept fully replaced.** The analytic
  shader-based glow (from v3/v4) is gone entirely — removed the
  `u_pulse_*` uniforms and shader code. In its place: a real, gentle
  burst of particles from each character (few particles, slow speed,
  muted saturation), using the same reusable `ParticleField` as the
  background pixel-cloud. Crucially, this new burst is triggered by the
  **new `percussion` mapping**, not `drums` — so hi-hats/perc now
  animate the characters, while kick/snare/snare2 still drive the
  background pixel-cloud and camera punch as before.

## v4 — 2026-07-21 — Dimmer/diffuse/noisy pulse, thinner erratic braid strands

- **Scenes 4 & 5 — glow pulse made dimmer, more diffuse, and grainy.**
  The band is now much wider/softer (lower falloff exponent) instead of
  a crisp ring, a noise-based "grain" term breaks it up into sparse,
  dusty flecks rather than a smooth gradient, and overall intensity was
  cut significantly (roughly 2.3x dimmer).
- **Scenes 4 & 5 — braid strands are now thin, with an erratic
  trajectory.** Falloff exponent raised substantially (much thinner
  lines), and a two-octave noise wobble was added on top of the
  existing sine curves so the path drifts irregularly instead of
  following a perfectly smooth periodic wave.

## v3 — 2026-07-21 — Gentler pulse, bigger points, 3-axis pop origins, denser fractal, braid flicker

- **Scenes 4 & 5 — pulsation replaced with a gentle glow.** The
  particle-ring burst (from v2) was still too intense/explosive. It's
  now a soft, analytic glow pulse computed directly in the background
  shader — a gently expanding, soft-edged ring of light with a quick
  fade-in and slow fade-out, no discrete points at all. Positioned the
  same way as before (projected through the logo's 3D transform so it
  tracks each character correctly).
- **Scene 1 — bigger points.** Base point size roughly doubled so the
  field reads as close/substantial rather than distant and small.
- **Scene 1 — pop origins randomized across X, Y, *and* Z.** Previously
  Y was always pinned to 0 for every burst (only X and, per-particle,
  Z varied) — now each pop's starting point is randomized across all
  three axes, so successive pops visibly start from different places
  in the field rather than always along the same horizontal line.
- **Scenes 4 & 5 — fractal frequency increased further** (zoomed out
  more to reveal more repeating detail), still with the morph/bloom
  speed unchanged.
- **Scenes 4 & 5 — braid now flickers** in a contrasting color: small
  stretches of the strands randomly brighten a few times a second, like
  light catching a moving thread, layered on top of the existing slow
  weave.

## v2 — 2026-07-21 — Bug fixes + more aggressive logo camera

- **Scene 2 — fixed a real white-out bug.** The previous version's
  fix (frame-rate-independent decay) exposed a second bug: the shader
  was accumulating `prev*decay + new_glow` every frame, which is
  unbounded — once decay correctly became a slow real-time value, more
  brightness was added each frame than could ever decay away, so the
  whole buffer rocketed to solid white within a second or two. Fixed by
  switching to a bounded decay-weighted blend toward a target color
  (`mix(target, prev, decay)`) instead of open-ended addition — this
  can never blow out, while still producing the same slow trailing
  effect.
- **Scenes 4 & 5 — letter bursts are now a coherent expanding RING**
  instead of a scattered directional burst (same speed/life for every
  particle in the ring, so they move together as one pulse rather than
  spreading into a cloud) — reads much more clearly as a "pulsation."
- **Scenes 4 & 5 — fractal made more present.** Increased spatial
  frequency (zoomed out to reveal more detail) and raised opacity;
  left the `c`-vector rotation speed (the "bloom"/morph speed)
  unchanged, as requested.
- **Scenes 4 & 5 — more aggressive 3D camera angles.** Yaw and pitch
  amplitudes roughly doubled, and a Z-axis roll was added (there was no
  roll at all before) — verified numerically that even at maximum
  combined rotation the plane stays safely within the camera's near/far
  planes (no clipping).

## v1 — 2026-07-21 — Baseline snapshot

This is the first tagged version, taken after the first several rounds
of building/tuning the rig, so it's a baseline rather than a "v0"
starting point. It includes everything built up to this point:

- 5 scenes: `particle_burst`, `feedback_trails`, `noise_field`,
  `logo_pulse`, `logo_video_pulse`
- Per-instrument-channel MIDI routing (kick/snare/hihat/perc/bass/synth2
  /pads/sampler), matching the SEQTRAK's fixed channel layout
- Shared virtual camera (`camera.py`) with automated pan/zoom/rotation,
  tempo-synced breathing, and drum-trigger punches
- Scene 1: dense continuous particle field, per-channel color, erratic
  jitter/flicker during fade-out
- Scene 2: frame-rate-independent decay (half-life in seconds) with a
  soft multi-tap blur for genuinely smooth, slow blending
- Scenes 4 & 5: logo/video rendered as a real 3D-projected plane
  (genuine camera-angle perspective), a fractal + noise + braid
  background, a background pixel-cloud burst, and per-character letter
  bursts (one distinct color per character, edge-fading, tracking the
  plane's current on-screen position) on every drum trigger
