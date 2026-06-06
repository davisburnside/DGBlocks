You are assisting with **DGBlocks**, a modular block-based template for Blender addons.
Each feature lives in a self-contained **block** folder. The main addon is an ordered list
of blocks to register.

# 1. PROJECT PURPOSE / BLOCK PHILOSOPHY

- **One block = one vertical feature slice:** bpy classes, properties, runtime data, loggers,
  hook contracts, UI, and registration live together.
- **Blocks are portable:** adding/removing a feature means adding/removing a folder plus its
  entry in the active-blocks manifest.
- **Dependencies are one-directional:** if block A imports block B, B must be listed in A's
  `_BLOCK_DEPENDENCIES`, and B must not import A.
- **Communication is hook-based:** blocks should not directly call each other's behavior except
  through declared dependencies and public wrapper APIs.
- **Data management is explicit:** Blender data (BL) owns persistent truth; Runtime Cache (RTC)
  mirrors/transforms it for Python-only runtime use.

# 2. AI OPERATING CONTRACT

Before authoring or editing a block:
1. Inspect the target block and the closest canonical example/reference code first.
2. Identify the block's BL data, RTC data, hook sources/subscribers, loggers, dependencies,
   and registration lifecycle before changing code.
3. Prefer copying/extending an existing canonical pattern over inventing a new architecture.
4. Preserve architectural boundaries; do not weaken data rules to satisfy a local feature request.
5. Treat `unfinished_blocks/` as **read-only reference** unless explicitly told otherwise.
6. If docs disagree with current working reference code, current code wins; flag the mismatch.
7. For every change, review lifecycle, sync, imports, logging, and README/update notes.

# 3. SOURCE-OF-TRUTH PRECEDENCE

1. Current working code in canonical examples/reference blocks.
2. `Developer/Structural_Standards/Block_Structure_Overview.md`
3. This summarized memory bank.
4. `Developer/AI_Assist/Memory_Bank/` files.

# 4. REPOSITORY + BLOCK LAYOUT

```text
<addon_root>/
├── __init__.py                  # bl_info, addon register/unregister entry points
├── addon_config/                # addon_name, addon_title, addon_bl_type_prefix, Documentation_URLs
├── addon_helpers/               # Generic utilities; NEVER imports from any block
│   └── data_structures.py       # All shared abstract classes & declaration dataclasses
├── native_blocks/
│   ├── block_core/              # REQUIRED by every other block
│   └── block_<name>/
├── unfinished_blocks/           # WIP/stub blocks; read-only reference by default
└── Developer/                   # Docs, cheatsheets, Memory Bank
```

```text
block_<feature_name>/
├── __init__.py          # _BLOCK_ID, _BLOCK_VERSION, _BLOCK_DEPENDENCIES,
│                        # _BLOCK_DECLARATION, register_block_props(), unregister_block_props()
├── constants.py         # Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_Data_Mirrors
├── feature_<name>.py    # One Feature Wrapper Class (FWC) per file
├── helper_functions.py  # uilayout_* and op_* helpers (optional)
└── README.md
```

# 5. BLOCK DECLARATION — THE CORE REGISTRATION PATTERN

Every `__init__.py` defines a `_BLOCK_DECLARATION` dataclass. There are NO `register_block()`
/ `unregister_block()` functions. `Wrapper_Control_Plane` reads the declaration automatically.

```python
_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__],
    block_id = "block-my-feature",
    block_dependencies = ["block-core"],
    block_bpy_classes = [DGBLOCKS_PT_My_Panel, DGBLOCKS_OT_My_Op],
    block_feature_wrapper_classes = [Wrapper_My_Feature],
    block_loggers = Block_Loggers,
    block_hook_sources = Block_Hook_Sources,   # optional
    block_RTC_members = Block_RTC_Members,     # optional
    block_data_mirrors = Block_Data_Mirrors,   # optional
)

def register_block_props():
    bpy.types.Scene.dgblocks_my_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_My_Props)

def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_my_props"):
        del bpy.types.Scene.dgblocks_my_props
```

# 6. CONSTANTS — DECLARATION DATACLASSES + String_Comparable_Mixin

All three standard constants classes inherit `String_Comparable_Mixin` (a custom Enum mixin
from `addon_helpers/data_structures.py`). Member **names** are used as keys; member **values**
are typed declaration dataclasses — NOT raw tuples.

```python
from addon_helpers.data_structures import (
    String_Comparable_Mixin,
    Hook_Source_Declaration,
    Logger_Declaration,
    RTC_Member_Declaration,
    RTC_Member_Data_Mirror_Declaration,
)

class Block_Hook_Sources(String_Comparable_Mixin):
    # Member name IS the hook function name subscribers must implement
    hook_draw_event   = Hook_Source_Declaration({"draw_handler_instance": any})
    hook_post_startup = Hook_Source_Declaration()   # no kwargs

class Block_Loggers(String_Comparable_Mixin):
    DRAWHANDLER_LIFECYCLE = Logger_Declaration("DEBUG")
    SHADER_BATCH_EVENTS   = Logger_Declaration("DEBUG")

class Block_RTC_Members(String_Comparable_Mixin):
    DRAW_PHASES = RTC_Member_Declaration({})   # default value = empty dict
    SHADERS     = RTC_Member_Declaration({})   # default value = empty dict
```

`String_Comparable_Mixin.__eq__` makes `Block_RTC_Members.DRAW_PHASES == "DRAW_PHASES"` true,
so enum members can be passed directly to `get_cache()` / `set_cache()` without `.name`.

**Forbidden old names** (do NOT use):
- `Block_Hooks` → use `Block_Hook_Sources`
- `Block_Runtime_Cache_Members` → use `Block_RTC_Members`
- `Block_Logger_Definitions` → use `Block_Loggers`
- Raw tuple values like `= ("timer-exec", "INFO")` → use declaration dataclasses

# 7. FEATURE WRAPPER CLASSES (FWCs)

**Abstract base (all FWCs inherit this):**

```python
class Abstract_Feature_Wrapper(ABC):
    @classmethod @abstractmethod
    def init_wrapper(cls) -> bool: ...    # called during post-bpy registration phase

    @classmethod @abstractmethod
    def destroy_wrapper(cls): ...         # called during block unregistration — no extra args
```

> The old `init_pre_bpy` / `init_post_bpy` two-phase pattern is **gone**. There is one
> `init_wrapper()`. The addon-wide deferred post-bpy init is handled only by
> `Wrapper_Control_Plane.init_post_bpy()` via `bpy.app.timers` and `load_post` handlers.

**Optional extensions:**

```python
class Abstract_Datawrapper_Instance_Manager(ABC):
    # For FWCs managing 0-to-many @dataclass instances
    def create_instance(cls, event: Enum_Sync_Events, **kwargs) -> any: ...
    def destroy_instance(cls, event: Enum_Sync_Events, **kwargs): ...

class Abstract_BL_RTC_List_Syncronizer(ABC):
    # Required if the FWC has at least one Data Mirror
    def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events): ...
    def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events): ...
```

**Naming:** `Wrapper_<Feature>` for managers; `RTC_<Feature>_Instance` for record dataclasses.

# 8. WRAPPER_CONTROL_PLANE — CENTRAL LIFECYCLE MANAGER

`Wrapper_Control_Plane` (in `block_core/core_features/control_plane/`) drives the full addon lifecycle:

- `init_wrapper()` → installs `bpy.app.handlers`, schedules deferred `init_post_bpy()`
- `init_post_bpy()` → calls `init_wrapper()` on all other FWCs, runs 2-pass data mirror sync,
  fires `hook_post_startup`, sets `ADDON_METADATA.POST_REG_INIT_HAS_RUN = True`
- `create_instance(event, block_module)` → reads `_BLOCK_DECLARATION`, registers bpy classes,
  FWCs, RTC members, loggers, hook sources, data mirrors
- `destroy_instance(event, block_id)` → removes all of the above for the named block

# 9. DATA OWNERSHIP + BL↔RTC SYNC

| Data kind | Store in | Rule |
|---|---|---|
| User-editable persistent values | `bpy.props` on `bpy.types.Scene` PropertyGroups | BL is source of truth |
| Persistent collection records | `CollectionProperty` rows | Mirror to RTC via Data Mirror |
| Python callables, handles, registries | RTC only | Rebuild from BL after reload/register/undo/redo |
| Blender ID references | Store name/session_uid, not the object | Re-resolve when needed |
| Addon-wide config | `addon_config/` | No DGBlocks imports |
| Block contract IDs | `constants.py` enums | No string literals elsewhere |

**Sync conventions:**

- `Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source)` is called:
  - During addon init (twice: RTC→BL then BL→RTC)
  - On every undo / redo
- Property update callbacks that trigger sync must guard with
  `Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(cache_key)`.
- `CollectionProperty.add/remove/move` do **not** fire update callbacks; sync must be
  triggered explicitly from operator logic or sentinel properties.

# 10. DATA MIRRORS

A fourth optional constants class, `Block_Data_Mirrors`, formally links an RTC list to a
Blender `CollectionProperty` for automatic bidirectional sync.

```python
class Block_Data_Mirrors(String_Comparable_Mixin):
    MY_LIST = RTC_Member_Data_Mirror_Declaration(
        RTC_key = "MY_RTC_KEY",
        FWC_name = "Wrapper_MyFeature",
        mirrored_key_field_names = ["id_field"],
        mirrored_data_field_names = ["editable_field"],
        default_data_path_in_scene = "dgblocks_my_props.my_collection",
    )
```

- If **`default_data_path_in_scene` is set**: the framework handles both sync directions
  automatically.
- If **`default_data_path_in_scene` is `None`**: the owning FWC **must** implement both
  `update_RTC_with_mirrored_BL_data(event)` and `update_BL_with_mirrored_RTC_data(event)`.
  Both functions are required; the framework calls them during all sync events.

# 11. HOOK SYSTEM

**Source block** — declares in `constants.py`; fires via `Wrapper_Hooks.run_hooked_funcs`:

```python
# Declaration: member name IS the hook function name
class Block_Hook_Sources(String_Comparable_Mixin):
    hook_draw_event = Hook_Source_Declaration({"draw_handler_instance": any})

# Firing:
Wrapper_Hooks.run_hooked_funcs(
    hook_func_name = Block_Hook_Sources.hook_draw_event,
    should_halt_on_exception = False,
    draw_handler_instance = draw_handler_instance,
)
```

**Subscriber block** — top-level function in `__init__.py` whose name matches the hook member:

```python
def hook_draw_event(draw_handler_instance):
    ...
```

No manual subscription registration. Discovery is automatic at block registration time.

**Core hooks (from `block_core`):**

| Member name | Fires when |
|---|---|
| `hook_post_startup` | Once, after full addon init and bpy context ready |
| `hook_core_event_undo` | After Blender undo |
| `hook_core_event_redo` | After Blender redo |
| `SCENE_MONITOR_ACTIVE_SCENE_CHANGED` | Active scene changed (depsgraph) |
| `SCENE_MONITOR_ACTIVE_WORKSPACE_CHANGED` | Active workspace changed |
| `SCENE_MONITOR_ACTIVE_MODE_CHANGED` | Active mode changed |
| `SCENE_MONITOR_ACTIVE_OBJ_CHANGED` | Active object changed |

Optional `@hook_data_filter(predicate)` decorator skips the hook call when predicate returns `False`.

# 12. LOGGING

```python
logger = get_logger(Block_Loggers.MY_LOGGER)
logger.debug("Starting sync")
logger.error("Failed", exc_info=True)
```

- Always use `get_logger(...)`; never `print()` in checked-in code.
- One logger per concern.
- Always pass `exc_info=True` with exception logging.

# 13. NAMING CONVENTIONS

| Category | Convention |
|---|---|
| Block folder | `block_<feature_name>` snake_case |
| Block ID | `"block-feature-name"` kebab-case |
| bpy classes | `DGBLOCKS_PG_*`, `_OT_*`, `_PT_*`, `_UL_*`, `_UP_*` |
| FWC managers | `Wrapper_<Feature>` |
| RTC records | `RTC_<Feature>_Instance` |
| Private helpers | `_leading_underscore`, e.g. `_rtc_*`, `_callback_*` |
| UI functions | `uilayout_*` / `ui_draw_*` — live in `helper_functions.py` |
| Operator bodies | `op_*` — operators delegate to helper functions |
| Hook subscribers | `hook_<name>` — top-level in `__init__.py` |

**Verb semantics:** `get_*` returns existing/None; `create_*` creates; `set_*` upserts;
`destroy_*` removes; `init_wrapper` sets up; `destroy_wrapper` tears down;
`update_RTC_with_mirrored_BL_data` rebuilds RTC from BL; `update_BL_with_mirrored_RTC_data`
pushes RTC to BL; `enable_/disable_` toggles without destroying.

# 14. BLOCK AUTHORING CHECKLIST

- [ ] Folder name and `_BLOCK_ID` match (snake_case ↔ kebab-case).
- [ ] `_BLOCK_VERSION`, `_BLOCK_DEPENDENCIES`, `_BLOCK_DECLARATION` defined.
- [ ] `register_block_props()` / `unregister_block_props()` present if block has Scene props.
- [ ] `constants.py` uses `String_Comparable_Mixin` and typed declaration dataclasses.
- [ ] All FWCs inherit `Abstract_Feature_Wrapper`; optional ABCs inherited where appropriate.
- [ ] Data Mirrors with `default_data_path_in_scene=None` have both sync methods on the FWC.
- [ ] Persistent data in BL PropertyGroups; runtime-only data in RTC dataclasses.
- [ ] Property update callbacks guard against re-entrant sync with `is_cache_flagged_as_syncing`.
- [ ] Operators delegate to `op_*`; panels delegate to `uilayout_*` / `ui_draw_*`.
- [ ] No `print()`, no magic string literals, no cached Blender ID references.
- [ ] README documents purpose, dependencies, hooks, public API, data architecture.

# 15. CRITICAL FORBIDDEN ACTIONS

- Do not modify `unfinished_blocks/` unless explicitly instructed.
- Do not import from another block unless it is listed in `_BLOCK_DEPENDENCIES`.
- Do not use magic string literals for hook names, RTC keys, or logger IDs outside enums.
- Do not use `print()` for diagnostics — use loggers.
- Do not cache `bpy.types.ID` objects in RTC — cache names/session_uids and re-resolve.
- Do not register bpy classes outside the `_BLOCK_DECLARATION` / `Wrapper_Control_Plane` flow.
- Do not let wrapper exceptions escape into Blender event callbacks — log and degrade gracefully.
- Do not use the old enum names `Block_Hooks`, `Block_Runtime_Cache_Members`, or
  `Block_Logger_Definitions` — they no longer exist.
- Do not use the old two-phase init methods `init_pre_bpy` / `init_post_bpy` — use `init_wrapper`.
- Do not define `register_block(event)` / `unregister_block(event)` functions — use `_BLOCK_DECLARATION`.