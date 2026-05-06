# DGBlocks — Technical Context

> The "what's actually installed and used" reference. Companion to
> `systemPatterns.md` (which covers *how* the code is shaped) and
> `projectBrief.md` (which covers *why*).

---

## 1. Runtime Requirements

| | Required | Notes |
|---|---|---|
| Blender | **5.0+** | `bl_info.blender = (5, 0, 0)`. Some APIs (`gpu.shader.from_builtin`, draw-handler signatures) target 4.x+ shape. |
| Python | **3.10+** | Bundled with Blender. We use `match`, parameterized generics in annotations, `StrEnum`. |
| OS | Cross-platform | Tested primarily on Windows 10. |

External pip libraries are **never** required for the template itself. Optional
features (Numba acceleration, etc.) are gated behind blocks like
`block_pip_library_manager` so the addon can start with no installs.

---

## 2. Standard Library Usage

| Module | Used for |
|---|---|
| `dataclasses` | All RTC `Record` types; see Wrapper-Record pattern |
| `enum` (`Enum`, `StrEnum`, `auto`) | The three standard block enums + many internal config enums |
| `typing` (`Optional`, `Callable`, `Type`, `Any`, `Dict`, `List`) | All public signatures |
| `abc` | `Abstract_Feature_Wrapper` and friends |
| `threading` | RTC's atomic locks |
| `logging` | Backbone of the per-block logger system |
| `importlib` | Recursive reload at top of `__init__.py` |
| `inspect` | Validating FWC abstract-method coverage |
| `collections` (`defaultdict`, `OrderedDict`) | Group maps, table-builder ordering |
| `datetime` | Timestamps in hook metadata |
| `os`, `sys` | Filesystem paths, `sys.dont_write_bytecode` |

`numpy` is used inside `block_onscreen_drawing` (shader vertex/index buffers).
It is bundled with Blender, so importing it is safe.

---

## 3. Blender APIs Touched

| Area | What we use it for |
|---|---|
| `bpy.types.PropertyGroup` | Persistent per-scene state per block |
| `bpy.props.*` | All persistent fields. `# type: ignore` always. |
| `bpy.types.{Operator, Panel, UIList, AddonPreferences, Menu}` | Per the prefix table in `systemPatterns.md` §4.4 |
| `bpy.app.handlers.{load_post, undo_post, redo_post}` | Lifecycle hooks consolidated in core-block |
| `bpy.app.timers` | Deferred post-bpy init when `load_post` doesn't fire |
| `bpy.utils.{register_class, unregister_class}` | Always called from `Wrapper_Block_Management` |
| `bpy.types.SpaceView3D.draw_handler_add/remove` | Onscreen drawing block |
| `gpu`, `gpu_extras.batch.batch_for_shader`, `mathutils` | Shader feature only |

**Never used** (intentionally):
- `bpy.ops.*` from non-Operator code paths. Direct API access only.
- `eval`/`exec` of user content.
- The pre-4.2 Extension manifest format (we ship as a classic addon).

---

## 4. Project Layout (file roles)

```
__init__.py                    bl_info, recursive reload, register/unregister
my_addon_config.py             addon_name, addon_title, addon_bl_type_prefix,
                               Documentation_URLs, Global_Tag_Ids, hotkey list,
                               UI sizing constants
my_activated_blocks.py         _ordered_blocks_list — the addon's "block manifest"

addon_helpers/
  data_structures.py           Global_Addon_State, Enum_Sync_Events, Enum_Sync_Actions,
                               Enum_Log_Levels, Abstract_Feature_Wrapper,
                               Abstract_BL_and_RTC_Data_Syncronizer,
                               Abstract_Datawrapper_Instance_Manager
  data_tools.py                fast_deepcopy_with_fallback, propertygroup utilities,
                               CSV-string parsers used by debug filters
  generic_helpers.py           clear_console, force_reload_all_scripts,
                               force_redraw_ui, is_bpy_ready,
                               get_self_block_module, get_names_of_parent_classes
  ui_drawing_helpers.py        ui_draw_block_panel_header, ui_draw_list_headers,
                               create_ui_box_with_header, uilayout_section_separator

native_blocks/
  block_core/
    __init__.py                Owns DGBLOCKS_PG_Core_Props (the master settings PG),
                               common operators (open_help_page, copy_to_clipboard,
                               force_reload_scripts), DGBLOCKS_UP_Core_Preferences
    core_helpers/
      constants.py             Core_Block_Loggers, Core_Block_Hook_Sources,
                               Core_Runtime_Cache_Members
      helper_datasync.py       update_dataclasses_to_match_collectionprop,
                               update_collectionprop_to_match_dataclasses
      helper_uilayouts.py      uilayout_draw_core_block_settings, draw_wrapped_text_v2
      helper_generalized_deptree_solver.py    Block dependency graph evaluator
    core_features/
      feature_runtime_cache.py     Wrapper_Runtime_Cache (thread-safe, atomic dict)
      feature_logs.py              Wrapper_Loggers, get_logger, DGBLOCKS_PG_Logger_Instance
      feature_hooks.py             Wrapper_Hooks, run_hooked_funcs, hook_data_filter
      feature_block_manager.py     Wrapper_Block_Management, RTC_Block_Instance,
                                   load/undo/redo callbacks
  block_debug_console_print/   Pretty-prints any block's state via hook
  block_onscreen_drawing/      Draw handlers + GPU shader manager
  block_pip_library_manager/   (in progress) pip install/uninstall + dependency tracking
  block_stable_modal/          (in progress) reentrant modal operator wrapper
  block_timers/                (in progress) bpy.app.timer wrapper

unfinished_blocks/             Held out of _ordered_blocks_list. WIP.
external_blocks/               (Optional) blocks pulled from other repos.

Developer/
  AI_Assist/
    README.md                  Memory Bank index
    Memory_Bank/               You are here.
  Cheatsheets/                 Topic-specific notes (Blender property update
                               callbacks, threading, data persistence, git)
  Structural_Standards/
    Block_Structure_Overview.md    Older long-form architecture doc;
                                   superseded by systemPatterns.md but kept
                                   as a deeper reference.
```

---

## 5. Key Subsystems by Owner Block

| Subsystem | Owner | Public API |
|---|---|---|
| Logging | `block-core` | `get_logger(enum)` → wrapped `logging.Logger` |
| Runtime Cache | `block-core` | `Wrapper_Runtime_Cache.{get_cache, set_cache, create_cache, remove_cache, flag_cache_as_syncing, ...}` |
| Hook dispatch | `block-core` | `Wrapper_Hooks.run_hooked_funcs(...)`, `@hook_data_filter` |
| Block lifecycle | `block-core` | `Wrapper_Block_Management.{create_instance, destroy_instance, ...}` |
| BL↔RTC sync helpers | `block-core` | `update_dataclasses_to_match_collectionprop`, `update_collectionprop_to_match_dataclasses` |
| Pretty-print debugging | `block-debug-console-print` | The `DGBLOCKS_OT_Debug_Console_Print_Block_Diagnostics` operator + `make_pretty_json_string_from_data` |
| GPU draw + shaders | `block-onscreen-drawing` | `Wrapper_Draw_Handlers.{enable_draw_handler, disable_draw_handler, add_shader}`, `Shader_Instance` |

---

## 6. Configuration Surface

End-users / addon re-skinners only need to touch four things:

1. `__init__.py` → `bl_info` (name, author, description, version, doc_url).
2. `my_addon_config.py` → `addon_name`, `addon_title`, `addon_bl_type_prefix`,
   `Documentation_URLs`, hotkey list.
3. `my_activated_blocks.py` → `_ordered_blocks_list`.
4. The **folder name** `DGBlocks` (or whatever the cwd is) — Blender uses
   the package name to disambiguate addons.

Anything inside `addon_helpers/` or `native_blocks/` should be treated as
"library code" and not edited per-project. Project-specific logic is always added as new blocks under /external_blocks (encouraged to use separate git repos for each block)

---

## 7. Threading Model

- **`Wrapper_Runtime_Cache`** uses a `threading.Lock` per cache member to make
  reads/writes atomic. Get/set ops are therefore safe from any thread.
- **Blender's main thread** is the only thread allowed to touch `bpy.*`. RTC
  *reads* from a worker thread are fine; mutations of Blender data must marshal
  back to the main thread (typically via `bpy.app.timers.register(...)` with a
  short `first_interval`).
- See `Developer/Cheatsheets/Threading.md` for the long-form discussion.

---

## 8. Persistence Model

- **Saved with the .blend file:** Anything stored on a `bpy.props`-backed
  PropertyGroup attached to `Scene`, `Object`, etc. Survives close/reopen,
  copies into appended scenes, ties into Blender undo/redo.
- **Saved with Blender (not the file):** `AddonPreferences`. Survives across
  files but is per-user-per-machine.
- **Not saved:** RTC contents. Always rebuilt from BL on register/load.
- See `Developer/Cheatsheets/Data_Persistence.md`.

---

## 9. Development Workflow

1. **Edit code.**
2. **Reload** in Blender via `bpy.ops.script.reload()` (often hotkeyed to
   `Ctrl+R` via `addon_hotkeys` in `my_addon_config.py`). The recursive
   reloader at the top of the main `__init__.py` ensures sub-modules refresh.
3. **Toggle a logger to DEBUG** via the dev panel (Block Core → Loggers UIList)
   to inspect the path you're working on.
4. **Use the Debug Console-Print panel** (Hook Subscribers table, RTC dump,
   Scene-Property dump) to verify state at any moment.
5. **Set breakpoints** in your IDE or inject `breakpoint()` calls; wrappers
   are stateless so call stacks stay shallow.

---

## 10. Versioning

- `_BLOCK_VERSION` per block uses SemVer `(MAJOR, MINOR, PATCH)`.
- `bl_info["version"]` in the main `__init__.py` is the addon-wide version,
  independent of any block.
- No formal compatibility guarantees yet — the template is pre-1.0. Breaking
  changes are tracked in `progress.md` / `activeContext.md`.
