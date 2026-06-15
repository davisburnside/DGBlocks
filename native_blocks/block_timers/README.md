# block_timers

**Block ID:** `block-timers`

## Purpose

Manages Blender `bpy.app.timers` registrations for the addon. Provides a pull-based
architecture: downstream blocks declare their timers via `hook_get_timer_definitions`, and
`Wrapper_Timer_Manager` owns the full lifecycle — creating `Timer_Instance` objects,
registering one `bpy.app.timers` callable per instance, and persisting per-timer `is_enabled`
state in a Blender `CollectionProperty` UIList so preferences survive undo/redo.

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers, hooks |

## Architecture Summary

Timer execution is controlled by the `enable_timers` scene property. Setting it `True`
triggers a full rebuild:

1. `_cb_enable_timers_changed` fires → calls `_rebuild_all_timers()`
2. `hook_get_timer_definitions` is broadcast — each subscribed block returns a list of its
   `Timer_Definition` objects.
3. Definitions are validated, `Timer_Instance` objects are created, and one
   `bpy.app.timers` callable is registered per enabled instance.
4. `Wrapper_Runtime_Cache.resync_single_data_mirror()` pushes the new RTC list to the BL
   `timer_mirror` collection.

Setting `enable_timers` `False` calls `_clear_all_timers()`, which unregisters all bpy timers
and clears the BL `timer_mirror`.

### Single callback function

All timers share one hardcoded dispatch function: `_universal_timer_callback(timer_instance)`.
Each `bpy.app.timers` registration uses a thin closure (created by `_make_timer_func`) that
captures the specific `Timer_Instance` and delegates to `_universal_timer_callback`. This keeps
all callback logic in one place while satisfying the bpy requirement for a unique callable per
registration.

`_universal_timer_callback`:
- Guards: returns `None` (stops timer) if the instance is no longer in the RTC or is disabled.
- Calls `timer_instance._callback(timer_instance)` (sourced from the `Timer_Definition`).
- Increments `timer_instance.run_count` on success.
- On exception: sets `timer_instance.timer_error_str`, disables the timer, returns `None`.
- Returns `timer_instance.frequency` to reschedule.

### Undo / Redo — smart structural comparison

Same pattern as `block_onscreen_drawing`:

1. If `enable_timers` is `False` → calls `_clear_all_timers()` and returns.
2. Uses `plan_dataclasses_to_match_collectionprop` to diff BL mirror vs RTC list.
3. If `Create` or `Remove` actions exist → full `_rebuild_all_timers()`.
4. If only `Edit` actions (e.g. `is_enabled` toggled) → toggles `is_enabled` on the RTC
   instance and calls `_register_bpy_timer` / `_unregister_bpy_timer` accordingly. No full
   rebuild needed.

## Data Architecture

### Blender Data

| Property path | Type | Purpose |
|---|---|---|
| `scene.dgblocks_timers_props.enable_timers` | `BoolProperty` | Master on/off toggle |
| `scene.dgblocks_timers_props.timer_mirror` | `CollectionProperty[DGBLOCKS_PG_Timer_Mirror_Row]` | Per-timer BL persistence |
| `scene.dgblocks_timers_props.timer_mirror_selected_idx` | `IntProperty` | Active UIList selection index |

**`DGBLOCKS_PG_Timer_Mirror_Row` fields:**

| Field | Type | Notes |
|---|---|---|
| `timer_uid` | `StringProperty` | Key — matches `Timer_Instance.timer_uid` |
| `frequency` | `FloatProperty` | Display only (seconds) |
| `is_enabled` | `BoolProperty` | User-editable toggle; `update` callback syncs to RTC immediately |

### Runtime Cache

| RTC Key | Type | Purpose |
|---|---|---|
| `TIMERS` | `list[Timer_Instance]` | All live timer instances |

## Hook Sources

| Member | Direction | Kwargs | Purpose |
|---|---|---|---|
| `hook_get_timer_definitions` | block_timers → subscribers | `{}` | Collect `Timer_Definition` objects; subscribers return a list of definitions |

## UID Handling

- `timer_uid = ""` is valid. Blank UIDs are auto-assigned `"TIMER_0"`, `"TIMER_1"`, … during each rebuild cycle.
- Non-blank UIDs must be **globally unique** across all contributing blocks' definitions.
- Validation runs before any bpy or RTC state is mutated.

## Public API — `Wrapper_Timer_Manager`

### `enable_and_poll_for_timers()`

Sets `enable_timers` to `True`, which triggers a full rebuild cycle.

### `disable_timers()`

Sets `enable_timers` to `False`, which unregisters all live bpy timers, discards all
`Timer_Instance` objects, and clears the BL `timer_mirror`.

### `get_timer(uid: str) -> Timer_Instance | None`

Returns the live `Timer_Instance` for a given `uid`, or `None`.

---

## Public API — `Timer_Definition`

Declarative descriptor. One per logical timer. Supplied by downstream blocks inside
`hook_get_timer_definitions`.

```python
Timer_Definition(
    timer_uid = "MY_TIMER",     # "" for auto-assigned UID
    frequency = 2.0,            # seconds
    callback  = _my_callback,   # (timer_instance: Timer_Instance) -> None
)
```

## Public API — `Timer_Instance`

A `@dataclass` representing a single live timer. Lifecycle fully managed by
`Wrapper_Timer_Manager`.

### Key Fields

| Field | Type | Description |
|---|---|---|
| `timer_uid` | `str` | Unique identifier (auto-assigned if blank in definition) |
| `src_block_id` | `str` | Block that supplied the `Timer_Definition` |
| `frequency` | `float` | Seconds between fires |
| `is_enabled` | `bool` | Toggle on/off; synced from BL mirror on undo/redo |
| `run_count` | `int` | Number of successful fires since last rebuild |
| `timer_error_str` | `str \| None` | Last exception message; `None` = healthy |

---

## Validation

`validate_timer_definitions()` in `helpers.py` runs all checks before any state is mutated:

1. Duplicate **non-blank** `timer_uid` detection across all contributing blocks.
2. `frequency > 0` for every definition.
3. `callback` is callable for every definition.

## Downstream Block Integration Example

```python
# my_block/__init__.py

from ...native_blocks.block_timers.data_structures import Timer_Definition

def hook_get_timer_definitions():
    return [
        Timer_Definition(
            timer_uid = "MY_POLLING_TIMER",
            frequency = 5.0,
            callback  = _on_timer_fire,
        )
    ]

def _on_timer_fire(timer_instance):
    # Called every 5 seconds while enable_timers is True and is_enabled is True
    print(f"Timer fired. Total runs: {timer_instance.run_count}")
```

## Loggers

| Logger | Level | Usage |
|---|---|---|
| `TIMER_LIFECYCLE` | `DEBUG` | Rebuild/clear events, bpy timer registration/unregistration |
| `TIMER_FIRE_EVENTS` | `DEBUG` | Per-fire callback exceptions with per-timer error details |

## Files

```text
block_timers/
├── __init__.py               # Block declaration, BL props, UIList, panel, hook subscribers
├── README.md                 # This file
├── common_declarations.py    # Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_Data_Mirrors, Block_UIList_Configs
├── data_structures.py        # Timer_Definition, Timer_Instance
├── feature_timer_manager.py  # Wrapper_Timer_Manager (_update_RTC..., _update_BL...)
├── helpers.py                # _rebuild_all_timers, _clear_all_timers, _universal_timer_callback, validate_timer_definitions
└── ui.py                     # UIList draw helpers
```
