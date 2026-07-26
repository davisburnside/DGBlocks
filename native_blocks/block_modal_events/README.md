# block_modal_events

**Block ID:** `block-modal-events`

## Purpose

Runs a single, always-on Blender **modal operator** ("the router") and fans every captured
mouse / keyboard / scroll / window event out to downstream blocks as ordered, per-block
**listeners**. Provides a pull-based architecture: downstream blocks declare their interest via
`hook_get_modal_listener_definitions`, and `Wrapper_Modal_Manager` owns the full lifecycle —
creating `RTC_Modal_Listener_Instance` records, dispatching events in deterministic priority
order, aggregating return values, and persisting per-listener `is_enabled` state in a Blender
`CollectionProperty` UIList so preferences survive undo/redo.

This is the **single-router / many-logical-subscribers** model: there is exactly one real
`{'RUNNING_MODAL'}` operator on Blender's modal stack. Ordering and event consumption are
controlled entirely in Python (by `priority`), rather than by Blender's coarse LIFO +
`PASS_THROUGH` stack semantics.

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, loggers, hooks |

> **Overlay drawing is NOT owned by this block.** Modal input-capture and GPU overlay drawing
> are fully independent mechanisms in Blender. A listener that needs to draw should declare a
> `Shader_Definition` through `block_onscreen_drawing` instead of registering its own draw
> handler.

## Architecture Summary

Modal capture is controlled by the `enable_modal` scene property:

1. The **listener registry** is (re)built independently of `enable_modal` by
   `_rebuild_all_listeners()`, which fires `hook_get_modal_listener_definitions`. Each
   subscribing block returns a **single-element** list containing one `Modal_Listener_Definition`
   (the listener is keyed by the source block id — one listener per block).
2. Setting `enable_modal = True` invokes the router operator `DGBLOCKS_OT_Modal_Event_Router`,
   which calls `modal_handler_add(self)` and returns `{'RUNNING_MODAL'}`. It fires each enabled
   listener's `before_modal_start` callback and broadcasts the `hook_modal_started` hook.
3. On every event, the router classifies it (see *Event Categories*), then dispatches to each
   enabled listener (skipping any whose matching `ignore_*` flag is set) in ascending `priority`
   order, calling `on_event(listener_instance, context, event)`.
4. Setting `enable_modal = False` lets the router self-terminate on its **next received event**
   (firing each `before_modal_end` and broadcasting `hook_modal_ended`).

The router reads listeners **live** from the RTC every event, so a rebuild while the modal is
running takes effect immediately without restarting the modal.

### Return value aggregation

Each listener's `on_event` returns a Blender modal return set, or `None` (treated as
`{'PASS_THROUGH'}`). The router default is `{'PASS_THROUGH'}` (non-blocking). The **first**
listener (in priority order) to return a non-`PASS_THROUGH` value **wins** for that event and
short-circuits the remaining listeners. If a listener returns `{'FINISHED'}` or `{'CANCELLED'}`,
the router ends.

### Crash isolation

If a listener's `on_event` raises, the router **disables that listener**
(`is_enabled = False`, records `listener_error_str`) and keeps running — one misbehaving block
cannot take down the modal or the other listeners. The router's own `modal()` body is fully
wrapped so no exception escapes into Blender's event callback.

### Startup / file load

A modal operator does not survive a file load, and Blender exposes no API to enumerate running
modals. The router is therefore (re)started from the `hook_post_startup` subscriber (when
`enable_modal` is `True`), which runs once the bpy context is ready — `_init_wrapper` only
rebuilds the listener registry, it does **not** invoke the operator (context may not be ready
during `init_post_bpy`).

### Undo / Redo — smart structural comparison

Same pattern as `block_timers` / `block_onscreen_drawing`, via
`Wrapper_Modal_Manager._update_RTC_with_mirrored_BL_data`:

1. Uses `plan_dataclasses_to_match_collectionprop` to diff the BL mirror vs the RTC list.
2. If `Create` or `Remove` actions exist → full `_rebuild_all_listeners()`.
3. If only `Edit` actions (e.g. `is_enabled` toggled) → toggles `is_enabled` on the affected RTC
   instance. The running router picks this up live — no restart required.

## Event Categories

Each incoming event is classified into one coarse category, mapped to one per-listener
`ignore_*` flag:

| Category | Maps to flag | Example `event.type`s |
|---|---|---|
| `MOUSE_CLICK` | `ignore_mouse_click_events` | `LEFTMOUSE`, `RIGHTMOUSE`, `MIDDLEMOUSE`, `BUTTON4/5MOUSE` |
| `MOUSE_MOVE`  | `ignore_mouse_move` | `MOUSEMOVE`, `INBETWEEN_MOUSEMOVE` |
| `SCROLL`      | `ignore_scroll_events` | `WHEELUP/DOWNMOUSE`, `TRACKPADPAN`, `TRACKPADZOOM` |
| `KEYBOARD`    | `ignore_keyboard_events` | all key types |
| `WINDOW`      | `ignore_window_events` | `WINDOW_DEACTIVATE` |
| `OTHER`       | *(none — always delivered)* | `NDOF_MOTION`, etc. |

This block does **not** add a modal event timer, so listeners never receive `TIMER` events.
Use `block_timers` for time-based work.

## Data Architecture

### Blender Data

| Property path | Type | Purpose |
|---|---|---|
| `scene.dgblocks_modal_events_props.enable_modal` | `BoolProperty` | Master on/off toggle; starts/stops the router |
| `scene.dgblocks_modal_events_props.listener_mirror` | `CollectionProperty[DGBLOCKS_PG_Modal_Listener_Row]` | Per-listener BL persistence |
| `scene.dgblocks_modal_events_props.listener_mirror_selected_idx` | `IntProperty` | Active UIList selection index |

**`DGBLOCKS_PG_Modal_Listener_Row` fields:**

| Field | Type | Notes |
|---|---|---|
| `src_block_id` | `StringProperty` | Key — matches `RTC_Modal_Listener_Instance.src_block_id` |
| `priority` | `IntProperty` | Display only |
| `is_enabled` | `BoolProperty` | User-editable toggle; `update` callback syncs to RTC immediately |

### Runtime Cache

| RTC Key | Type | Purpose |
|---|---|---|
| `LISTENERS` | `list[RTC_Modal_Listener_Instance]` | All live listener instances, sorted by `(priority, src_block_id)` |

### Data Mirrors

| Mirror | Key fields | Data fields | Scene path |
|---|---|---|---|
| `LISTENER_MIRROR` | `["src_block_id"]` | `["is_enabled"]` | `dgblocks_modal_events_props.listener_mirror` |

## Hook Sources

| Member | Direction | Kwargs | Purpose |
|---|---|---|---|
| `hook_get_modal_listener_definitions` | block_modal_events → subscribers | `{}` | Collect `Modal_Listener_Definition` objects; subscribers return a single-element list |
| `hook_modal_started` | block_modal_events → subscribers | `{context}` | Broadcast once when the router starts |
| `hook_modal_ended` | block_modal_events → subscribers | `{context, reason}` | Broadcast once when the router stops (`reason` ∈ `"disabled"`, `"listener_requested"`) |

## Public API — `Wrapper_Modal_Manager`

### `enable_and_poll_for_modal_listeners()`
Sets `enable_modal` to `True`, starting the router.

### `disable_modal()`
Sets `enable_modal` to `False`; the router self-terminates on its next event.

### `get_listener(src_block_id: str) -> RTC_Modal_Listener_Instance | None`
Returns the live listener instance for a block id, or `None`.

### `repoll(event)`
Re-polls all listener definitions and rebuilds the RTC registry + BL mirror. Does not
start/stop the router; the running router picks up the new set immediately.

## Public API — `Modal_Listener_Definition`

Declarative descriptor. **One per block.** Supplied inside `hook_get_modal_listener_definitions`.

```python
Modal_Listener_Definition(
    priority = 0,                       # lower = dispatched earlier
    on_event = _my_on_event,            # (listener_instance, context, event) -> set | None
    before_modal_start = _my_on_start,  # optional: (listener_instance, context) -> None
    before_modal_end   = _my_on_end,    # optional: (listener_instance, context, reason) -> None
    ignore_mouse_click_events = False,
    ignore_mouse_move         = False,
    ignore_scroll_events      = False,
    ignore_keyboard_events    = False,
    ignore_window_events      = False,
)
```

## Public API — `RTC_Modal_Listener_Instance`

A `@dataclass` representing one block's live subscription. Managed by `Wrapper_Modal_Manager`.

| Field | Type | Description |
|---|---|---|
| `src_block_id` | `str` | Unique key — the subscribing block's id |
| `priority` | `int` | Dispatch order (ascending) |
| `is_enabled` | `bool` | Toggle on/off; synced from BL mirror on undo/redo |
| `event_count` | `int` | Events delivered since last rebuild |
| `last_return` | `str \| None` | Stringified last return value |
| `modal_start_timestamp` | `float` | Set at true router start |
| `last_event_timestamp` | `float` | Updated each delivered event |
| `listener_error_str` | `str \| None` | Last exception message; set + disables on crash |

## Downstream Block Integration Example

```python
# my_block/__init__.py

from ...native_blocks.block_modal_events.data_structures import Modal_Listener_Definition

def _on_modal_event(listener_instance, context, event):
    if event.type == 'G' and event.value == 'PRESS':
        # handle the key, consume the event
        return {'RUNNING_MODAL'}
    return {'PASS_THROUGH'}

def _before_modal_start(listener_instance, context):
    print("Modal router started — my listener is live")

def hook_get_modal_listener_definitions():
    return [
        Modal_Listener_Definition(
            priority = 10,
            on_event = _on_modal_event,
            before_modal_start = _before_modal_start,
            ignore_mouse_move = True,   # don't get spammed by MOUSEMOVE
        )
    ]
```

> **Note:** `block-modal-events` must be listed in your block's `_BLOCK_DEPENDENCIES` if you
> import its data structures or call `Wrapper_Modal_Manager`.

## Validation

`validate_listener_definitions()` in `helpers.py` runs before any RTC/bpy state is mutated:

1. At most **one** definition per block (the listener is keyed by `src_block_id`).
2. `on_event` is callable.

## Loggers

| Logger | Level | Usage |
|---|---|---|
| `MODAL_LIFECYCLE` | `INFO` | Router start/stop, rebuild/clear, start/end callbacks |
| `MODAL_EVENTS` | `INFO` | Per-event dispatch and per-listener `on_event` failures |

## Files

```text
block_modal_events/
├── __init__.py               # Block declaration, BL props, UIList, panel, update callbacks, hook_post_startup
├── README.md                 # This file
├── common_declarations.py    # Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_Data_Mirrors, Block_UIList_Configs
├── data_structures.py        # Modal_Event_Category, Modal_Listener_Definition, RTC_Modal_Listener_Instance
├── feature_modal_manager.py  # Wrapper_Modal_Manager (_update_RTC..., _update_BL..., public API)
├── helpers.py                # Router operator, event classification/dispatch, rebuild/clear, validation
└── ui.py                     # UIList row + details draw helpers
```
