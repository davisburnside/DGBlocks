````shell
You are assisting with **DGBlocks**, a modular block-based template for Blender addons. Each feature lives in a self-contained **block** folder. The main addon is primarily an ordered list of blocks to register.

# 1. PROJECT PURPOSE / BLOCK PHILOSOPHY
- **One block = one vertical feature slice:** bpy classes, properties, runtime data, loggers, hook contracts, UI, and registration live together.
- **Blocks are portable:** adding/removing a feature should usually mean adding/removing a folder plus its entry in `my_activated_blocks.py`.
- **Dependencies are one-directional:** if block A imports block B, B must be listed in A's `_BLOCK_DEPENDENCIES`, and B must not import A.
- **Communication is hook-based:** blocks should not directly call each other's behavior except through declared dependencies and public wrapper APIs.
- **Data management is explicit:** Blender data (BL) owns persistent truth; Runtime Cache (RTC) mirrors/transforms it for Python-only runtime use.

# 2. AI OPERATING CONTRACT
Before authoring or editing a block:
1. Inspect the target block and the closest canonical example/reference code first.
2. Identify the block's BL data, RTC data, hook sources/subscribers, loggers, dependencies, and registration lifecycle before changing code.
3. Prefer copying/extending an existing canonical pattern over inventing a new architecture.
4. Preserve architectural boundaries; do not weaken data rules to satisfy a local feature request.
5. Treat `unfinished_blocks/` as **read-only reference** unless explicitly told otherwise.
6. If docs disagree with current working reference code, current code wins; flag the mismatch.
7. For every change, review lifecycle, sync, imports, logging, and README/update notes.

# 3. SOURCE-OF-TRUTH PRECEDENCE
1. Current working code in canonical examples/reference blocks.
2. `Developer/AI_Assist/Memory_Bank/systemPatterns.md` and `blockAuthoringGuide.md`.
3. This summarized memory bank.
4. Older docs such as `Developer/Structural_Standards/Block_Structure_Overview.md`.

Do **not** propagate older names such as `Block_Hooks` or `Block_Runtime_Cache_Members`; use `Block_Hook_Sources` and `Block_RTC_Members`.

# 4. REPOSITORY + BLOCK LAYOUT
```text
<addon_root>/
├── __init__.py                  # bl_info, addon register/unregister entry points
├── my_addon_config.py           # addon_name, addon_title, addon_bl_type_prefix, Documentation_URLs
├── my_activated_blocks.py       # _ordered_blocks_list — ordered block manifest
├── addon_helpers/               # Generic utilities; NEVER imports from any block
├── native_blocks/               # Blocks shipped with the template
│   ├── block_core/              # REQUIRED by every other block: RTC, Loggers, Hooks, Block Management
│   ├── _example_usecases/       # Authoritative scaffolding templates
│   └── block_<name>/
├── external_blocks/             # User/project-specific blocks; sibling of native_blocks
├── unfinished_blocks/           # WIP/stub blocks; read-only reference by default
└── Developer/                   # Docs, cheatsheets, Memory Bank
````

```text
block_<feature_name>/            # folder snake_case | _BLOCK_ID kebab-case: "block-feature-name"
├── __init__.py                  # _BLOCK_ID, _BLOCK_VERSION, _BLOCK_DEPENDENCIES, register_block(event), unregister_block(event)
├── constants.py                 # Declarative hook/logger/RTC contract enums
├── feature_<name>.py            # Optional: one Feature Wrapper Class (FWC) per file
├── helper_functions.py          # Optional: uilayout_* and op_* functions
└── README.md                    # Recommended for every non-trivial block
```

# 5. REFERENCE SOURCES / EXAMPLES

For scaffolding new blocks, copy the closest template under `native_blocks/_example_usecases/`:

| Example | Purpose | Key pattern | |---|---|---| | `_block_usecase_01_minimal` | Minimum viable block | Empty block registration, no features | | `_block_usecase_02_basic` | Standard wired block | Logger, RTC member, PropertyGroup, operator, panel, hooks | | `_block_usecase_02B_basic` | Full BL↔RTC mirror | Collection-backed data, `UIList`, two-way synchronizer, CRUD |

For framework internals and real-world patterns, inspect:

- `block_core/` — RTC, loggers, hooks, block management, lifecycle primitives.
- `block_debug_console_print/` — hook subscription and developer UI.
- `block_onscreen_drawing/` — many RTC instances and GPU/runtime resources.

# 6. DATA OWNERSHIP + BL↔RTC SYNC RULES

| Data kind | Store in | Rule | |---|---|---| | User-editable persistent primitive values | `bpy.props` on `bpy.types.Scene` PropertyGroups | BL is source of truth and saved in `.blend` | | Persistent collection records | `CollectionProperty` rows | Mirror to RTC via synchronizer | | Python callables, handlers, timers, GPU handles, registries | RTC only | Rebuild from BL after reload/register/undo/redo | | Blender datablock references | Store name/path/id, not object reference | Re-resolve when needed; never cache `bpy.types.ID` refs | | Addon-wide user config | `my_addon_config.py` | No DGBlocks imports | | Block contract IDs | `constants.py` enums | No string literals elsewhere |

Sync conventions:

- `Abstract_BL_RTC_List_Syncronizer` is used when RTC records mirror BL PropertyGroup/CollectionProperty data.
- `update_RTC_with_mirrored_BL_data(event)` rebuilds RTC from BL; __BL wins__ on register/load/undo/redo.
- `update_BL_with_mirrored_RTC_data(event)` pushes RTC changes to BL only for explicit RTC-driven workflows.
- Property update callbacks call `update_RTC_with_mirrored_BL_data(...)` only after guards pass.
- Guard callbacks with `is_bpy_ready()` and `Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(...)`.
- `PropertyGroup` has no group-level update callback; updates belong on individual properties.
- `CollectionProperty.add/remove/move` do __not__ fire collection update callbacks; sync from operator logic, sentinel props, or explicit synchronizer calls.

# 7. WRAPPER-RECORD PATTERN

__Wrapper / Manager:__ stateless, `@classmethod` only, owns behavior, reads/writes RTC records.

- Always inherits `Abstract_Feature_Wrapper`: `init_pre_bpy(event)`, `init_post_bpy(event)`, `destroy_wrapper(event)`.
- Also inherit `Abstract_Datawrapper_Instance_Manager` for multi-instance CRUD.
- Also inherit `Abstract_BL_RTC_List_Syncronizer` for BL↔RTC mirrored data.

__Record:__ `@dataclass`, data only, no manager logic, stored in RTC.

- Naming: `RTC_<Feature>_Instance` for records; `Wrapper_<Feature>` for managers.
- Internal/runtime-only fields should be `_prefixed` and usually `repr=False`.

# 8. DECLARATIVE CONSTANTS, ENUMS, HOOKS, LOGGERS, RTC

Each block declares its core contract __declaratively__ in `constants.py`. The three standard enums describe what the block publishes, logs, and stores without scattering magic strings through implementation files.

1. `Block_Hook_Sources` — `(hook_func_name, {kwarg_name: type})`; events this block publishes.
2. `Block_Logger_Definitions` — `(display_name, default_level)`; per-concern loggers.
3. `Block_RTC_Members` — `(cache_key, default_value)`; RTC slots for this block.

Rules:

- Enum member names are `SCREAMING_SNAKE_CASE`.
- Enum values are unique tuples; duplicate enum values alias in Python.
- Pass enum classes verbatim to `Wrapper_Control_Plane.create_instance(...)`.
- Use enum members for hook names, logger IDs, and RTC keys — __never string literals__.

Hook rules:

- Publisher: `Wrapper_Hooks.run_hooked_funcs(hook_func_name=Block_Hook_Sources.MY_EVENT, ...)`.
- Subscriber: top-level `hook_*` function in `__init__.py` matching the declared hook name.
- No manual subscriber registration; discovery is by name at block registration.
- Optional `@hook_data_filter(predicate)` can bypass subscribers conditionally.
- Core hooks include `hook_post_register_init`, `hook_core_event_undo`, `hook_core_event_redo`, `hook_block_registered`, `hook_block_unregistered`.

Logging rules:

- Use `get_logger(Block_Logger_Definitions.X)`; never `print()` in checked-in code.
- One logger per concern, not necessarily per file.
- Exceptions should be logged with `exc_info=True`.

# 9. REGISTRATION LIFECYCLE

Every block `__init__.py` defines:

```python
_BLOCK_ID = "block-example"
_BLOCK_VERSION = (0, 1, 0)
_BLOCK_DEPENDENCIES = ["block-core"]

def register_block(event: Enum_Sync_Events): ...
def unregister_block(event: Enum_Sync_Events): ...
```

`register_block(event)`:

1. Gets `block_module = get_self_block_module(block_manager_wrapper=Wrapper_Control_Plane)`.
2. Calls `Wrapper_Control_Plane.create_instance(event, block_module=..., block_bpy_types_classes=..., block_feature_wrapper_classes=..., block_hook_source_enums=..., block_RTC_member_enums=..., block_logger_enums=...)`.
3. Attaches block PropertyGroups to `bpy.types.Scene` with `PointerProperty` if needed.
4. `init_post_bpy(event)` is deferred until `bpy.context` is ready, then `hook_post_register_init` fires.

`unregister_block(event)`:

1. Destroys wrappers/runtime resources through block management.
2. Calls `Wrapper_Control_Plane.destroy_instance(event, block_id=_BLOCK_ID)`.
3. Deletes Scene properties with `hasattr(bpy.types.Scene, "...")` guards.

# 10. NAMING, IMPORT, UI, OPERATOR CONVENTIONS

| Category | Convention | |---|---| | Block folder | `block_<feature_name>` snake_case | | Block ID | `"block-feature-name"` kebab-case | | bpy classes | `<PREFIX>_PG_*`, `_OT_*`, `_PT_*`, `_UL_*`, `_MT_*`, `_UP_*`; prefix comes from `addon_bl_type_prefix` and is replaced for re-skinned addons | | Wrappers / records | `Wrapper_<Feature>` / `RTC_<Feature>_Instance` | | Private helpers | `_leading_underscore`, especially `_rtc_*` | | UI functions | `uilayout_*` / `ui_draw_*`; drawing logic lives in `helper_functions.py` | | Operator bodies | `op_*`; operators delegate real work to helper functions |

Import rules:

- Use relative imports within the addon.
- Standard library first, then addon-level, inter-block, intra-block sections.
- Never import a block not listed in `_BLOCK_DEPENDENCIES`.
- `__init__.py` should not own variables/functions sibling modules need to import; use `constants.py` or feature modules.
- `import bpy # type: ignore`; bpy property annotations also get `# type: ignore`.

Function verb semantics: `get_*` returns existing/None; `create_*` creates new; `set_*` upserts; `destroy_*` removes; `sync_*` / `update_*_with_mirrored_*` rebuilds one data layer from another; `hook_*` subscribes to hooks.

# 11. BLOCK AUTHORING CHECKLIST

For every new/updated block:

- [ ] Folder and `_BLOCK_ID` match via snake_case/kebab-case conversion.
- [ ] `_BLOCK_VERSION`, `_BLOCK_DEPENDENCIES`, `register_block(event)`, and `unregister_block(event)` exist.
- [ ] Dependencies are listed before inter-block imports; no circular dependencies.
- [ ] `constants.py` declaratively defines `Block_Hook_Sources`, `Block_Logger_Definitions`, and `Block_RTC_Members` when relevant.
- [ ] All wrappers inherit the correct abstract base classes.
- [ ] Persistent data lives in BL PropertyGroups; runtime-only data lives in RTC dataclasses.
- [ ] BL↔RTC mirrored data has guarded callbacks and synchronizer methods.
- [ ] Operators delegate to `op_*`; panels delegate to `uilayout_*` / `ui_draw_*`.
- [ ] No `print()`, no string hook/logger/RTC IDs, no cached Blender ID refs.
- [ ] README documents purpose, dependencies, hooks, public API, and data architecture.

# 12. DONE CRITERIA / SMOKE-TEST EXPECTATIONS

A block change is not complete until reviewed for:

- registration/unregistration lifecycle symmetry
- runtime enable/disable safety
- dependency order in `my_activated_blocks.py`
- BL↔RTC sync on register/load/undo/redo where applicable
- guarded property update callbacks and no re-entrant sync loops
- logger usage and exception logging
- no forbidden imports, stale enum names, or cached Blender ID refs
- human-readable RTC records for debug-console-print inspection
- README/update notes if public behavior changed

Expected Blender smoke test when possible:

1. Reload scripts or restart Blender.
2. Confirm block registration logs start/end without tracebacks.
3. Verify declared loggers/hooks/RTC slots appear in core/debug tooling.
4. Disable and re-enable the block at runtime without errors.
5. For mirrored data, verify BL edits update RTC and undo/redo re-syncs correctly.

# 13. CRITICAL FORBIDDEN ACTIONS

- Do not modify files in `unfinished_blocks/` unless explicitly instructed; use them only as reference.
- Do not import from another block unless listed in `_BLOCK_DEPENDENCIES`.
- Do not use `magic string` literals for hook names, RTC keys, or logger IDs outside enums.
- Do not use `print()` for diagnostics; use loggers.
- Do not cache `bpy.types.ID` objects in RTC; cache names/paths and re-resolve.
- Do not register bpy classes outside `Wrapper_Control_Plane` / `_block_classes_to_register` flow.
- Do not let wrapper exceptions escape into Blender event callbacks; log and degrade except during registration, where block management handles failures.
- Do not silently catch `Exception`; always log at minimum. '@ | Set-Content -Path 'Developer/AI_Assist/Summarized_Memory_Bank.md' -Encoding UTF8"
