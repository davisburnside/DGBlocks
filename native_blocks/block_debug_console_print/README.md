# block_debug_console_print

**Block ID:** `block-debug-console-print`

## Purpose

Provides a Blender 3D View side-panel that collects structured state data from other blocks
and pretty-prints it to the system console. Any block can opt in to diagnostics by subscribing
to the hook sources declared here. The panel exposes filter controls (dict-key filtering,
numerical value filtering, structural truncation) so developers can zero in on relevant data
without drowning in noise.

## Dependencies

| Block | Reason |
|---|---|
| `block-core` | Hooks (`Wrapper_Hooks`), runtime cache (`Wrapper_Runtime_Cache`), loggers, core helpers |

## Data Architecture

### Blender Data (source of truth)

| PropertyGroup | Scene path | Purpose |
|---|---|---|
| `DGBLOCKS_PG_Debug_Props_Profile` | `bpy.types.Scene.dgblocks_debug_console_print_props` | Persistent user settings: clear-on-print, min-verbosity, JSON indent, dict-key filters, numeric filters, structural truncation, table sort-order |

### Runtime Cache

None. This block owns no RTC members.

### Data Mirrors

None.

## Hook Sources

This block **declares** the following hook sources. Subscriber blocks implement matching
top-level functions in their `__init__.py` to provide data or UI for the debug panel.

| Hook member | Fires when | Extra kwargs |
|---|---|---|
| `hook_debug_get_state_data_to_print` | The "Print Block Diagnostics" operator executes | `other_input: str` |
| `hook_debug_uilayout_draw_console_print_settings` | The debugging panel redraws | `ui_container: bpy.types.UILayout` |

### `hook_debug_get_state_data_to_print`

Subscribers return an arbitrary Python object (dict, list, dataclass, etc.). The operator
collects all subscriber results, applies the active filters, converts to pretty JSON, and calls
`print()`.

```python
# Example subscriber implementation (in another block's __init__.py):
def hook_debug_get_state_data_to_print(other_input: str) -> dict:
    return {"my_feature": {"active": True, "count": 42}}
```

### `hook_debug_uilayout_draw_console_print_settings`

Subscribers draw their own per-block debug settings directly into a panel body. Only blocks
that also subscribe to `hook_debug_get_state_data_to_print` will have their settings drawn.

```python
# Example subscriber implementation:
def hook_debug_uilayout_draw_console_print_settings(ui_container: bpy.types.UILayout):
    ui_container.label(text="My Feature Debug Options")
    ui_container.prop(scene.my_props, "some_debug_flag")
```

## Public API

### Operator

| Class | bl_idname | Description |
|---|---|---|
| `DGBLOCKS_OT_Debug_Console_Print_Block_Diagnostics` | `dgblocks.debug_console_print_block_diagnostics` | Collects data from all subscriber blocks, applies filters, prints to console |

**Operator inputs:**
- `source_block_id: str` — the specific block to query (passed to `run_hooked_funcs`)
- `other_input: str` — arbitrary string forwarded to each subscriber's hook

### Panel

`DGBLOCKS_PT_Debugging_Panel` appears in the 3D Viewport side panel under the addon's tab.
It contains:

1. **Filter settings** (collapsible panels):
   - General: clear console toggle, min-verbosity, JSON indent size, memory-address display, data-type display
   - Dict-key filtering: comma-separated wildcard strings for inclusion/exclusion, applied to leaf, branch, or all nodes
   - Data filtering: max rows per container, max search depth, numerical value filters (`>`, `>=`, `==`, `!=`, `<=`, `<`)

2. **Per-subscriber-block debug settings** — populated dynamically via `hook_debug_uilayout_draw_console_print_settings`

### Helper Functions

| Function | Location | Purpose |
|---|---|---|
| `ui_draw_filter_settings()` | `helpers/ui.py` | Draws filter controls into a layout |
| `uilayout_draw_debug_settings()` | `helpers/ui.py` | Iterates subscribers and calls their hook-drawn settings |

## Loggers

None declared by this block.

## Files

```
block_debug_console_print/
├── __init__.py              # Block declaration, bpy classes, register/unregister
├── README.md                # This file
└── helpers/
    ├── constants.py         # Block_Hook_Sources, filter enum items
    └── ui.py                # uilayout_draw_debug_settings, ui_draw_filter_settings