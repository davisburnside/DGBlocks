# block_core

## Block Dependencies
- None (block_core has no dependencies — it is the foundation for all other blocks)

## External Dependencies
- None (standard library only)

## Purpose

`block_core` provides the fundamental infrastructure required by every other block:

- **Control Plane** — Addon lifecycle management, block registry, FWC orchestration
- **Runtime Cache (RTC)** — Thread-safe, transient Python data store
- **Loggers** — Per-concern logger registry with adjustable log levels
- **Hooks** — Hook source/subscriber system for decoupled inter-block communication
- **Scene Monitor** — Depsgraph-driven context tracking (scene, workspace, mode, active object)

---

## File Structure

```
block_core/
├── __init__.py                 # _BLOCK_DECLARATION, register_block_props(), unregister_block_props()
├── core_features/
│   ├── control_plane/          # Wrapper_Control_Plane — addon lifecycle & block registry
│   │   ├── feature_wrapper.py  # Wrapper_Control_Plane class
│   │   ├── data_structures.py  # RTC_Block_Instance dataclass
│   │   ├── helpers.py          # Internal helpers for create/destroy block instances
│   │   ├── app_handlers.py     # bpy.app.handlers callbacks (load_post, undo, redo, depsgraph)
│   │   ├── msgbus.py           # msgbus scene-change subscriptions
│   │   └── ui.py               # DGBLOCKS_UL_Blocks UIList
│   ├── hooks/                  # Wrapper_Hooks — hook source/subscriber registry
│   │   ├── feature_wrapper.py  # Wrapper_Hooks class + hook_data_filter decorator
│   │   ├── data_structures.py  # RTC_Hook_Source_Instance, RTC_Hook_Subscriber_Instance, DGBLOCKS_PG_Hook_Reference
│   │   └── ui.py               # DGBLOCKS_UL_Hooks UIList
│   ├── loggers/                # Wrapper_Loggers — per-concern logger registry
│   │   ├── feature_wrapper.py  # Wrapper_Loggers class + get_logger() convenience function
│   │   ├── data_structures.py  # RTC_Logger_Instance, DGBLOCKS_PG_Logger_Instance
│   │   └── ui.py               # DGBLOCKS_UL_Loggers UIList
│   └── runtime_cache/          # Wrapper_Runtime_Cache — thread-safe Python-only cache
│       ├── feature_wrapper.py  # Wrapper_Runtime_Cache class + get_actual_rtc_key()
│       └── data_sync_tools.py  # Default BL↔RTC mirror sync logic
└── core_helpers/
    ├── constants.py            # Core_Block_Hook_Sources, Core_Block_Loggers,
    │                           # Core_Runtime_Cache_Members, Core_Data_Mirrors
    ├── props.py                # DGBLOCKS_PG_Core_Props (scene PropertyGroup)
    ├── ops.py                  # Core operators (reload, clipboard copy, cache debug, etc.)
    └── ui.py                   # DGBLOCKS_PT_Core_Block_Panel
```

---

## Key Feature Wrappers

### `Wrapper_Control_Plane`
Central lifecycle manager for the entire addon. Drives block registration, FWC orchestration,
data mirror sync, and fires lifecycle hooks.

- `init_wrapper()` — Installs `bpy.app.handlers` (load_post, undo_post, redo_post,
  depsgraph_update_post) and schedules deferred `init_post_bpy()` via `bpy.app.timers`.
- `init_post_bpy()` — Called once bpy context is ready. Calls `init_wrapper()` on all
  other FWCs, runs the two-pass BL↔RTC data mirror sync, fires `hook_post_startup`.
- `create_instance(event, block_module)` — Reads `block_module._BLOCK_DECLARATION` and
  registers the block's bpy classes, FWCs, RTC members, loggers, hook sources, and data mirrors.
- `destroy_instance(event, block_id)` — Unregisters all of the above for the named block.

### `Wrapper_Runtime_Cache`
Thread-safe (RLock) in-memory dictionary. All transient addon data lives here.

- `get_cache(key)` / `set_cache(key, value)` — Primary access methods. Accepts enum members
  directly via `get_actual_rtc_key()`.
- `resync_data_mirrors(event, BL_is_truth_source)` — Iterates all registered Data Mirrors and
  triggers the appropriate sync direction.
- `is_cache_flagged_as_syncing(key)` / `flag_cache_as_syncing(key, bool)` — Re-entrancy guard
  for property update callbacks.

### `Wrapper_Loggers`
Registry of Python `logging.Logger` instances, one per declared logger.

- `get_logger(logger_id)` — Public convenience function. Returns the logger for the given
  enum member (or a fallback logger if the RTC is not yet initialised).
- `create_instance(event, logger_name, src_block_id, level_name)` — Creates and caches a new logger.

### `Wrapper_Hooks`
Registry of hook sources and their discovered subscriber functions.

- `create_instance(event, src_block_id, hook_func_name, hook_func_named_args)` — Registers a
  new hook source in RTC.
- `rebuild_hook_subs_cache()` — Scans all registered block modules for top-level functions
  whose names match declared hook source member names. Called once during `init_post_bpy()`.
- `run_hooked_funcs(hook_func_name, ...)` — Fires a hook to all subscriber blocks. Handles
  re-entrancy protection, rate limiting, `@hook_data_filter` predicates, and execution timing.

---

## Constants (`core_helpers/constants.py`)

### `Core_Block_Loggers`
| Member | Default Level |
|---|---|
| `HOOKS` | INFO |
| `BLOCK_MGMT` | DEBUG |
| `RTC_DATA_SYNC` | DEBUG |
| `REGISTRATE` | DEBUG |
| `POST_REGISTRATE` | DEBUG |
| `UI` | WARNING |
| `TRACKED_DATABLOCK_TYPES` | DEBUG |
| `SCENE_MONITOR` | DEBUG |

### `Core_Block_Hook_Sources`
| Member (= hook function name) | Kwargs |
|---|---|
| `hook_post_startup` | _(none)_ |
| `hook_core_event_undo` | _(none)_ |
| `hook_core_event_redo` | _(none)_ |
| `SCENE_MONITOR_ACTIVE_SCENE_CHANGED` | `old_id: tuple`, `new_id: tuple` |
| `SCENE_MONITOR_ACTIVE_WORKSPACE_CHANGED` | `old_id: tuple`, `new_id: tuple` |
| `SCENE_MONITOR_ACTIVE_MODE_CHANGED` | `old_id: tuple`, `new_id: tuple` |
| `SCENE_MONITOR_ACTIVE_OBJ_CHANGED` | `old_id: tuple`, `new_id: tuple` |

### `Core_Runtime_Cache_Members`
| Member | Default Value | Purpose |
|---|---|---|
| `ADDON_METADATA` | `Global_Addon_State()` | Addon-wide state flags and context trackers |
| `REGISTRY_ALL_BLOCKS` | `[]` | All registered `RTC_Block_Instance` records |
| `REGISTRY_ALL_FWCS` | `[]` | All registered `RTC_FWC_Instance` records |
| `REGISTRY_ALL_HOOK_SOURCES` | `[]` | All registered `RTC_Hook_Source_Instance` records |
| `REGISTRY_ALL_HOOK_SUBSCRIBERS` | `{}` | Dict of `hook_func_name → [RTC_Hook_Subscriber_Instance]` |
| `REGISTRY_ALL_LOGGERS` | `[]` | All registered `RTC_Logger_Instance` records |
| `REGISTRY_ALL_DATA_MIRRORS` | `[]` | All registered `RTC_FWC_Data_Mirror_Instance` records |
| `META_REGISTRIES_BEING_SYNCED` | `[]` | List of cache keys currently mid-sync (re-entrancy guard) |

### `Core_Data_Mirrors`
| Member | RTC Key | Scene Path | Purpose |
|---|---|---|---|
| `HOOKS_LIST` | `REGISTRY_ALL_HOOK_SOURCES` | `dgblocks_core_props.managed_hooks` | Persists hook enabled/disabled state |
| `LOGGERS_LIST` | `REGISTRY_ALL_LOGGERS` | `dgblocks_core_props.managed_loggers` | Persists logger level settings |

---

## Scene Properties (`DGBLOCKS_PG_Core_Props`)

Attached to `bpy.types.Scene.dgblocks_core_props`:

| Property | Type | Purpose |
|---|---|---|
| `addon_is_active` | BoolProperty | Master enable/disable switch |
| `documentation_weblinks_enabled` | BoolProperty | Show `[?]` help buttons |
| `debug_mode_enabled` | BoolProperty | Show extra debug UI |
| `debug_log_all_RTC_BL_sync_actions` | BoolProperty | Verbose sync logging |
| `debug_clear_BL_data_on_startup` | BoolProperty | Clear CollectionProps on each startup |
| `managed_hooks` | CollectionProperty | Mirrors `REGISTRY_ALL_HOOK_SOURCES` |
| `managed_loggers` | CollectionProperty | Mirrors `REGISTRY_ALL_LOGGERS` |

---

## Hook Subscriptions This Block Implements

| Hook function | Source block | Purpose |
|---|---|---|
| `hook_debug_get_state_data_to_print` | `block_debug_console_print` | Returns RTC state data for console printing |
| `hook_debug_uilayout_draw_console_print_settings` | `block_debug_console_print` | Draws block-specific debug UI inside the console-print panel |

---

## Public API

```python
# Logging
from .core_features.loggers.feature_wrapper import get_logger
logger = get_logger(Core_Block_Loggers.BLOCK_MGMT)

# Runtime Cache
from .core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache
value = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.MY_KEY)
Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.MY_KEY, value)

# Hooks
from .core_features.hooks.feature_wrapper import Wrapper_Hooks, hook_data_filter
Wrapper_Hooks.run_hooked_funcs(hook_func_name=Block_Hook_Sources.hook_post_startup)

# Control Plane
from .core_features.control_plane.feature_wrapper import Wrapper_Control_Plane
Wrapper_Control_Plane.create_instance(event, block_module=sys.modules[__name__])
Wrapper_Control_Plane.destroy_instance(event, block_id="block-my-feature")
```

---

## Usage Notes

- `block_core` is required by every other block and must always be the first block registered.
- Never remove `block_core` from the active-blocks manifest.
- The `Wrapper_Control_Plane.init_post_bpy()` deferred init runs once per Blender session
  (guarded by `ADDON_METADATA.POST_REG_INIT_HAS_RUN`). It re-runs on file-open events.
- `Wrapper_Runtime_Cache` data does not survive Blender reload/restart. BL properties
  (via Data Mirrors) are the persistence mechanism for any data that must survive.
