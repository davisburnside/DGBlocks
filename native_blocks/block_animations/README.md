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

### `pause_animation(uid: str) -> None`

Toggle `is_paused` on the matching animation.  Elapsed time and delay countdown
freeze while paused; other animations at the same framerate are unaffected.

### `cancel_animation(uid: str) -> None`

Immediately remove an animation, revert the shader attribute to its pre-animation
value, and fire `callback_after_interrupt`.

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
| `callback_after_every_tick` | `Callable` | `None` | `callback(anim_instance)` called after each lerp step |
| `callback_after_finish` | `Callable` | `None` | `callback(anim_instance)` called after animation is removed from RTC |
| `callback_after_interrupt` | `Callable` | `None` | `callback(anim_instance)` called on `cancel_animation()` or error |

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

### Infinite loop via `callback_after_finish`

```python
def _loop(anim):
    Wrapper_Animation_Manager.add_animations([
        Animation_Declaration(
            animation_uid     = anim.animation_uid,  # reuse same uid — it was removed before this fires
            target_shader_uid = anim.target_shader_uid,
            data_type         = anim.data_type,
            data_name         = anim.data_name,
            end_state         = anim._start_state,   # reverse direction
            delay_start       = 0.01,                # tiny delay avoids deep recursion
            duration          = anim.duration,
            framerate         = anim.framerate,
            callback_after_finish = _loop,
        )
    ])

Wrapper_Animation_Manager.add_animations([
    Animation_Declaration(
        animation_uid         = "pulse",
        target_shader_uid     = "my_shader",
        data_type             = ANIM_DATA_TYPE_UNIFORMS,
        data_name             = "alpha",
        start_state           = 0.0,
        end_state             = 1.0,
        duration              = 0.6,
        callback_after_finish = _loop,
    )
])
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
  restored to the shader on `cancel_animation()` or unhandled tick exception.
- **Looping pattern.**  Call `add_animations()` inside `callback_after_finish`
  with a small `delay_start`.  The animation is removed from the RTC before the
  callback fires, so the uid is available for reuse.
