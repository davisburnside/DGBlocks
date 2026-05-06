You are assisting with DGBlocks, a modular block-based template for Blender addons. Each feature lives in a self-contained "block" folder. The main addon is just an ordered list of blocks to register.

# DIRECTORY LAYOUT
```
<addon_root>/
├── __init__.py                  # bl_info, register/unregister entry points
├── my_addon_config.py           # addon_name, addon_title, addon_bl_type_prefix, Documentation_URLs
├── my_activated_blocks.py       # _ordered_blocks_list — the block manifest
├── addon_helpers/               # Generic utilities — NEVER imports from any block
│   ├── data_structures.py       # Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager,
│   │                            # Abstract_BL_and_RTC_Data_Syncronizer, Enum_Sync_Events
│   ├── data_tools.py
│   ├── generic_helpers.py       # is_bpy_ready(), get_self_block_module(), force_reload_all_scripts()
│   └── ui_drawing_helpers.py    # ui_draw_block_panel_header(), create_ui_box_with_header()
├── native_blocks/               # Blocks shipped with the template
│   ├── block_core/              # REQUIRED by every other block — provides RTC, Loggers, Hooks, Block Management
│   ├── block_debug_console_print/
│   ├── block_onscreen_drawing/
│   └── block_<name>/
├── external_blocks/             # User/project-specific blocks
└── unfinished_blocks/           # WIP blocks not in _ordered_blocks_list
```

# INDIVIDUAL BLOCK STRUCTURE
```
block_<feature_name>/            # folder: snake_case  |  _BLOCK_ID: kebab-case ("block-feature-name")
├── __init__.py                  # REQUIRED: _BLOCK_ID, _BLOCK_VERSION, _BLOCK_DEPENDENCIES, register_block(event), unregister_block(event)
├── constants.py                 # REQUIRED if block has any hooks/loggers/RTC members — holds the three standard enums
├── feature_<name>.py            # OPTIONAL: one Feature Wrapper Class (FWC) per file
├── helper_functions.py          # OPTIONAL: uilayout_* (UI drawing) and op_* (operator execution) functions
└── README.md
```

# TWO-TIER DATA MODEL
**Source of Truth** (persistent, saved in .blend):
- `bpy.props` PropertyGroups attached to `bpy.types.Scene`
- Holds user-editable, primitive-typed data only

**Runtime Cache (RTC)** (transient, lost on reload):
- `Wrapper_Runtime_Cache._cache` — thread-safe dict
- Holds Python-only data: `@dataclass` records, callables, registries
- Rebuilt from BL on register/load/undo/redo — BL always wins

Sync pattern: Property update callbacks call `update_RTC_with_mirrored_BL_data()`. Two-way sync for collection-backed data uses `Abstract_BL_and_RTC_Data_Syncronizer`.

# WRAPPER-RECORD PATTERN (dominant pattern)
**Wrapper (Manager):** `@classmethod` only, stateless. Reads/writes records via RTC.
- Inherits: `Abstract_Feature_Wrapper` (forces `init_pre_bpy`, `init_post_bpy`, `destroy_wrapper`)
- Optionally: `Abstract_Datawrapper_Instance_Manager` (CRUD for multi-instance features)
- Optionally: `Abstract_BL_and_RTC_Data_Syncronizer` (two-way BL↔RTC sync)

**Record (`@dataclass`):** Instance state only, no logic. Stored in RTC.
- Naming: `RTC_<Feature>_Instance` (record) / `Wrapper_<Feature>` (manager)

# THREE STANDARD ENUMS (in constants.py)
1. `Block_Hook_Sources` — `(hook_func_name, {kwarg_name: type})` — events this block publishes
2. `Block_Logger_Definitions` — `(display_name, default_level)` — per-concern loggers
3. `Block_RTC_Members` — `(cache_key, default_value)` — RTC slots for this block

All enum NAMES are `SCREAMING_SNAKE_CASE`. Values are unique tuples. These enums are passed verbatim to `Wrapper_Block_Management.create_instance()`.

# COMMUNICATION: HOOK SYSTEM
- **Publisher:** calls `Wrapper_Hooks.run_hooked_funcs(hook_func_name=Block_Hook_Sources.MY_EVENT, ...)`
- **Subscriber:** defines a top-level function matching the hook name in `__init__.py`
  - No registration needed — discovery is by name at block registration time
  - Optional `@hook_data_filter(predicate)` for conditional bypass
- No direct cross-block behavioral calls — hooks only

Core-block provides: `hook_post_register_init`, `hook_core_event_undo`, `hook_core_event_redo`, `hook_block_registered`, `hook_block_unregistered`

# REGISTRATION LIFECYCLE
**register_block(event: Enum_Sync_Events):**
1. Calls `Wrapper_Block_Management.create_instance(event, block_module, classes, enums...)` → Registers bpy classes, calls `init_pre_bpy()` on each FWC, creates RTC/loggers/hooks
2. Attaches PropertyGroup to `bpy.types.Scene` via `PointerProperty`

`init_post_bpy()` is deferred until `bpy.context` is ready (load_post handler or timer poll). Fires `hook_post_register_init` afterward.

**unregister_block(event: Enum_Sync_Events):**
1. Calls wrapper's `destroy_wrapper()` (clean up runtime resources)
2. Calls `Wrapper_Block_Management.destroy_instance(event, block_id=_BLOCK_ID)`
3. `del bpy.types.Scene.<prop>` (with `hasattr` guard)

All register/unregister accept `event: Enum_Sync_Events`.

# NAMING CONVENTIONS
| Category | Style | Example |
|---|---|---|
| Block ID | kebab-case string | `"block-example-name"` |
| Block folder | snake_case | `block_example_name` |
| bpy Classes | `DGBLOCKS_PG_*`, `_OT_*`, `_PT_*`, `_UL_*`, `_MT_*`, `_UP_*` | `DGBLOCKS_PG_Core_Props` |
| Functions | snake_case with semantic verbs | see below |
| Constants | SCREAMING_SNAKE_CASE | `_BLOCK_ID` |
| Private | `_leading_underscore` | `_rtc_get_all()` |

Function verb semantics:
- `get_*` → retrieve (None if missing)
- `create_*` → new (error if exists)
- `set_*` → upsert
- `destroy_*` → remove
- `sync_*` / `update_*_with_mirrored_*` → rebuild one layer from the other
- `register_*` / `unregister_*` → Blender class registry
- `hook_*` → subscriber callback
- `uilayout_*` → UI drawing
- `op_*` → operator execution body

# CORE WRAPPERS (all in block_core)
| Wrapper | Key Methods |
|---|---|
| `Wrapper_Runtime_Cache` | `get_cache(key)`, `set_cache(key, val)`, `create_cache(...)`, `flag_cache_as_syncing(...)` |
| `Wrapper_Loggers` / `get_logger(enum)` | per-concern `logging.Logger` |
| `Wrapper_Hooks` | `run_hooked_funcs(...)`, `@hook_data_filter` |
| `Wrapper_Block_Management` | `create_instance(...)`, `destroy_instance(...)`, `is_block_enabled(...)` |

# CRITICAL RULES
- `addon_helpers/` **NEVER** imports from any block. Blocks may import from it.
- A block imports from another block **ONLY** if listed in `_BLOCK_DEPENDENCIES`. No circular deps.
- Use enums for hook names, RTC keys, logger IDs — **NEVER** string literals.
- Use loggers, **NEVER** `print()`.
- Do **NOT** cache `bpy.types.ID` references in RTC. Cache names/paths and re-resolve.
- `__init__.py` should not own variables/functions sibling files need to import — use `constants.py`.
- Property `update=` callbacks must guard with `is_bpy_ready()` and syncing flag checks.