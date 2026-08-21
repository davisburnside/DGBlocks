# block_modal_events

**Block ID:** `block-modal-events`

## Purpose

Owns one Blender modal router and fans raw input events out to ordered logical listeners. Downstream
blocks declare listeners through `hook_get_modal_listener_definitions`; the block owns their RTC
records, per-listener enable toggles, dispatch order, crash isolation, and lifecycle notifications.

The block also owns an optional, RTC-only registry of toolbar `WorkSpaceTool`s. Tool declarations
are collected from downstream blocks during `hook_post_startup`. A logical declaration may
cover several editor/mode placements and is expanded to one concrete Blender tool per placement.

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Runtime cache, hooks, loggers, registration lifecycle |

Overlay drawing is not owned here. Use `block-onscreen-draw` for GPU overlays.

## Modal lifecycle

There is no master `enable_modal` property and no `_router_is_running` flag.

1. `Wrapper_Modal_Manager.repoll(event)` fires `hook_get_modal_listener_definitions` and rebuilds
   the RTC listener registry.
2. An unbound listener transition from none -> some invokes `DGBLOCKS_OT_Modal_Event_Router`.
3. Invocation uses a consistent `window/screen/VIEW_3D area/WINDOW region` context override. This
   is required when repoll is reached from a timer or `bpy.ops.dgblocks.reload_all_blocks()`.
4. A running router reads the listener registry live, so non-empty -> non-empty rebuilds do not
   restart it.
5. When no unbound listener remains, the raw router finishes. Tool-bound listeners continue
   independently through their active `WorkSpaceTool` keymaps.

Each router also retains the identity of the listener-list object it started with. Reload/file-load
recovery replaces that object; a stale pre-reload router detects the generation mismatch and exits
instead of dispatching alongside the replacement. This is not a global running-state flag.

Individual listeners may still be toggled with `listener_mirror[].is_enabled`. A disabled listener
remains registered, so disabling all listeners does not itself repoll or remove them.

### Listener return values

Listeners run in ascending `(priority, src_block_id)` order.

| Return | Behavior |
|---|---|
| `None` / `{'PASS_THROUGH'}` | Continue to the next listener |
| `{'RUNNING_MODAL'}` | Consume the event and short-circuit remaining listeners |
| `{'FINISHED'}` | Remove only the returning listener; do not repoll |
| `{'CANCELLED'}` | Remove only the returning listener; do not repoll |

After `FINISHED`/`CANCELLED`, the BL mirror is refreshed directly from RTC. The raw router ends when
no unbound listener remains; unrelated tool-bound listeners continue through their tool keymaps.

### Listener end reasons

`hook_modal_listener_ended(context, reason, listener_info)` is broadcast after a listener ends.
`listener_info` is an immutable `Modal_Listener_End_Info` snapshot; it does not expose the removed
mutable RTC record.

| Reason | Meaning |
|---|---|
| `FINISHED` | Listener returned `{'FINISHED'}` |
| `CANCELLED` | Listener returned `{'CANCELLED'}` |
| `DEFINITION_REMOVED` | A later repoll no longer returned that listener |
| `ROUTER_SHUTDOWN` | Router/reload preparation ended listeners |
| `ADDON_SHUTDOWN` | Block/add-on teardown ended listeners |

`before_modal_end(listener, context, reason)` runs before the broadcast for that listener.
`hook_modal_ended(context, reason)` remains a router-level notification.

### Crash isolation

An exception from `on_event` records `listener_error_str`, disables only that listener, and logs
the exception. Exceptions never escape the router callback.

## Listener declarations

Each downstream block may return at most one listener because `src_block_id` is the key.

```python
from ...native_blocks.block_modal_events.data_structures import Modal_Listener_Definition

def hook_get_modal_listener_definitions():
    return [Modal_Listener_Definition(
        priority=10,
        on_event=_on_modal_event,
        before_modal_start=_on_start,
        before_modal_end=_on_end,
        workspace_tool_ids=("flatypus.assembly_select",),
        ignore_scroll_events=True,
    )]
```

`workspace_tool_ids=()` means the listener is eligible regardless of the active custom tool.
Otherwise all IDs must resolve to preregistered logical tool declarations and the listener is
dispatched only while one of those logical tools is active. An unknown ID disables the listener
and records an error.

## Workspace tools

### Declaration hook

Downstream blocks should implement `hook_get_workspace_tool_definitions()`. The older
`hook_get_modal_workspace_tool_definitions()` name remains supported for compatibility:

```python
from ...native_blocks.block_modal_events.data_structures import (
    Workspace_Tool_Definition,
    Workspace_Tool_Placement,
    Workspace_Tool_Listener_Event,
)

def hook_get_workspace_tool_definitions():
    return [Workspace_Tool_Definition(
        tool_id="flatypus.assembly_select",
        label="Assembly Select",
        description="Select Flatypus assembly entities",
        image_icon_name="Flatypus Assembly Select Icon",
        icon="ops.generic.select",  # fallback
        placements=(
            Workspace_Tool_Placement("VIEW_3D", "OBJECT"),
            Workspace_Tool_Placement("VIEW_3D", "EDIT_MESH"),
        ),
        listener_events=(
            Workspace_Tool_Listener_Event("MOUSEMOVE"),
            Workspace_Tool_Listener_Event("LEFTMOUSE", "PRESS"),
        ),
        after=frozenset({"builtin.select_box"}),
        separator=True,
        group=True,
    )]
```

### Multiple modes and areas

A single **DGBlocks logical declaration** can contain multiple `placements`. Blender itself allows
only one scalar `bl_space_type` and `bl_context_mode` on each concrete `WorkSpaceTool`, so the
manager expands the logical declaration into one generated class per placement. Placement IDs are
deterministic, for example:

```text
flatypus.assembly_select.view_3d.object
flatypus.assembly_select.view_3d.edit_mesh
```

Use explicit placements. DGBlocks does not pass an `ALL` mode to Blender.

### Registration and persistence

- Tools are collected and registered during this block's `hook_post_startup`.
- Referenced operators have already been registered at that point.
- Registrations are stored in RTC member `WORKSPACE_TOOLS`.
- There is intentionally no Blender-data mirror or UIList for tools.
- Tools are unregistered before block reload and during wrapper removal.
- Tools remain registered while their runtime listeners are absent; an active dormant tool is
  harmless and is not automatically replaced with another user tool.

### Image datablock icons

`image_icon_name` refers to an existing `bpy.data.images` name. The manager gets a datablock icon
value through `bpy.types.UILayout.icon(image)` and bridges it into Blender's toolbar icon cache.
If the image is absent or has no usable icon, `icon` is used; the default fallback is
`ops.generic.select`.

The cache bridge is necessary because `WorkSpaceTool.bl_icon` publicly accepts only a Blender
toolbar `.dat` icon handle, not an Image datablock or integer `icon_value`.

```python
resolved_count = Wrapper_Modal_Manager.refresh_icons()
```

`refresh_icons()` retries every Image-backed tool, updates Blender's immutable toolbar `ToolDef`
records, redraws areas, and returns the number resolved.

### Tool-keymap listener forwarding

`listener_events` generates active-tool keymap entries for
`DGBLOCKS_OT_Workspace_Tool_Listener_Event`. This one-shot operator forwards the exact Blender-routed
event to listeners that reference the logical tool ID. Tool-bound listeners are skipped by the raw
modal router, preventing duplicate delivery.

Listener return translation for this one-shot operator is:

| Listener result | Keymap operator result |
|---|---|
| `PASS_THROUGH` / `None` | `PASS_THROUGH` |
| `RUNNING_MODAL` | `FINISHED` (consume this event; no modal handler is installed) |
| `FINISHED` / `CANCELLED` | Remove that listener, then `FINISHED` |

Blender 5 accepts `MOUSEMOVE` with value `ANY` in a tool keymap. It does not accept
`INBETWEEN_MOUSEMOVE` as a keymap event type, so tools should bind `MOUSEMOVE` only.

The normal `keymap` field remains independent and may contain arbitrary Blender operator entries.
A workspace tool therefore needs no modal listener: it may use only ordinary non-modal operators,
only `listener_events`, or both. `is_event_over_viewport()` remains a useful defensive check inside
viewport listeners/

### Programmatic activation

```python
Wrapper_Modal_Manager.activate_tool("flatypus.assembly_select", context)
```

This resolves the concrete placement for the current `(area.type, context.mode)` and activates it.
If the supplied context is not a 3D View, the API retries with a consistent 3D View `WINDOW`
override. It does not automatically restore the previously active tool on listener removal, and
it does not force the counterpart placement active after a later Object/Edit mode change; Blender
remembers an active tool separately per mode.

## Data architecture

### Blender data

| Path | Purpose |
|---|---|
| `scene.dgblocks_modal_events_props.listener_mirror` | Per-listener `is_enabled` persistence |
| `scene.dgblocks_modal_events_props.listener_mirror_selected_idx` | UIList selection |

### Runtime cache

| RTC key | Type | Purpose |
|---|---|---|
| `LISTENERS` | `list[RTC_Modal_Listener_Instance]` | Live ordered listeners |
| `USER_INPUT_CAPTURE` | `User_Input_Capture_Instance` | Latest raw event metadata |
| `WORKSPACE_TOOLS` | `list[RTC_Workspace_Tool_Instance]` | Concrete registered tool placements |

Only `LISTENERS` has a BL mirror, keyed by `src_block_id` and mirroring `is_enabled`.

## Public API

| Method | Description |
|---|---|
| `Wrapper_Modal_Manager.repoll(event)` | Rebuild listeners; activate raw router only when unbound listeners require it |
| `Wrapper_Modal_Manager.get_listener(src_block_id)` | Return one live listener or `None` |
| `Wrapper_Modal_Manager.refresh_icons()` | Retry Image-backed toolbar icons; return resolved count |
| `Wrapper_Modal_Manager.activate_tool(logical_tool_id, context)` | Activate the matching concrete placement |

## Startup and file load

Core's persistent `load_post` handler calls `Wrapper_Control_Plane.init_post_bpy()` after a
`.blend` load. The already-initialized branch reruns mirror sync and then fires `hook_post_startup`.
Modal events uses that pass to end any stale Python listeners with `ROUTER_SHUTDOWN`, recollect
tools (including Image icons from the newly loaded file), repoll listeners, and restart the router
under a valid 3D-view context override.

## Files

```text
block_modal_events/
├── __init__.py
├── common_declarations.py
├── data_structures.py
├── feature_modal_manager.py
├── helpers.py
├── modal_interaction.py
├── ui.py
├── workspace_tools.py
└── README.md
```