# block_onscreen_drawing

**Block ID:** `block-onscreen-draw`

## Purpose

Manages GPU-accelerated onscreen drawing in Blender viewports. Provides a pull-based
architecture: downstream blocks declare their shaders via `hook_get_shader_declarations`, and
`Wrapper_Shader_Manager` owns the full lifecycle — grouping shaders by draw location,
registering one Blender draw handler per `(space, region, phase)` group, creating
`Shader_Instance` objects, and persisting per-shader `is_enabled` state in a Blender
`CollectionProperty` UIList so preferences survive undo/redo.

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers, hooks |
| `block-timers` | Tick cadence for the animation sub-feature (`animations/`) |

> **Registration order:** `block_timers` must appear **before** `block_onscreen_drawing`
> in `addon_config/active_blocks.py`, since dependencies register first.

## Architecture Summary

Drawing is gated by the `enable_drawing` scene property. Any change to the desired shader set
(enabling drawing, a downstream block calling `repoll()`, toggling viewport debugging, undo/redo)
triggers a **reconcile**, not a destroy-and-recreate:

1. `hook_get_shader_declarations` is broadcast — each subscribed block returns a list of its
   `Shader_Declaration` objects. This is the **authoritative** "what should exist" set.
2. Definitions are validated and grouped by `(space, region, phase)`.
3. `_rebuild_all_shaders()` **reuses** any existing live `Shader_Instance` whose class, shader
   type, builtin name and draw location still match — preserving its GPU batch, cached uniforms,
   `is_enabled` state and animations. Only *new* uids create instances; only *removed* uids are
   destroyed. All draw handlers are re-registered (one per `(space, region, phase)` group).
4. `_update_BL_with_mirrored_RTC_data()` pushes the live RTC set to the BL `shader_mirror`
   collection (uid + display fields only).
5. `hook_before_first_draw` is broadcast — subscribers push geometry via
   `Wrapper_Shader_Manager.get_shader(uid)`.
6. Declared animations (`Shader_Declaration.animations`) are re-applied idempotently.

Setting `enable_drawing` `False` calls `_clear_all_shaders()`, which tears down all draw handlers,
discards all `Shader_Instance` objects, and clears the BL `shader_mirror`.

### Undo / Redo — smart structural comparison

Undo/redo is handled automatically by the core runtime cache mirroring system, which delegates to
`Wrapper_Shader_Manager._update_RTC_with_mirrored_BL_data(event)`.

The BL `shader_mirror` holds only a `shader_uid` key plus display-only fields — **`is_enabled` is
RTC-only** — so the diff planner can only ever emit `Create` / `Remove` / `Move` / `Noop`
(never `Edit`). BL is purely a change-detector; the hooks are the source of truth for the desired
set:

1. If `enable_drawing` is `False` → `_clear_all_shaders()` and return.
2. `plan_dataclasses_to_match_collectionprop` diffs the BL mirror against the RTC list.
3. If any `Create` / `Remove` action exists (structure changed) → re-poll the hooks and reconcile
   via `_rebuild_all_shaders()`. Surviving shaders (and their `is_enabled` + animation state) are
   reused, not rebuilt.
4. If only `Move` actions exist (reorder) → the RTC list is reordered in place. No GPU work.

Because reused instances survive, imperatively-added animations (`shader.set_animation(...)`) and
per-shader visibility now carry across undo/redo and repolls instead of being discarded.

## Data Architecture

### Blender Data

| Property path | Type | Purpose |
|---|---|---|
| `scene.dgblocks_onscreen_drawing_props.enable_drawing` | `BoolProperty` | Master on/off toggle; drives rebuild/clear |
| `scene.dgblocks_onscreen_drawing_props.shader_mirror` | `CollectionProperty[DGBLOCKS_PG_Shader_Mirror_Row]` | Per-shader BL persistence |
| `scene.dgblocks_onscreen_drawing_props.shader_mirror_index` | `IntProperty` | Active UIList selection index |

**`DGBLOCKS_PG_Shader_Mirror_Row` fields:**

| Field | Type | Notes |
|---|---|---|
| `shader_uid` | `StringProperty` | Key — matches `Shader_Instance.shader_uid` |
| `draw_space` | `StringProperty` | Display only (`Draw_Space_Types.name`) |
| `draw_region` | `StringProperty` | Display only |
| `draw_phase` | `StringProperty` | Display only |

> **`is_enabled` is not a BL field.** It lives only on the RTC `Shader_Instance` and is toggled
> through `DGBLOCKS_OT_Toggle_Shader` (single prop: `shader_uid`), which carries `bl_options =
> {"INTERNAL"}` and no `UNDO` — so toggling visibility never adds an undo step. The Shaders UIList
> renders this operator (eye icon reflecting live RTC state) plus the shader's current batch count.
> The BL mirror exists purely to back the UIList and to detect structural changes on undo/redo;
> it never drives RTC.

### Runtime Cache

| RTC Key | Type | Purpose |
|---|---|---|
| `SHADERS` | `dict[str, Shader_Instance]` | All live shader instances, keyed by `shader_uid` |
| `DRAW_PHASES` | `dict[tuple, Drawhandler_Instance]` | Live draw handler instances, keyed by `(space, region, phase)` |

## Hook Sources

| Member | Direction | Kwargs | Purpose |
|---|---|---|---|
| `hook_get_shader_declarations` | block_onscreen_drawing → subscribers | `{}` | Collect `Shader_Declaration` objects; subscribers return a list of definitions |
| `hook_before_first_draw` | block_onscreen_drawing → subscribers | `{}` | Push initial geometry via `get_shader(uid)` after all instances are live |

## Hook Subscriptions (other blocks)

| Member | Source block | Purpose |
|---|---|---|
| `hook_get_timer_definitions` | `block-timers` | Returns one `Timer_Definition` per unique animation framerate |

## Hook Subscriptions (core hooks)

*(No direct core hook subscriptions in `__init__.py`. Undo/redo is handled via `Abstract_BL_RTC_List_Syncronizer` data mirror sync in `Wrapper_Shader_Manager._update_RTC_with_mirrored_BL_data`)*

## Public API — `Wrapper_Shader_Manager`

### `repoll(event)`

Re-polls all downstream blocks for their `Shader_Declaration`s and **reconciles** the live shader
set against them, reusing existing `Shader_Instance` objects where possible. Safe to call whether
or not drawing is already enabled — if drawing is off it enables it (which reconciles); if drawing
is already on it reconciles directly. (The old behaviour of merely setting `enable_drawing = True`
was a no-op when it was already `True`, so a downstream declaration change was silently ignored.)

### `disable_shaders()`

Sets `enable_drawing` to `False`, which tears down all live Blender draw handlers, discards all `Shader_Instance` objects, and clears the BL `shader_mirror`.

### `get_shader(uid: str) -> Shader_Instance | None`

Returns the live `Shader_Instance` for a given `uid`, or `None`. Intended for use inside
`hook_before_first_draw` subscribers to push initial geometry.

```python
def hook_before_first_draw():
    shader = Wrapper_Shader_Manager.get_shader("MY_SHADER")
    if shader:
        shader.set_points([(0, 0, 0), (1, 0, 0)])
        shader.set_uniform("color", (1.0, 0.0, 0.0, 1.0))
```

## Public API — `Shader_Declaration`

Declarative descriptor. One per logical shader. Supplied by downstream blocks inside
`hook_get_shader_declarations`.

```python
Shader_Declaration(
    uid="MY_LINES",                              # unique across all blocks
    shader_type=Shader_Types.LINES,
    space=Draw_Space_Types.VIEW_3D,
    region=Draw_Region_Type.WINDOW,
    phase=Draw_Phase_type.POST_VIEW,
    builtin_shader_name=Builtin_Shader_Names.POLYLINE_UNIFORM_COLOR,
)
```

For custom shaders, set `custom_shader_class` to a `Shader_Instance` subclass and pass
constructor kwargs via `custom_shader_kwargs`:

```python
Shader_Declaration(
    uid="MY_BILLBOARD",
    shader_type=Shader_Types.TRIS,
    space=Draw_Space_Types.VIEW_3D,
    region=Draw_Region_Type.WINDOW,
    phase=Draw_Phase_type.POST_VIEW,
    custom_shader_class=My_Billboard_Shader,
    custom_shader_kwargs={"image_name": "my_image"},
)
```

Optionally attach animations that should be re-created on every rebuild:

```python
Shader_Declaration(
    shader_uid="MY_LINES",
    ...,
    animations=[
        Animation_Declaration(
            animation_uid="ambient_pulse",
            data_type=ANIM_DATA_TYPE_UNIFORMS,
            data_name="alpha",
            start_state=0.2,
            end_state=1.0,
            duration=0.6,
            loop_mode=ANIM_LOOP_PING_PONG,
            loop_count=0,
        ),
    ],
)
```

**Note:** `group_id` has been removed. Shaders are automatically batched into one draw handler
per unique `(space, region, phase)` combination — no explicit grouping needed.

## Public API — `Shader_Instance`

A `@dataclass` representing a single GPU shader pipeline. Lifecycle fully managed by
`Wrapper_Shader_Manager`.

### Key Fields

| Field | Type | Description |
|---|---|---|
| `shader_uid` | `str` | Unique identifier |
| `shader_type` | `str` | `'POINTS'`, `'LINES'`, or `'TRIS'` |
| `is_enabled` | `bool` | Toggle draw on/off; synced from BL mirror on undo/redo |
| `shader_error_str` | `str \| None` | Last draw exception message; `None` = healthy |
| `draw_space` | `Draw_Space_Types` | Draw location space (set at creation) |
| `draw_region` | `Draw_Region_Type` | Draw location region (set at creation) |
| `draw_phase` | `Draw_Phase_type` | Draw location phase (set at creation) |
| `_is_builtin_shader` | `bool` (property) | Computed: `builtin_shader_name is not None` |

### Key Methods

| Method | Triggers batch rebuild? | Purpose |
|---|---|---|
| `set_indices(value)` | Yes | Set index array (TRIS) |
| `set_points(value)` | Yes | Set vertex positions |
| `set_colors(value)` | Yes | Set per-vertex colors (SMOOTH_COLOR shaders) |
| `set_uniform(name, value)` | No | Set a shader uniform (auto-maps float/bool/int/sampler) |

### Custom shader subclasses

Inherit `Shader_Instance` and override `_shader_init()` to create the GPU shader, and
`_shader_draw()` to set frame-varying uniforms before calling `super()._shader_draw()`.
Builtin shaders call `_builtin_shader_before_draw()` / `_builtin_shader_after_draw()` around
the draw; these can be monkeypatched via `Shader_Declaration.builtin_shader_before_draw`.

## Downstream Block Integration Example

```python
# my_block/__init__.py

from ...native_blocks.block_onscreen_drawing.feature_shader_manager import Wrapper_Shader_Manager
from .constants import MY_SHADER_DEFS

def hook_get_shader_declarations():
    return MY_SHADER_DEFS

def hook_before_first_draw():
    shader = Wrapper_Shader_Manager.get_shader("MY_LINES")
    if shader:
        shader.set_points([(0, 0, 0), (1, 1, 0)])
        shader.set_uniform("color", (1.0, 1.0, 0.0, 1.0))
```

```python
# my_block/constants.py

SHADER_DEFS = [
    Shader_Declaration(
        uid="MY_LINES",
        shader_type=Shader_Types.LINES,
        space=Draw_Space_Types.VIEW_3D,
        region=Draw_Region_Type.WINDOW,
        phase=Draw_Phase_type.POST_VIEW,
        builtin_shader_name=Builtin_Shader_Names.POLYLINE_UNIFORM_COLOR,
    ),
]
```

The `enable_drawing` toggle in the panel (owned by `block_onscreen_drawing`) drives everything.

## Validation

`_validate_shader_definitions()` in `helpers.py` runs all checks before any Blender state is
mutated. Checks:

1. Duplicate `uid` detection across all contributing blocks
2. `(space, region, phase)` allowlist enforcement (see `BL_gpu_data_structures._VALID_SPACE_REGION_PHASE_COMBOS`)
3. Exactly one of `builtin_shader_name` / `custom_shader_class` per definition
4. Builtin shader name compatibility with the declared `shader_type`

## Viewport Region Debugging

`scene.dgblocks_onscreen_drawing_props.debug_props.show_region_boundaries` (a checkbox in the
panel's **Viewport Region Debugging** sub-subpanel, active only while `enable_drawing` is on)
draws a thin border around **every region of every area of every open window** — useful for
seeing where each `(space, region)` actually lives. It governs **only** the border shaders — it
no longer gates the example demo shaders (those are controlled by their own `show_shader` eyes).

- **Per-region-type checkboxes:** a `grid_flow` of checkboxes (`region_boundary_toggles`, one
  `BoolProperty` per drawable `Draw_Region_Type` — WINDOW, HEADER, TOOL_HEADER, UI, TOOLS, …)
  lets you disable individual region types for all areas at once. Unchecking one omits its
  border declaration on the next repoll.
- **Reliable enable/disable:** `enable_drawing` now carries an `update` callback
  (`_cb_enable_drawing_changed`), and every debug/demo/region property routes structural changes
  through `_rebuild_all_shaders`, so toggles reconcile reliably (fixing the earlier "sometimes
  nothing happens on disable").

- The `hook_get_shader_declarations` subscriber walks `bpy.context.window_manager.windows` live,
  rather than hardcoding a list, so it only ever declares real, currently-valid `(space, region)`
  combinations. This transparently covers all editor types across all windows and picks up regions
  such as `TOOL_HEADER` automatically. One `Shader_Declaration` is emitted per unique
  `(space_type, region_type)`; Blender's single draw handler per space type then draws that border
  in every matching area/window.
- **Hover highlight (optional):** each border's `builtin_shader_before_draw` reads the optional
  foreign RTC member `USER_INPUT_CAPTURE` (owned by `block_modal_events`, which is **not** a
  dependency) via `get_cache("USER_INPUT_CAPTURE")` — returning `None` gracefully when that block is
  absent. If the captured mouse position (`mouse_x`/`mouse_y`, window-space) has both fields `> 0`,
  matches the current window (`window_id`), and falls inside the region being drawn, the border is
  drawn green instead of magenta.

> **Limitation:** `USER_INPUT_CAPTURE` is only populated while `block_modal_events`' modal router is
> running (it is cleared to `None` when idle), so the hover color only reacts while that block's
> modal is active. Reading the key cross-block is otherwise safe and adds no dependency.


## Built-in Example Shaders

The block's own panel ships three demo shaders under a collapsible **"Shader Examples"**
subpanel (drawn with `ui_draw_subpanel`). **Each demo now has its own nested sub-subpanel**
whose header carries an **eye icon** bound to that demo's `show_shader` property (in
`demo_settings`). Toggling the eye triggers a repoll, and a hidden demo is excluded from — and
implicitly removed from — the shader list. They are self-subscribed via this block's own
`hook_get_shader_declarations` / `hook_before_first_draw`, and controlled by
`scene.dgblocks_onscreen_drawing_props.debug_props` (per-shader static params) plus
`scene.dgblocks_onscreen_drawing_props.demo_settings` (unified per-demo options — see below).
Each is a **custom `Shader_Instance` subclass** living in `builtin_shaders_and_effects/`; the
pure GPU/shader files are kept fully independent of the controlling logic — the panel and hooks
only call small public setters. Static shader props are arranged in **width-sensitive
`grid_flow` grids** rather than plain columns.

Every example follows the same "declare-when-visible" contract: while `enable_drawing` is on,
any property edit triggers a reconcile, which re-fires both hooks — so `hook_before_first_draw`
re-pushes geometry on every change (the billboard example uses this to **re-randomize** on each
edit).

### Unified per-demo settings (`demo_settings`)

New PropertyGroups and the demo-animation logic live in the dedicated module
`demo_shader_settings.py`. `scene.dgblocks_onscreen_drawing_props.demo_settings` is a
`CollectionProperty[DGBLOCKS_PG_Demo_Shader_Common]` with one row per demo (keyed by `demo_id`,
seeded idempotently by `ensure_demo_rows()`). Each row holds options common to **all** shaders:

| Field | Purpose |
|---|---|
| `show_shader` | Eye toggle — whether the demo shader exists at all (drives repoll) |
| `is_animating` | Runs an infinite-loop demo animation (RTC-only; never writes BL values) |
| `animation_fps` | Ticks/sec for the demo animation, **capped at 60** |
| `scale` | Uniform scale hook available to all demos |
| `unique_attributes` | Nested `CollectionProperty` of shader-unique knobs (e.g. dashed `phase`, cluster `count`) |

**Demo animations (task 3/4):** each animatable demo shows an **Animate** toggle (operator
`DGBLOCKS_OT_Toggle_Demo_Animation`, `INTERNAL`, no UNDO) and — while running — an **FPS
slider**. Turning it on applies an infinite (`loop_count=0`) `set_animation()` mix per demo:
the dashed shader lerps its `_phase`, `_color` and `_points`; the billboard lerps `_colors`,
`_points` and `_sizes`. While a demo is animating, its other props render **read-only**; the
animation drives only RTC shader state, so the Blender property values stay static. The old
"Sample Animations" button has been removed.

| Example | Property | Behaviour |
|---|---|---|
| **2D image billboard** | `show_img_2Dbillboard` (Image), `billboard_count`, `billboard_default_size`, `billboard_size_spread`, `billboard_location_spread`, `billboard_color_spread` + `is_animating` | Declared **only when its eye is on AND an image is set**. Draws `count` camera-facing quads with random location, size, and color. Its `shader_uid` embeds the image name so swapping images forces a fresh GPU texture. Animatable. |
| **Dashed polyline** | `show_linedash`, `linedash_thickness`, `linedash_dash_width`, `linedash_dash_ratio`, `linedash_color`, `linedash_color2` + unique attrs `phase` (0–1, hard-capped) and cluster `count` + `is_animating` | A `Polyline_Dash_Shader` port of the legacy dashed-line shader with true Metal-safe thickness. `count` draws that many extra **disjointed, radially-symmetric ring clusters** stacked in Z above the base square — proving the polyline shader handles disjointed line clusters in one batch. Animatable. |
| **Text boxes** | `show_textbox_count`, `textbox_spawn_point`, `textbox_x_offset`, `textbox_y_offset` | Draws N BLF text boxes via `draw_text_box()`, wrapped in `Textbox_Demo_Shader`. `spawn_point` is a radio (TOP_LEFT / TOP_RIGHT / BOTTOM_LEFT / BOTTOM_RIGHT / **MOUSE**). `textbox_x_offset` / `textbox_y_offset` shift the whole group of boxes (in px) away from the chosen anchor. The **At Mouse** option positions boxes at the captured mouse; it requires a live `block_modal_event` instance (`USER_INPUT_CAPTURE`), otherwise the panel shows *"An active block_modal_event instance is required for mouse/key capture"*. |
| **Stripe holdout** | `show_stripes`, `stripe_angle`, `stripe_width`, `stripe_color1`, `stripe_color2` + unique `phase` | Draws a unit cube of TRIs at world-space points but computes an **alternating-stripe pattern purely from window-space pixels** (`gl_FragCoord.xy`) in the fragment shader. The 2D pattern is therefore screen-locked — orbiting the camera makes the static stripes *slide across* the geometry, the intended "glitchy" holdout effect. `stripe_angle` (degrees), `stripe_width` (shared band width in px), the two stripe colors, and a `phase` slider (band scroll offset) are all controllable from the panel. Animatable: its infinite-loop animation scrolls **only** the `phase`, making the banded holdout crawl along the stripe direction. |

### `Polyline_Dash_Shader` — Metal-safe line thickness

The legacy shader (`legacy_custom_shader_linedash.py`, kept read-only for reference) drew
`GL_LINES` and relied on `gpu.state.line_width_set()`, which Metal ignores — lines always
rendered 1px on Mac. Blender's own `POLYLINE_*` builtins avoid this by expanding each segment
into a screen-space quad and offsetting corners perpendicular to the segment by half the
thickness; thickness then becomes real geometry. `Polyline_Dash_Shader` does exactly that and
additionally carries the legacy dash fragment logic (`dash_width` / `udash_factor` / two colors).
Input is a flat list of segment endpoint pairs via `set_polyline([A, B, B, C, ...])`.

## Animations

Lives in `animations/`. Lerps any Python-readable attribute on a `Shader_Instance`
(batch arrays **or** cached uniform values) over time, driven by `block_timers`.

**Animations are owned by their shader.** They live in `Shader_Instance._animations`
(`uid -> Animation_Instance`), not in a separate RTC list, which means:

- The API is on the shader: `shader.set_animation(decl)`, not a manager class.
- `animation_uid` is scoped **per shader** — two shaders may both own a `"pulse"`.
- An animation is destroyed with its shader. No orphan cleanup, no stale-uid lookups.

### Declared vs imperative

|  | Declared (`Shader_Declaration.animations`) | Imperative (`shader.set_animation()`) |
|---|---|---|
| Survives a shader rebuild (undo/redo, debug toggle) | **Yes** — re-applied every rebuild | No — dies with the instance |
| Best for | Permanent/ambient effects | Effects driven by transient state (selection, hover) |

Declared animations are applied **after** `hook_before_first_draw`, so a declaration
using `start_state=None` auto-captures real geometry rather than `None`.

### Shader API (from `Animatable_Mixin`)

| Method | Purpose |
|---|---|
| `set_animation(decl)` | **Upsert.** Creates, or updates in place *preserving phase* |
| `add_animation(decl)` | Create only; warns if the uid is already active |
| `cancel_animation(uid, revert=True)` | Remove; the only way to stop an infinite loop |
| `cancel_all_animations(revert=True)` | Remove every animation on this shader |
| `get_animation(uid)` / `has_animation(uid)` | Lookup |
| `get_active_animations()` | Snapshot list |
| `pause_animation(uid)` | Toggle `is_paused` |
| `update_animation(uid, **fields)` | Patch fields, preserving phase |

Phase preservation is what makes `set_animation()` the call to reach for: swapping in
new data mid-cycle produces no visual seam, because `_elapsed_time` survives.

```python
shader = Wrapper_Shader_Manager.get_shader("SELECTION_SHADER")
shader.set_animation(Animation_Declaration(
    animation_uid = "SELECTION_PULSE",
    data_type     = ANIM_DATA_TYPE_BATCH,   # or ANIM_DATA_TYPE_UNIFORMS
    data_name     = "_colors",              # or a uniform name, e.g. "alpha"
    start_state   = colors_bright,          # None -> auto-capture from the shader
    end_state     = colors_dim,
    duration      = 1.2,
    framerate     = 30,
    loop_mode     = ANIM_LOOP_PING_PONG,    # ONCE | REPEAT | PING_PONG
    loop_count    = 0,                      # 0 = infinite
))
```

### Rules

1. `_indices` can never be animated (integer topology, not interpolatable).
2. `add_animation()` ignores a uid already active on that shader; `set_animation()` upserts.
3. A looping animation runs until `cancel_animation()` or `loop_count` exhaustion. By
   default it lands on `end_state`; set `revert_on_finish=True` to snap back.
4. One `bpy.app.timer` per unique framerate, shared across all animations at that rate.
   The tick loop disables a timer once nothing is left running at its framerate.

## Loggers

| Logger | Level | Usage |
|---|---|---|
| `DRAWHANDLER_LIFECYCLE` | `DEBUG` | Rebuild/clear events, handler registration, shader creation |
| `SHADER_BATCH_EVENTS` | `DEBUG` | Per-frame draw failures with per-shader error details |
| `ANIMATION_LIFECYCLE` | `DEBUG` | Animation create/update/cancel events |
| `ANIMATION_TICK_EVENTS` | `DEBUG` | Per-tick lerp errors and timer shutdown |

## Files

```text
block_onscreen_drawing/
├── __init__.py                       # Block declaration, BL props, UIList, panel, hook subscribers
├── README.md                         # This file
├── common_declarations.py            # Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_Data_Mirrors, Block_UIList_Configs
├── BL_drawing_structures.py          # Space/Region/Phase enums, builtin shaders enums, validation allowlists
├── data_structures.py                # Shader_Declaration, Shader_Instance, Drawhandler_Instance
├── demo_shader_settings.py           # Demo PropertyGroups (Common/Attribute/Region toggles), demo-animation apply/cancel
├── feature_shader_manager.py         # Wrapper_Shader_Manager (_update_RTC..., _update_BL...)
├── helpers.py                        # _rebuild_all_shaders, _clear_all_shaders, _universal_draw_callback, _validate_shader_definitions
├── ui.py                             # UIList draw helpers
├── builtin_shaders_and_effects/      # Reusable custom Shader_Instance subclasses
│   ├── custom_shader_billboard2D.py       # Billboard_Shader — camera-facing image quads
│   ├── custom_shader_polyline_dash.py     # Polyline_Dash_Shader — dashed line, Metal-safe thickness
│   ├── custom_shader_stripe.py            # Stripe_Shader — screen-locked window-space stripe holdout
│   ├── custom_shader_textbox_demo.py      # Textbox_Demo_Shader — N BLF text boxes
│   ├── legacy_custom_shader_linedash.py   # READ-ONLY reference: the old GL-line dashed shader
│   └── simple_textbox.py                  # draw_text_box() BLF renderer (used by textbox demo)
└── animations/                       # Animation sub-feature (see "Animations" above)
    ├── constants.py                  # ANIM_* string constants — imports nothing (leaf)
    ├── data_structures.py            # Animation_Declaration, Animation_Instance (leaf)
    ├── engine.py                     # lerp, tick loop, timer definitions, validation
    └── mixin.py                      # Animatable_Mixin — the per-shader public API
```

**Import direction inside `animations/`** is strictly one-way, which is what keeps the
`common_declarations.py -> ui.py` chain free of cycles:

```text
constants.py  <-  data_structures.py  <-  engine.py  <-  mixin.py  <-  ../data_structures.py
```

`constants.py` and `data_structures.py` import nothing from the parent block, so
downstream blocks can safely import declarations without pulling in the engine.
