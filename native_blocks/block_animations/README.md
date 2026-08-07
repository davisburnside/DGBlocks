# block_animations

Runtime animation system for `block_onscreen_drawing` shaders.  Lerps any
Python-readable attribute on a `Shader_Instance` (batch arrays **or** cached
uniform values) over time, driven by `block_timers`.

---

## Dependencies

| Block | Role |
|---|---|
| `block-core` | RTC, loggers, hooks |
| `block-onscreen-draw` | `Shader_Instance` target, `Wrapper_Shader_Manager.get_shader()` |
| `block-timers` | Provides the tick cadence via `hook_get_timer_definitions` |

---

## Public API — `Wrapper_Animation_Manager`

```python
from native_blocks.block_animations.feature_animation_manager import Wrapper_Animation_Manager
from native_blocks.block_animations.data_structures import Animation_Declaration, ANIM_DATA_TYPE_BATCH, ANIM_DATA_TYPE_UNIFORMS
```

### `add_animations(declarations: list[Animation_Declaration]) -> None`

Create one or more animations.  Each declaration is validated and, if the target
shader exists, stored as an `Animation_Instance` in the RTC.  A timer rebuild is
requested for any new framerate introduced.

### `set_animation(declaration: Animation_Declaration) -> None`

**Upsert — the call to reach for whenever the data being animated changes.**

- UID not active → identical to `add_animations([declaration])`.
- UID already active → the live instance is updated **in place**, and its phase
  (`_elapsed_time`) is **preserved**.

Phase preservation is what makes a looping animation seamless across data
changes: swapping in a new point/color set mid-cycle produces no visual jump,
because the animation simply carries on from where it was with the new data.

```python
# Called every time the selection changes — no interrupt, no restart, no seam.
Wrapper_Animation_Manager.set_animation(Animation_Declaration(
    animation_uid     = "MY_PULSE",
    target_shader_uid = "MY_SHADER",
    data_type         = ANIM_DATA_TYPE_BATCH,
    data_name         = "_colors",
    start_state       = colors_dim,
    end_state         = colors_bright,
    duration          = 1.2,
    framerate         = 30,
    loop_mode         = ANIM_LOOP_PING_PONG,
    loop_count        = 0,   # infinite
))
```

> `start_state=None` auto-captures from the shader **on create only**. On update it
> keeps the existing `start_state`, since re-capturing mid-lerp would read a
> half-interpolated value.

### `update_animation(uid: str, **fields) -> None`

Patch individual fields on a live animation, preserving phase.  Accepts any
`Animation_Instance` field plus the aliases `start_state` and the four callback
names.  Warns and does nothing if `uid` is not active — use `set_animation()`
when the animation may not exist yet.

### `get_animation(uid: str)` / `has_animation(uid: str) -> bool`

Read-only lookup of a live `Animation_Instance`.

### `pause_animation(uid: str) -> None`

Toggle `is_paused` on the matching animation.  Elapsed time and delay countdown
freeze while paused; other animations at the same framerate are unaffected.

### `cancel_animation(uid: str, revert: bool = True) -> None`

The interrupt entry point.  Immediately removes an animation and fires
`callback_after_interrupt`.  By default the shader attribute is reverted to its
pre-animation value; pass `revert=False` to freeze it at the last written value.

This is the only way to stop an infinite (`loop_count=0`) looping animation.


### `get_active_animations() -> list[Animation_Instance]`

Return a snapshot of all currently active `Animation_Instance` objects.

---

## `Animation_Declaration` fields

| Field | Type | Default | Description |
|---|---|---|---|
| `animation_uid` | `str` | *required* | Unique ID; must not already be active |
| `target_shader_uid` | `str` | *required* | UID of the target `Shader_Instance` |
| `data_type` | `str` | *required* | `'batch_data'` or `'uniforms_data'` |
| `data_name` | `str` | *required* | Attribute name (`'_colors'`, `'_sizes'`, …) or uniform name (`'color'`, …) |
| `end_state` | `Any` | *required* | Lerp target; same shape/dtype as the start value |
| `start_state` | `Any` | `None` | If `None`, auto-captured from shader at `add_animations()` time |
| `delay_start` | `float` | `0.0` | Seconds before lerp begins |
| `duration` | `float` | `1.0` | Seconds for the full lerp |
| `framerate` | `float` | `60.0` | Ticks per second; shared framerate → shared timer |
| `enabled` | `bool` | `True` | Set `False` to skip creation |
| `loop_mode` | `str` | `ANIM_LOOP_ONCE` | `ANIM_LOOP_ONCE`, `ANIM_LOOP_REPEAT`, or `ANIM_LOOP_PING_PONG` |
| `loop_count` | `int` | `0` | Cycles to play when looping; `0` = infinite |
| `revert_on_finish` | `bool` | `False` | If `True`, restore `start_state` when the animation completes |
| `callback_after_every_tick` | `Callable` | `None` | `callback(anim_instance)` called after each lerp step |
| `callback_after_loop` | `Callable` | `None` | `callback(anim_instance)` called at each loop boundary |
| `callback_after_finish` | `Callable` | `None` | `callback(anim_instance)` called after animation is removed from RTC |
| `callback_after_interrupt` | `Callable` | `None` | `callback(anim_instance)` called on `cancel_animation()` or error |

---

## The complete rulebook

There is no hidden behaviour beyond these three rules:

1. **`_indices` can never be animated** (it is integer topology, not an
   interpolatable value).  Every other batch attribute and every uniform can be.
2. **`add_animations()` ignores a declaration whose uid is already active.**
   `set_animation()` upserts instead, preserving the live animation's phase.
3. **A looping animation runs until `cancel_animation()` or `loop_count`
   exhaustion.**  By default an animation lands on `end_state`; set
   `revert_on_finish=True` to snap back to `start_state` instead.

---

## Loop modes

| Mode | Behaviour at `t >= 1.0` |
|---|---|
| `ANIM_LOOP_ONCE` | Finish: remove from RTC, fire `callback_after_finish` |
| `ANIM_LOOP_REPEAT` | Jump back to `start_state` and replay forwards |
| `ANIM_LOOP_PING_PONG` | Swap `start_state` ↔ `end_state` and play back the other way |

At every loop boundary the overshoot is **carried into the next cycle**, so long-
running loops never accumulate timing drift.  A ping-pong out-and-back counts as
**two** completed loops (`loops_completed`).

Useful read-only properties on `Animation_Instance`:

| Property | Meaning |
|---|---|
| `is_looping` | `True` for `REPEAT` / `PING_PONG` |
| `completion_factor` | Position within the current cycle, `0.0` → `1.0` |
| `loops_completed` | Number of cycles finished so far |

---


## Data types

### `batch_data`
Writes directly to a Python-side numpy attribute on the `Shader_Instance` and
sets `_needs_new_batch = True` each tick.  The batch is rebuilt on the next draw.

```python
# Built-in attributes
data_name='_points'   # shader._points  (float32 ndarray)
data_name='_colors'   # shader._colors  (float32 ndarray)

# Custom shader attributes (e.g. Billboard_Shader)
data_name='_sizes'    # shader._sizes   (list[float])
```

### `uniforms_data`
Calls `shader.set_uniform(data_name, lerped_value)` each tick.  No batch
rebuild needed.  The `_uniforms` dict on `Shader_Instance` caches every
`set_uniform()` call, so `start_state` can be auto-captured for uniforms that
have been set at least once before the animation starts.

```python
data_name='color'   # shader.set_uniform("color", value)
data_name='alpha'   # shader.set_uniform("alpha", value)
```

---

## Usage examples

### Fade in a SMOOTH_COLORS shader color uniform

```python
Wrapper_Animation_Manager.add_animations([
    Animation_Declaration(
        animation_uid     = "fade_in_color",
        target_shader_uid = "my_color_shader",
        data_type         = ANIM_DATA_TYPE_UNIFORMS,
        data_name         = "color",
        start_state       = (0.0, 0.5, 1.0, 0.0),   # explicit: uniform not yet set
        end_state         = (0.0, 0.5, 1.0, 1.0),
        duration          = 0.5,
        framerate         = 30.0,
    )
])
```

### Slide batch points (auto-captures current positions as start)

```python
Wrapper_Animation_Manager.add_animations([
    Animation_Declaration(
        animation_uid     = "slide_points",
        target_shader_uid = "my_lines_shader",
        data_type         = ANIM_DATA_TYPE_BATCH,
        data_name         = "_points",
        end_state         = np.array([[200.0, 400.0], [500.0, 400.0]], dtype=np.float32),
        duration          = 0.8,
        framerate         = 60.0,
    )
])
```

### Endless pulse (infinite ping-pong)

```python
Wrapper_Animation_Manager.add_animations([
    Animation_Declaration(
        animation_uid     = "pulse",
        target_shader_uid = "my_shader",
        data_type         = ANIM_DATA_TYPE_UNIFORMS,
        data_name         = "alpha",
        start_state       = 0.2,
        end_state         = 1.0,
        duration          = 0.6,
        loop_mode         = ANIM_LOOP_PING_PONG,
        loop_count        = 0,          # infinite
    )
])

# ...later, stop it:
Wrapper_Animation_Manager.cancel_animation("pulse")
```

### Keeping a pulse alive across data changes

The animation instance lives for as long as the feature needs it.  Whenever the
underlying data changes (e.g. the user's selection grows or shrinks), rebuild the
states and call `set_animation()` with the same uid — the phase is preserved, so
the pulse never blinks or restarts:

```python
def refresh_selection_pulse(colors_dim, colors_bright):
    Wrapper_Animation_Manager.set_animation(Animation_Declaration(
        animation_uid     = "SELECTION_PULSE",
        target_shader_uid = "SELECTION_SHADER",
        data_type         = ANIM_DATA_TYPE_BATCH,
        data_name         = "_colors",
        start_state       = colors_dim,
        end_state         = colors_bright,
        duration          = 1.2,
        framerate         = 30,
        loop_mode         = ANIM_LOOP_PING_PONG,
        loop_count        = 0,
    ))
```


---

## Architecture notes

- **No Blender data.**  All animation state lives exclusively in the RTC
  (`Block_RTC_Members.ANIMATIONS`).
- **Timer sharing.**  One `bpy.app.timer` per unique framerate.  Multiple
  animations at the same framerate share a single timer.
- **Timer lifecycle.**  When the last animation at a framerate finishes or is
  cancelled, the timer is disabled and a deferred `request_timer_rebuild()` is
  scheduled (0.01 s) to clean up the RTC timer entry.
- **State revert.**  `_start_state` (captured at `add_animations()` time) is
  restored to the shader on `cancel_animation(revert=True)` (the default) or on an
  unhandled tick exception.  On normal completion the shader keeps `end_state`
  unless `revert_on_finish=True`.
- **Looping.**  Handled natively by `loop_mode` — no callback juggling required.
  Loop boundaries carry their overshoot forward, so cycles never drift.
- **Updating a live animation.**  `set_animation()` / `update_animation()` mutate
  the existing `Animation_Instance` rather than replacing it, so `_elapsed_time`
  (the phase) survives.  This is the supported way to keep a long-lived looping
  animation visually seamless while its underlying data changes.


