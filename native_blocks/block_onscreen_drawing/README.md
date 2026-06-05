# block_onscreen_drawing

**Block ID:** `block-onscreen-draw`

## Purpose

Manages GPU-accelerated onscreen drawing in Blender viewports. Provides a declarative API
(`set_state` / `clear`) that other blocks call to define and tear down batches of shaders.
Internally groups shader definitions by `(space, region, phase)`, registers one Blender draw
handler per group, and creates `Shader_Instance` objects that own individual `gpu.shader`
pipelines. A debug panel in the 3D View sidebar shows live handler/shader counts and status.

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers |

## Data Architecture

### Runtime Cache

This block owns two RTC members, both populated/cleared by `Wrapper_Draw_Handlers`:

| RTC Key | Type | Purpose |
|---|---|---|
| `DRAW_PHASES` | `dict[(Draw_Space_Types, Draw_Region_Type, Draw_Phase_type), Drawhandler_Instance]` | Live draw handler instances, keyed by their Blender registration tuple |
| `SHADERS` | `dict[str, Shader_Instance]` | All shader instances keyed by unique `shader_uid` |

### Blender Data

None. All state is runtime-only.

### Data Mirrors

None.

## Hook Sources

| Hook member | Fires when | Extra kwargs |
|---|---|---|
| `hook_draw_event` | Each frame Blender invokes the registered draw handlers | `draw_handler_instance: Drawhandler_Instance` |

Subscriber blocks implement `hook_draw_event(draw_handler_instance)` as a top-level function
in `__init__.py`. They receive the `Drawhandler_Instance` dataclass and can inspect or extend
behavior during the draw callback.

## Public API — `Wrapper_Draw_Handlers`

### `set_state(shader_defs: list[Shader_Definition]) -> None`

Declares the complete desired set of shaders. All validation runs before any Blender state is
mutated — either the full state is applied atomically or nothing changes.

**Validation checks:**
1. Duplicate `uid` detection
2. `(space, region, phase)` allowlist enforcement (see `_VALID_SPACE_REGION_PHASE_COMBOS`)
3. Exactly one of `builtin_shader_name` or `custom_shader_class` must be set per def
4. Builtin shader name compatibility with the declared `shader_type`

The method internally:
- Tears down any existing state via `clear()`
- Groups `Shader_Definition` objects by `(space, region, phase)`
- Creates one `Drawhandler_Instance` per group
- Instantiates `Shader_Instance` objects (builtin or custom subclass)
- Registers a single Blender `draw_handler_add` per group, bound to `callback_omnishader_draw`
- Stores everything in `DRAW_PHASES` and `SHADERS` RTC members

**Example:**
```python
from native_blocks.block_onscreen_drawing.drawing_constants import (
    Shader_Definition, Draw_Space_Types, Draw_Region_Type, Draw_Phase_type,
    Shader_Types, Builtin_Shader_Names,
)
from native_blocks.block_onscreen_drawing.feature_draw_handler_manager import (
    Wrapper_Draw_Handlers,
)

Wrapper_Draw_Handlers.set_state([
    Shader_Definition(
        uid="my-lines",
        group_id="my-feature",
        shader_type=Shader_Types.LINES,
        space=Draw_Space_Types.VIEW_3D,
        region=Draw_Region_Type.WINDOW,
        phase=Draw_Phase_type.POST_VIEW,
        builtin_shader_name=Builtin_Shader_Names.POLYLINE_UNIFORM_COLOR,
    ),
    Shader_Definition(
        uid="my-points",
        group_id="my-feature",
        shader_type=Shader_Types.POINTS,
        space=Draw_Space_Types.VIEW_3D,
        region=Draw_Region_Type.WINDOW,
        phase=Draw_Phase_type.POST_VIEW,
        builtin_shader_name=Builtin_Shader_Names.POINT_UNIFORM_COLOR,
    ),
])
```

### `clear() -> None`

Tears down all live Blender draw handlers and discards all shader instances. Called
automatically by `destroy_wrapper()` and at the start of `set_state()` before applying
new state.

### `get_shader(uid: str) -> Shader_Instance | None`

Returns the live `Shader_Instance` for a given `uid`, or `None` if not found. Callers
typically use this to call `set_points()`, `set_colors()`, or `set_uniform()` before
each frame.

```python
shader = Wrapper_Draw_Handlers.get_shader("my-lines")
if shader:
    shader.set_points([(0,0,0), (1,0,0), (0,1,0)])
    shader.set_uniform("color", (1.0, 0.0, 0.0, 1.0))
```

## Public API — `Shader_Instance`

A `@dataclass` representing a single GPU shader pipeline. Not a subclass of
`Abstract_Feature_Wrapper` — its lifecycle is fully managed by `Wrapper_Draw_Handlers`.

### Fields

| Field | Type | Description |
|---|---|---|
| `shader_uid` | `str` | Unique identifier |
| `shader_group_id` | `str` | Logical grouping key |
| `shader_type` | `str` | `'POINTS'`, `'LINES'`, or `'TRIS'` |
| `builtin_shader_name` | `str \| None` | Builtin Blender shader name, or `None` for custom |
| `is_enabled` | `bool` | Toggle draw on/off per-instance (default `True`) |
| `shader_error_str` | `str \| None` | Last exception message. Set to None upon successful draw

### Methods

| Method | Triggers batch rebuild? | Purpose |
|---|---|---|
| `set_indices(value)` | Yes | Set index array (for `TRIS`) |
| `set_points(value)` | Yes | Set vertex positions |
| `set_colors(value)` | Yes | Set per-vertex colors (`SMOOTH_COLOR` shaders only) |
| `set_uniform(name, value)` | No | Set a shader uniform (auto-maps float/bool/int/sampler) |
| `draw()` | — | Bind shader and draw the batch (called by draw callback) |

**Custom shader subclasses** set `custom_shader_class` on `Shader_Definition`. The class must
inherit `Shader_Instance` and create its own `gpu.shader` in `__post_init__`. Extra kwargs
are forwarded from `Shader_Definition.custom_shader_kwargs`.

## Enums and Dataclasses

All defined in `drawing_constants.py`:

| Type | Purpose |
|---|---|
| `Draw_Space_Types` | Maps to Blender space types (`SpaceView3D`, `SpaceNodeEditor`, etc.) |
| `Draw_Region_Type` | Region within a space (`WINDOW`, `HEADER`, `HUD`, etc.) |
| `Draw_Phase_type` | Draw phase (`PRE_VIEW`, `POST_VIEW`, `POST_PIXEL`, `BACKDROP`) |
| `Builtin_Shader_Names` | Known Blender built-in shader names |
| `Shader_Types` | Batch type (`POINTS`, `LINES`, `TRIS`) |
| `Shader_Definition` | Declarative descriptor for a single shader |
| `Drawhandler_Definition` | Internal grouping struct (space, region, phase + shader defs) |

### Valid (space, region, phase) combinations

The allowlist `_VALID_SPACE_REGION_PHASE_COMBOS` in `drawing_constants.py` documents every
known-valid tuple across all supported space types. `set_state()` raises `ValueError` for
any combination not in this list before touching Blender state.

### Builtin shader compatibility

`_BUILTIN_SHADER_COMPATIBLE_TYPES` maps each `Builtin_Shader_Names` member to the set of
`Shader_Types` it supports. `set_state()` validates this pairing upfront.

## Panel

`DGBLOCKS_PT_Debug_Drawing_Panel` appears in the 3D Viewport side panel under the addon's
tab. For each active `Drawhandler_Instance` it displays:

- Space name, region, and phase
- Number of shaders
- ON/OFF status (whether a live Blender handle exists)

## Loggers

| Logger | Level | Usage |
|---|---|---|
| `DRAWHANDLER_LIFECYCLE` | `DEBUG` | Handler registration, teardown, and set_state/clear events |
| `SHADER_BATCH_EVENTS` | `DEBUG` | Per-frame draw failures with per-shader error details |

## Files

```
block_onscreen_drawing/
├── __init__.py                          # Block declaration, DGBLOCKS_PT_Debug_Drawing_Panel
├── README.md                            # This file
├── common_constants.py                  # Block_Hook_Sources, Block_Loggers, Block_RTC_Members
├── drawing_constants.py                 # Space/Region/Phase enums, Shader_Definition/Drawhandler_Definition, validation allowlists
├── feature_draw_handler_manager.py      # Wrapper_Draw_Handlers (set_state, clear, get_shader)
├── feature_shader.py                    # Shader_Instance dataclass
└── helpers.py                           # callback_omnishader_draw, validate_shader_definitions