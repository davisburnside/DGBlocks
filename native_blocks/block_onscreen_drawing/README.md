# block_onscreen_drawing

**Block ID:** `block-onscreen-draw`

## Purpose

Manages GPU-accelerated onscreen drawing in Blender viewports. Provides a pull-based
architecture: downstream blocks declare their shaders via `hook_get_shader_definitions`, and
`Wrapper_Shader_Manager` owns the full lifecycle — grouping shaders by draw location,
registering one Blender draw handler per `(space, region, phase)` group, creating
`Shader_Instance` objects, and persisting per-shader `is_enabled` state in a Blender
`CollectionProperty` UIList so preferences survive undo/redo.

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers, hooks |

## Architecture Summary

Drawing is controlled by the `enable_drawing` scene property. Setting it `True` triggers a full
rebuild:

1. `_cb_enable_drawing_changed` fires → calls `_rebuild_all_shaders()`
2. `hook_get_shader_definitions` is broadcast — each subscribed block returns a list of its `Shader_Definition` objects.
3. Definitions are validated, grouped by `(space, region, phase)`, and turned into live
   `Shader_Instance` objects with one Blender draw handler per group
4. `Wrapper_Runtime_Cache.resync_single_data_mirror()` pushes the new RTC list to the BL `shader_mirror` collection to reflect the new live shader set
5. `hook_before_first_draw` is broadcast — each subscribed block pushes initial geometry via
   `Wrapper_Shader_Manager.get_shader(uid)`

Setting `enable_drawing` `False` calls `_clear_all_shaders()`, which tears down all draw handlers and clears the BL `shader_mirror`.

### Undo / Redo — smart structural comparison

Undo/redo is handled automatically by the core runtime cache mirroring system which delegates to `Wrapper_Shader_Manager._update_RTC_with_mirrored_BL_data(event)`.

`_update_RTC_with_mirrored_BL_data` avoids unnecessary GPU work by comparing the current BL mirror against what is currently in the RTC:

1. If `enable_drawing` is `False` → calls `_clear_all_shaders()` and returns.
2. Uses `plan_dataclasses_to_match_collectionprop` to generate a list of differences between the BL collection and RTC list.
3. If `Create` or `Remove` actions exist (e.g. shader sets changed structure), it triggers a full `_rebuild_all_shaders()`.
4. If only `Edit` actions exist (e.g. the user toggled `is_enabled`), it simply toggles `is_enabled` on the affected RTC instances. No draw handlers or GPU resources are recreated.

The most common undo/redo step (editing non-drawing data while drawing is active) takes the
fast path and never touches GPU objects.

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
| `uid` | `StringProperty` | Key — matches `Shader_Instance.shader_uid` |
| `is_enabled` | `BoolProperty` | User-editable toggle; `update` callback syncs to RTC immediately |
| `draw_space` | `StringProperty` | Display only (`Draw_Space_Types.name`) |
| `draw_region` | `StringProperty` | Display only |
| `draw_phase` | `StringProperty` | Display only |

### Runtime Cache

| RTC Key | Type | Purpose |
|---|---|---|
| `SHADERS` | `dict[str, Shader_Instance]` | All live shader instances, keyed by `shader_uid` |
| `DRAW_PHASES` | `dict[tuple, Drawhandler_Instance]` | Live draw handler instances, keyed by `(space, region, phase)` |

## Hook Sources

| Member | Direction | Kwargs | Purpose |
|---|---|---|---|
| `hook_get_shader_definitions` | block_onscreen_drawing → subscribers | `{}` | Collect `Shader_Definition` objects; subscribers return a list of definitions |
| `hook_before_first_draw` | block_onscreen_drawing → subscribers | `{}` | Push initial geometry via `get_shader(uid)` after all instances are live |

## Hook Subscriptions (core hooks)

*(No direct core hook subscriptions in `__init__.py`. Undo/redo is handled via `Abstract_BL_RTC_List_Syncronizer` data mirror sync in `Wrapper_Shader_Manager._update_RTC_with_mirrored_BL_data`)*

## Public API — `Wrapper_Shader_Manager`

### `enable_and_poll_for_shaders()`

Sets `enable_drawing` to `True`, which triggers a full rebuild cycle.

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

## Public API — `Shader_Definition`

Declarative descriptor. One per logical shader. Supplied by downstream blocks inside
`hook_get_shader_definitions`.

```python
Shader_Definition(
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
Shader_Definition(
    uid="MY_BILLBOARD",
    shader_type=Shader_Types.TRIS,
    space=Draw_Space_Types.VIEW_3D,
    region=Draw_Region_Type.WINDOW,
    phase=Draw_Phase_type.POST_VIEW,
    custom_shader_class=My_Billboard_Shader,
    custom_shader_kwargs={"image_name": "my_image"},
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
the draw; these can be monkeypatched via `Shader_Definition.builtin_shader_before_draw`.

## Downstream Block Integration Example

```python
# my_block/__init__.py

from ...native_blocks.block_onscreen_drawing.feature_shader_manager import Wrapper_Shader_Manager
from .constants import MY_SHADER_DEFS

def hook_get_shader_definitions():
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
    Shader_Definition(
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

`validate_shader_definitions()` in `helpers.py` runs all checks before any Blender state is
mutated. Checks:

1. Duplicate `uid` detection across all contributing blocks
2. `(space, region, phase)` allowlist enforcement (see `BL_gpu_data_structures._VALID_SPACE_REGION_PHASE_COMBOS`)
3. Exactly one of `builtin_shader_name` / `custom_shader_class` per definition
4. Builtin shader name compatibility with the declared `shader_type`

## Loggers

| Logger | Level | Usage |
|---|---|---|
| `DRAWHANDLER_LIFECYCLE` | `DEBUG` | Rebuild/clear events, handler registration, shader creation |
| `SHADER_BATCH_EVENTS` | `DEBUG` | Per-frame draw failures with per-shader error details |

## Files

```text
block_onscreen_drawing/
├── __init__.py                       # Block declaration, BL props, UIList, panel, hook subscribers
├── README.md                         # This file
├── common_declarations.py            # Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_Data_Mirrors, Block_UIList_Configs
├── BL_drawing_structures.py          # Space/Region/Phase enums, builtin shaders enums, validation allowlists
├── data_structures.py                # Shader_Definition, Shader_Instance, Drawhandler_Instance
├── feature_shader_manager.py         # Wrapper_Shader_Manager (_update_RTC..., _update_BL...)
├── helpers.py                        # _rebuild_all_shaders, _clear_all_shaders, _universal_draw_callback, validate_shader_definitions
└── ui.py                             # UIList draw helpers
```
