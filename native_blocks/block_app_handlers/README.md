# block_app_handlers

**Block ID:** `block-app-handlers`

## Purpose

Manages `bpy.app.handlers` registrations on behalf of all downstream blocks. Downstream
blocks declare which handler events they need via `hook_get_app_handler_subscriptions`, and
this block installs the Blender callbacks, applies re-entrancy protection and frequency
filtering, then fires per-type notification hooks when Blender triggers the event.

**Structural handlers owned by `block_core` — NOT available here:**
`load_post`, `undo_post`, `redo_post`

---

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers, hooks |

---

## Architecture Summary

### Lifecycle

1. `hook_post_startup` subscriber fires `Wrapper_App_Handlers.refresh_subscriptions()`.
2. `refresh_subscriptions()` fires `hook_get_app_handler_subscriptions` to all subscribers.
3. Each subscriber returns `list[App_Handler_Subscription_Declaration]`.
4. Subscriptions are merged per handler type (minimum frequency filter wins).
5. `bpy.app.handlers` callbacks are installed for all requested types.
6. When Blender triggers a handler, `_fire_handler(type_name, **kwargs)` runs:
   - **Re-entrancy guard** — if this type is already executing, skip (prevents loops).
   - **`is_enabled` check** — if user disabled the type in UIList, skip with debug log.
   - **Frequency filter** — if less than `frequency_filter_seconds` have elapsed, skip.
   - **Notification hook** — fires `hook_app_handler_<type_name>(**kwargs)`.

### Re-entrancy Protection

An RTC `set[str]` (`APP_HANDLERS_CURRENTLY_EXECUTING`) tracks which handler types are
currently in their notification chain. If a handler fires while already executing (e.g., a
`save_pre` subscriber triggers another save), the second call is silently discarded with a
warning log.

### Frequency Filter

Each `App_Handler_Subscription_Declaration` has an optional `frequency_filter_seconds`.
When multiple blocks subscribe to the same type, the **minimum** across all declarations
is used (most-permissive merge). This ensures no subscriber is starved of events.

Common use case: set `frequency_filter_seconds = 0.25` for `frame_change_post` to avoid
running expensive logic on every single frame during animation playback.

### `is_enabled` Toggle

Each handler type has a user-facing `is_enabled` checkbox in the UIList. When disabled:
- The Blender callback remains installed (no re-registration overhead).
- The downstream notification hook is skipped.
- A `DEBUG` log message is written.
- `is_enabled` always resets to `True` on the next `refresh_subscriptions()` call.

---

## Downstream Block Integration

```python
# my_block/__init__.py

from native_blocks.block_app_handlers.data_structures import (
    App_Handler_Type,
    App_Handler_Subscription_Declaration,
)


def hook_get_app_handler_subscriptions():
    """Declare which handlers this block needs."""
    return [
        App_Handler_Subscription_Declaration(
            handler_type = App_Handler_Type.save_pre,
        ),
        App_Handler_Subscription_Declaration(
            handler_type             = App_Handler_Type.frame_change_post,
            frequency_filter_seconds = 0.5,   # at most once per 0.5 seconds
        ),
    ]


def hook_app_handler_save_pre(scene):
    """Called before every file save (after re-entrancy + enabled + freq checks)."""
    print(f"About to save scene: {scene.name}")


def hook_app_handler_frame_change_post(scene, depsgraph):
    """Called after frame changes, rate-limited to 2Hz."""
    print(f"Frame changed in scene: {scene.name}")
```

---

## Hook Sources

### Poll hook (downstream → block_app_handlers)

| Member | Direction | Kwargs | Returns |
|---|---|---|---|
| `hook_get_app_handler_subscriptions` | downstream → block | `{}` | `list[App_Handler_Subscription_Declaration]` |

### Notification hooks (block_app_handlers → downstream)

| Member | Kwargs |
|---|---|
| `hook_app_handler_save_pre` | `scene` |
| `hook_app_handler_save_post` | `scene` |
| `hook_app_handler_load_pre` | _(none)_ |
| `hook_app_handler_render_init` | `scene` |
| `hook_app_handler_render_pre` | `scene` |
| `hook_app_handler_render_post` | `scene` |
| `hook_app_handler_render_write` | `scene` |
| `hook_app_handler_render_stats` | `scene` |
| `hook_app_handler_render_cancel` | `scene` |
| `hook_app_handler_render_complete` | `scene` |
| `hook_app_handler_object_bake_pre` | `scene` |
| `hook_app_handler_object_bake_complete` | `scene` |
| `hook_app_handler_object_bake_cancel` | `scene` |
| `hook_app_handler_frame_change_pre` | `scene`, `depsgraph` |
| `hook_app_handler_frame_change_post` | `scene`, `depsgraph` |
| `hook_app_handler_annotation_pre` | `scene` |
| `hook_app_handler_annotation_post` | `scene` |
| `hook_app_handler_composite_pre` | `scene` |
| `hook_app_handler_composite_post` | `scene` |
| `hook_app_handler_composite_cancel` | `scene` |
| `hook_app_handler_version_update` | _(none)_ |
| `hook_app_handler_xr_session_start_pre` | _(none)_ |
| `hook_app_handler_xr_session_end` | _(none)_ |

---

## Data Architecture

### Blender Data

| Property path | Type | Purpose |
|---|---|---|
| `scene.dgblocks_app_handlers_props.handler_status_mirror` | `CollectionProperty` | Display mirror of active handler statuses |
| `scene.dgblocks_app_handlers_props.handler_status_mirror_selected_idx` | `IntProperty` | Active UIList row |

**`DGBLOCKS_PG_App_Handler_Status_Row` fields:**

| Field | Type | Editable | Notes |
|---|---|---|---|
| `handler_type_name` | `StringProperty` | No | Key — matches `App_Handler_Type.name` |
| `is_enabled` | `BoolProperty` | **Yes** | Fires `set_handler_enabled()` on change |
| `is_registered` | `BoolProperty` | No | Whether callback is in `bpy.app.handlers` |
| `subscriber_count` | `IntProperty` | No | Blocks that requested this type |
| `frequency_filter_seconds` | `FloatProperty` | No | Merged min-interval in seconds |

### Runtime Cache

| RTC Key | Type | Purpose |
|---|---|---|
| `APP_HANDLER_STATUS_LIST` | `list[RTC_App_Handler_Status_Instance]` | Status of all active handler types |
| `APP_HANDLERS_CURRENTLY_EXECUTING` | `set[str]` | Re-entrancy guard — types currently in their notification chain |

### `RTC_App_Handler_Status_Instance` Fields

| Field | Type | BL-mirrored | Description |
|---|---|---|---|
| `handler_type_name` | str | Yes (key) | Matches `App_Handler_Type.name` |
| `is_registered` | bool | Yes | In `bpy.app.handlers` list |
| `is_enabled` | bool | Yes | Notification hook active |
| `subscriber_count` | int | Yes | From last poll |
| `frequency_filter_seconds` | float | Yes | Merged min-interval |
| `fire_count` | int | **No** | Times notification hook was fired |
| `last_fired_timestamp` | float | **No** | `time.monotonic()` of last fire |

---

## Public API — `Wrapper_App_Handlers`

| Method | Returns | Description |
|---|---|---|
| `refresh_subscriptions()` | `None` | Re-poll subscribers; reconcile installed handlers |
| `set_handler_enabled(type_name, is_enabled)` | `None` | Enable/disable notification for one handler type |

---

## Loggers

| Logger | Level | Usage |
|---|---|---|
| `APP_HANDLERS_LIFECYCLE` | `INFO` | refresh_subscriptions, install/uninstall, init/remove |
| `APP_HANDLERS_EVENTS` | `DEBUG` | Per-fire dispatch, re-entrancy warnings, freq-limit skips |

---

## Files

```text
block_app_handlers/
├── __init__.py              # _BLOCK_DECLARATION, BL props, Panel, Operator,
│                            # hook_post_startup() subscriber
├── README.md                # This file
├── common_declarations.py   # Block_Hook_Sources (poll + all notifications),
│                            # Block_Loggers, Block_RTC_Members, Block_Data_Mirrors,
│                            # Block_UIList_Configs
├── data_structures.py       # App_Handler_Type (enum), App_Handler_Subscription_Declaration,
│                            # RTC_App_Handler_Status_Instance
├── feature_app_handlers.py  # Wrapper_App_Handlers (FWC) — refresh_subscriptions(),
│                            # set_handler_enabled(), _sync_status_to_BL()
├── handler_callbacks.py     # @persistent bpy.app.handlers callbacks, _fire_handler()
│                            # central dispatch, install/uninstall helpers, _CALLBACK_MAP
└── ui.py                    # _uilist_draw_row, _uilist_draw_selection_details
```
