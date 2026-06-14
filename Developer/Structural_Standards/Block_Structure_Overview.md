
# Blender Addon Architecture Patterns — Comprehensive Analysis

> **Source-of-truth precedence:** current working code in reference blocks > this document.
> If any example in this file disagrees with the actual source, the code wins. Update the doc.

Note that any instance of "DGBLOCKS", in any capitalisation, is replaced with your own addon's
prefix (the value of `addon_bl_type_prefix` in `addon_config/static_settings.py`) in the final
export step.

---

## 1. FILE ORGANIZATION & NAMING

### Repository Layout

```
<addon_root>/
├── __init__.py                  # bl_info, addon register/unregister entry points
├── addon_config/                # addon_name, addon_title, addon_bl_type_prefix, Documentation_URLs, static_settings
├── addon_helpers/               # Generic utilities; NEVER imports from any block
│   └── data_structures.py       # All shared abstract classes and declaration dataclasses live here
├── native_blocks/               # Blocks shipped with the template
│   ├── block_core/              # REQUIRED by every other block
│   └── block_<name>/
├── unfinished_blocks/           # WIP/stub blocks — read-only reference by default
└── Developer/                   # Docs, cheatsheets, Memory Bank
```

### Block Folder Layout

```
block_<feature_name>/
├── __init__.py          # _BLOCK_DECLARATION, register_block_props(), unregister_block_props()
├── constants.py         # Block_Hook_Sources, Block_Loggers, Block_RTC_Members, Block_Data_Mirrors
├── feature_<name>.py    # One Feature Wrapper Class (FWC) per file
├── helper_functions.py  # uilayout_* and op_* helpers (optional)
└── README.md            # Recommended for every non-trivial block
```

These are suggestions, not hard rules. Blocks with many features may use subfolders (see
`block_core/core_features/` for a real example of this).

### `block_core` Internal Structure

`block_core` is the most complex block and uses a nested layout. Other blocks should not mirror
this verbatim, but it serves as the authoritative example for how to organise large blocks.

```
block_core/
├── __init__.py
├── core_features/
│   ├── control_plane/      # Wrapper_Control_Plane — addon lifecycle & block registry
│   │   ├── feature_wrapper.py
│   │   ├── data_structures.py
│   │   ├── helpers.py
│   │   ├── app_handlers.py  # bpy.app.handlers callbacks (load_post, undo, redo, depsgraph)
│   │   ├── msgbus.py
│   │   └── ui.py
│   ├── hooks/              # Wrapper_Hooks — hook source/subscriber registry
│   │   ├── feature_wrapper.py
│   │   ├── data_structures.py
│   │   └── ui.py
│   ├── loggers/            # Wrapper_Loggers — per-concern logger registry
│   │   ├── feature_wrapper.py
│   │   ├── data_structures.py
│   │   └── ui.py
│   └── runtime_cache/      # Wrapper_Runtime_Cache — thread-safe Python-only cache
│       ├── feature_wrapper.py
│       └── data_sync_tools.py
└── core_helpers/
    ├── constants.py        # Core_Block_Hook_Sources, Core_Block_Loggers, Core_Runtime_Cache_Members, Core_Data_Mirrors
    ├── props.py            # DGBLOCKS_PG_Core_Props (scene PropertyGroup)
    ├── ops.py              # Core operators
    └── ui.py               # Core panel
```

### Naming Conventions

- **Block folders**: `block_<feature_name>` snake_case
- **Block IDs**: kebab-case: `"block-stable-timers"`, `"block-core"`
- **Files**: snake_case: `constants.py`, `feature_draw_handler_manager.py`
- **bpy classes** (prefix comes from `addon_bl_type_prefix`):
  - `DGBLOCKS_PG_*` — PropertyGroups
  - `DGBLOCKS_OT_*` — Operators
  - `DGBLOCKS_PT_*` — Panels
  - `DGBLOCKS_UL_*` — UILists
  - `DGBLOCKS_UP_*` — AddonPreferences
- **Feature Wrapper Classes (FWCs)**: `Wrapper_<Feature>` — e.g. `Wrapper_Draw_Handlers`
- **RTC record dataclasses**: `RTC_<Feature>_Instance` — e.g. `RTC_Draw_Handler_Instance`
- **Functions**: snake_case — `register_block_props()`, `get_logger()`
- **Hook functions**: named exactly after the hook source member: `hook_post_startup`, `hook_draw_event`
- **Private/internal**: leading underscore: `_rtc_get_all()`, `_callback_load_post()`
- **Constants**: SCREAMING_SNAKE_CASE: `_BLOCK_ID`, `_BLOCK_VERSION`

---

## 2. COMMENT & DOCUMENTATION STYLES

### Banner Comments (Section Separators)

```python
#================================================================================
# MAJOR SECTION NAME
#================================================================================

# ------------------------------------------------------------
# Subsection name
# ------------------------------------------------------------
```

**Rules:**
- Major sections: 80 `=` characters
- Subsections: 60 `-` characters
- ALL CAPS for major sections, Sentence case for subsections
- Always blank line before/after

### Docstrings

Comprehensive docstrings for wrapper classes and complex functions:

```python
class Wrapper_Draw_Handlers(Abstract_Feature_Wrapper):
    """
    Manages a fixed set of toggleable members with BL ↔ RTC sync.
    No instance creation/destruction — all members exist at dev time.
    """
```

**Inline comments** explain non-obvious logic:

```python
# Re-entrancy guard
if instance.is_currently_running:
    instance.count_bypass_via_status += 1
    continue
```

### Documentation Headers

Functions document: purpose, args (with types), returns, and side effects.

---

## 3. IMPORT ORGANIZATION

**Strict three-tier hierarchy** with visual separators:

```python
# Standard library (no separator)
import sys
import threading

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Block_Declaration, Enum_Sync_Events

# --------------------------------------------------------------
# Inter-block imports (from other blocks)
# --------------------------------------------------------------
from ..block_core.core_features.loggers.feature_wrapper import get_logger
from ..block_core.core_features.runtime_cache.feature_wrapper import Wrapper_Runtime_Cache

# --------------------------------------------------------------
# Intra-block imports (same block, other files)
# --------------------------------------------------------------
from .constants import Block_Loggers, Block_RTC_Members
from .feature_draw_handler_manager import Wrapper_Draw_Handlers
```

**Rules:**
1. Standard library first (no separator)
2. Addon-level, then inter-block, then intra-block — each with a separator
3. Relative imports always within the addon
4. `import bpy # type: ignore` to suppress type-checker warnings
5. Never import from a block not listed in `_BLOCK_DEPENDENCIES`

---

## 4. CONSTANTS & DECLARATION DATACLASSES

### Declaration Dataclasses (defined in `addon_helpers/data_structures.py`)

All constants values use typed **declaration dataclasses** — not raw tuples:

| Dataclass | Used for | Key fields |
|---|---|---|
| `Logger_Declaration(default_level)` | Each logger | `default_level: str` |
| `Hook_Source_Declaration(arg_types)` | Each hook source | `arg_types: dict[str, any]` |
| `RTC_Member_Declaration(default_value)` | Each RTC slot | `default_value: any` (defaults to `[]`) |
| `RTC_Member_Data_Mirror_Declaration(...)` | BL↔RTC sync links | see §9 below |

### `String_Comparable_Mixin`

All three standard constants classes (and Data Mirrors) inherit from `String_Comparable_Mixin`,
a custom Enum subclass defined in `addon_helpers/data_structures.py`. It makes enum members
compare equal to their `.name` as a plain string, which lets the framework resolve enum members
to their string key without explicit `.name` calls.

### The Three Standard Constants Classes

Defined in each block's `constants.py`:

**1. `Block_Hook_Sources`** — hook events this block publishes

```python
class Block_Hook_Sources(String_Comparable_Mixin):
    # Member name IS the hook function name that subscriber blocks must implement
    hook_draw_event = Hook_Source_Declaration({"draw_handler_instance": any})
    hook_post_startup = Hook_Source_Declaration()  # no args
```

**2. `Block_Loggers`** — per-concern loggers

```python
class Block_Loggers(String_Comparable_Mixin):
    DRAWHANDLER_LIFECYCLE = Logger_Declaration("DEBUG")
    SHADER_BATCH_EVENTS   = Logger_Declaration("DEBUG")
```

**3. `Block_RTC_Members`** — runtime cache slots

```python
class Block_RTC_Members(String_Comparable_Mixin):
    DRAW_PHASES = RTC_Member_Declaration({})   # default value is empty dict
    SHADERS     = RTC_Member_Declaration({})
```

**Pattern notes:**
- Member **names** are used as RTC keys and logger names (autocomplete-friendly, no magic strings)
- Member **values** are typed declaration dataclasses (not tuples)
- `String_Comparable_Mixin` lets `key == "DRAW_PHASES"` work, avoiding `.name` everywhere

### Block Metadata (Always at top of `__init__.py`)

```python
_BLOCK_ID = "block-onscreen-drawing"
_BLOCK_VERSION = (1, 0, 0)
_BLOCK_DEPENDENCIES = ["block-core"]
```

---

## 5. ARCHITECTURE PATTERNS

### Feature Wrapper Classes (FWCs)

Every feature is packaged in a single **Feature Wrapper Class** (FWC). All FWCs inherit
`Abstract_Feature_Wrapper`. They may also inherit one or both of the two optional abstract classes:

```python
class Abstract_Feature_Wrapper(ABC):
    @classmethod
    @abstractmethod
    def _init_wrapper(cls) -> bool:
        """Called during block registration. No extra arguments."""
        ...

    @classmethod
    @abstractmethod
    def _remove_wrapper(cls):
        """Called during block unregistration. No extra arguments."""
        ...
```

> **Note:** The old two-phase `init_pre_bpy` / `init_post_bpy` pattern no longer exists.
> There is a single `_init_wrapper()`. The addon-wide post-bpy deferred init is handled
> exclusively by `Wrapper_Control_Plane.init_post_bpy()` via app-timer and `load_post` handlers.

**Optional abstract extensions:**

```python
class Abstract_Datawrapper_Instance_Manager(ABC):
    # For FWCs that manage 0-to-many instances of a @dataclass
    def _create_instance(cls, event: Enum_Sync_Events, **kwargs) -> any: ...
    def _remove_instance(cls, event: Enum_Sync_Events, **kwargs): ...

class Abstract_BL_RTC_List_Syncronizer(ABC):
    # Required when the FWC has at least one Data Mirror (see §9)
    def _update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events): ...
    def _update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events): ...
```

### Wrapper + RTC Record Pattern

**Manager-Record separation:**

- **Wrapper class** (`Wrapper_<Feature>`): stateless, `@classmethod` only, owns all behavior,
  reads/writes RTC record dataclasses.
- **RTC record dataclass** (`RTC_<Feature>_Instance`): data only, no logic, stored in RTC.

```python
@dataclass
class RTC_Draw_Handler_Instance:
    """Record — instance state only, no manager logic."""
    draw_phase_name: str
    region_name: str
    groups_to_shaders_map: defaultdict[list]
    _optional_draw_callback: Callable = field(default=None, repr=False)
    _generated_handle: Callable = field(init=False, default=None, repr=False)

class Wrapper_Draw_Handlers(Abstract_Feature_Wrapper):
    """Manager — classmethods only, no instance state."""

    @classmethod
    def _init_wrapper(cls) -> bool:
        # Creates RTC_Draw_Handler_Instance entries in RTC at startup
        ...

    @classmethod
    def enable_draw_handler(cls, draw_phase_name: str, ...):
        draw_handler_instance = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)[draw_phase_name]
        ...
```

**Key insight:** All instance data lives in a `@dataclass` stored in the RTC. The wrapper
class itself holds no state.

---

## 6. BLOCK DECLARATION & REGISTRATION LIFECYCLE

### `Block_Declaration` Dataclass

Every `__init__.py` creates a single `_BLOCK_DECLARATION` at module level that bundles all
block metadata. This replaces the old `register_block_components()` helper function pattern.

```python
_BLOCK_DECLARATION = Block_Declaration(
    block_module = sys.modules[__name__],        # this __init__.py file
    block_id = "block-onscreen-drawing",
    block_dependencies = ["block-core"],
    block_bpy_classes = [DGBLOCKS_PT_Debug_Drawing_Panel],
    block_feature_wrapper_classes = [Wrapper_Draw_Handlers],
    block_RTC_members = Block_RTC_Members,
    block_loggers = Block_Loggers,
    block_hook_sources = Block_Hook_Sources,     # optional
    block_data_mirrors = Block_Data_Mirrors,     # optional
)
```

Fields that are not relevant to a given block can be omitted (they default to empty).

### `register_block_props` / `unregister_block_props`

The only explicit functions remaining in `__init__.py`. Called by the addon's top-level
`register()` to attach / detach scene `PointerProperty` objects:

```python
def register_block_props():
    bpy.types.Scene.dgblocks_my_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_My_Props)

def unregister_block_props():
    if hasattr(bpy.types.Scene, "dgblocks_my_props"):
        del bpy.types.Scene.dgblocks_my_props
```

### `Wrapper_Control_Plane` — Central Lifecycle Manager

`Wrapper_Control_Plane` is the FWC that drives the entire addon lifecycle:

1. **`_init_wrapper()`** (called during addon `register()`):
   - Writes initial `Global_Addon_State` to RTC
   - Installs all `bpy.app.handlers` (load_post, undo_post, redo_post, depsgraph_update_post)
   - Schedules deferred `init_post_bpy()` via `bpy.app.timers`

2. **`init_post_bpy()`** (deferred, called once bpy context is ready):
   - Calls `_init_wrapper()` on all other registered FWCs
   - Runs two-pass BL↔RTC data mirror sync
   - Fires `hook_post_startup` to all subscriber blocks
   - Sets `ADDON_METADATA.POST_REG_INIT_HAS_RUN = True`

3. **`_create_instance(event, block_module)`**:
   - Reads `block_module._BLOCK_DECLARATION`
   - Registers bpy classes, FWC classes, RTC members, loggers, hook sources, data mirrors

4. **`_remove_instance(event, block_id)`**:
   - Removes bpy classes, FWC instances, RTC members for the given block

---

## 7. DATA STORAGE ARCHITECTURE

### Two-Tier Data System

| Layer | Description |
|---|---|
| **Blender Scene Properties** | Persistent (saved in `.blend`). User-editable. Attached to `bpy.types.Scene` via `PointerProperty`. Source of truth for all user-visible data. |
| **Runtime Cache (RTC)** | Transient (lost on reload/unregister). Stores Python callables, dataclass instances, GPU handles, block registries. Thread-safe dict managed by `Wrapper_Runtime_Cache`. |

### RTC Access Pattern

```python
# Get a cache slot by enum member
all_handlers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)

# Set a cache slot
Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, all_handlers)
```

`get_actual_rtc_key(key)` resolves an enum member to its `.name` string automatically,
so enum members can be passed directly.

---

## 8. LOGGING PATTERNS

### Logger Access

```python
logger = get_logger(Block_Loggers.DRAWHANDLER_LIFECYCLE)
```

### Log Level Usage

- **DEBUG**: Detailed flow tracing
- **INFO**: Significant state changes
- **WARNING**: Recoverable issues
- **ERROR**: Failures (`exc_info=True` always)
- **CRITICAL**: Unrecoverable failures

### Conventions

- Use `get_logger(...)` always — never `print()` in checked-in code
- Log at entry/exit of lifecycle methods
- Include identifiers in messages: `f"Draw handler '{draw_phase_name}' enabled"`
- Use verb prefixes: "Running", "Finished", "Skipping", "Removing", "Enabling", "Disabling"

---

## 9. HOOK SYSTEM PATTERNS

### Publishing a Hook (Source Block)

Declare in `constants.py`. **The member name is the hook function name:**

```python
class Block_Hook_Sources(String_Comparable_Mixin):
    hook_draw_event = Hook_Source_Declaration({"draw_handler_instance": any})
```

Publish (fire) the hook from within the source block:

```python
Wrapper_Hooks.run_hooked_funcs(
    hook_func_name = Block_Hook_Sources.hook_draw_event,
    should_halt_on_exception = False,
    draw_handler_instance = draw_handler_instance,
)
```

### Subscribing to a Hook (Subscriber Block)

Implement a **top-level function** in `__init__.py` whose name exactly matches the hook member
name. No explicit subscription registration is needed — discovery is by name at block registration:

```python
def hook_draw_event(draw_handler_instance):
    """Called by block_onscreen_drawing on every draw tick."""
    ...
```

### Core Hooks (from `block_core`)

| Hook | Fires when |
|---|---|
| `hook_post_startup` | Once, after addon is fully initialised and bpy context is ready |
| `hook_core_event_undo` | After Blender processes an undo |
| `hook_core_event_redo` | After Blender processes a redo |
| `SCENE_MONITOR_ACTIVE_SCENE_CHANGED` | Active scene changes (depsgraph) |
| `SCENE_MONITOR_ACTIVE_WORKSPACE_CHANGED` | Active workspace changes |
| `SCENE_MONITOR_ACTIVE_MODE_CHANGED` | Active mode (OBJECT, EDIT…) changes |
| `SCENE_MONITOR_ACTIVE_OBJ_CHANGED` | Active object changes |

### `@hook_data_filter` Decorator

Optional predicate attached to a subscriber hook function. Evaluated before the hook is called;
if it returns `False`, the call is skipped and counted as `bypass-via-data-filter`:

```python
@hook_data_filter(lambda hook_metadata, context, **_: context.scene.my_props.is_enabled)
def hook_post_startup():
    # Only runs when is_enabled is True
    pass
```

---

## 10. DATA MIRRORS (BL ↔ RTC SYNC)

Data mirrors formally link a Blender `CollectionProperty` to an RTC list, and drive automatic
bidirectional sync on init / undo / redo.

### Declaration (in `constants.py`)

```python
class Block_Data_Mirrors(String_Comparable_Mixin):
    MY_LIST = RTC_Member_Data_Mirror_Declaration(
        RTC_key = "MY_RTC_KEY",           # must match a Block_RTC_Members member name
        FWC_name = "Wrapper_MyFeature",   # class name of the owning FWC (as string)
        mirrored_key_field_names = ["id_field"],         # unique identity fields
        mirrored_data_field_names = ["editable_field"],  # fields synced between layers
        default_data_path_in_scene = "dgblocks_my_props.my_collection",  # dotted scene path
    )
```

### Default vs. Custom Sync

- If **`default_data_path_in_scene` is set**: `Wrapper_Runtime_Cache.resync_data_mirrors()`
  handles both directions automatically using the declared field names.
- If **`default_data_path_in_scene` is `None`**: the owning FWC **must** implement both
  `_update_RTC_with_mirrored_BL_data(event)` and `_update_BL_with_mirrored_RTC_data(event)`.
  Both functions must be present; the framework will call them during sync events.

### Sync Triggers

`Wrapper_Runtime_Cache.resync_data_mirrors(event, BL_is_truth_source)` is called:
- During addon init (twice: once RTC→BL, once BL→RTC)
- On every undo / redo via `bpy.app.handlers`

### Property Update Callback Guard

Property update callbacks that trigger a sync must guard against re-entrant loops:

```python
def _my_update_callback(self, context):
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(Block_RTC_Members.MY_RTC_KEY):
        return
    Wrapper_Runtime_Cache.resync_data_mirrors(Enum_Sync_Events.PROPERTY_UPDATE, BL_is_truth_source=True, ...)
```

---

## 11. UI PATTERNS

### Panel Header

```python
def draw_header(self, context):
    ui_draw_block_panel_header(
        context,
        self.layout,
        _BLOCK_DECLARATION.block_id,
        Documentation_URLs.MY_PLACEHOLDER_URL,
        icon_name = "FILE_3D"
    )
```

### UI Drawing Separation

Drawing logic lives in `helper_functions.py` (or a dedicated helper module); the panel
class only delegates:

```python
# helper_functions.py
def uilayout_draw_debug_settings(context, container):
    """All drawing logic lives here."""
    ...

# __init__.py
def draw(self, context):
    uilayout_draw_debug_settings(context, self.layout)
```

### Operator Execution Separation

Same pattern for operators:

```python
# helper_functions.py
def op_my_action(context):
    ...
    return {'FINISHED'}

# __init__.py
def execute(self, context):
    return op_my_action(context)
```

---

## 12. ERROR HANDLING PATTERNS

### Try-Except-Finally for Cleanup

```python
try:
    result = instance.actual_function(**kwargs)
    instance.count_hook_propagate_success += 1
except Exception as e:
    instance.count_hook_propagate_failure += 1
    logger.error(f"Exception in hook '{hook_func_name}'", exc_info=True)
    if should_halt_on_exception:
        raise e
finally:
    instance.is_currently_running = False
```

### Graceful Degradation

```python
if draw_handler_instance._generated_handle is None:
    logger.warning("Draw handler already disabled, returning with no action")
    return
```

### Defensive Programming

```python
if not hasattr(bpy.types.Scene, "dgblocks_my_props"):
    logger.warning("Scene has no my_props")
    return

if hasattr(bpy.types.Scene, "dgblocks_my_props"):
    del bpy.types.Scene.dgblocks_my_props
```

---

## 13. NAMING SEMANTICS

### Verb Conventions

| Prefix | Meaning |
|---|---|
| `get_*` | Retrieve existing value; return `None` if missing |
| `create_*` | Create new instance; fail/warn if already exists |
| `set_*` | Upsert (create or overwrite) |
| `destroy_*` | Remove instance or tear down wrapper |
| `_init_wrapper` | One-time setup during block registration |
| `_remove_wrapper` | Complete teardown during block unregistration |
| `_update_RTC_with_mirrored_BL_data` | Rebuild RTC from BL (BL is source of truth) |
| `_update_BL_with_mirrored_RTC_data` | Push RTC data into BL |
| `enable_` / `disable_` | Toggle without destroying |
| `register_*` / `unregister_*` | Blender registry operations |
| `hook_*` | Top-level subscriber hook function in `__init__.py` |
| `_callback_*` | `bpy.app.handlers` or timer callbacks |

### Prefix Conventions

| Prefix | Used for |
|---|---|
| `_rtc_` | Private RTC helper functions |
| `hook_` | Hook subscriber functions (also hook source member names) |
| `uilayout_` / `ui_draw_` | UI drawing functions in `helper_functions.py` |
| `op_` | Operator execution logic in `helper_functions.py` |
| `RTC_` | RTC record dataclasses |
| `Wrapper_` | Feature Wrapper Classes |

---

## 14. TYPE HINTS & ANNOTATIONS

### Function Signatures

```python
@classmethod
def enable_draw_handler(
    cls,
    draw_phase_name: str,
    region_name: str = "WINDOW",
    draw_callback: Optional[Callable] = None,
) -> None:
```

### Blender Property Annotations

```python
is_enabled: bpy.props.BoolProperty(default=True)  # type: ignore
```

### Dataclass Field Annotations

```python
@dataclass
class RTC_Draw_Handler_Instance:
    draw_phase_name: str
    region_name: str
    groups_to_shaders_map: defaultdict[list]

    # Private fields: excluded from repr, not set via __init__
    _generated_handle: Callable = field(init=False, default=None, repr=False)
```

---

## 15. REGISTRATION CHECKLIST (per block)

- [ ] `_BLOCK_ID`, `_BLOCK_VERSION`, `_BLOCK_DEPENDENCIES` defined
- [ ] `_BLOCK_DECLARATION` created with `Block_Declaration(...)`
- [ ] `register_block_props()` and `unregister_block_props()` defined if block has Scene properties
- [ ] All bpy classes listed in `block_bpy_classes`
- [ ] All FWCs listed in `block_feature_wrapper_classes`
- [ ] `constants.py` declares `Block_Hook_Sources`, `Block_Loggers`, `Block_RTC_Members` (and `Block_Data_Mirrors`) using `String_Comparable_Mixin` and typed declaration dataclasses
- [ ] If block has Data Mirrors with `default_data_path_in_scene=None`, the FWC implements both `_update_RTC_with_mirrored_BL_data` and `_update_BL_with_mirrored_RTC_data`
- [ ] No `print()`, no magic string literals for hook/logger/RTC IDs
- [ ] Dependent blocks listed in `_BLOCK_DEPENDENCIES` before any inter-block imports

---

## Summary: Key Architectural Principles

1. **Separation of Concerns**: UI, logic, data storage in separate files
2. **`Block_Declaration`**: Single declarative object bundles all block metadata; no manual register/unregister helper calls
3. **Typed Declarations**: `Hook_Source_Declaration`, `Logger_Declaration`, `RTC_Member_Declaration` replace raw tuples in enums
4. **Manager-Record Pattern**: `Wrapper_*` classes manage; `RTC_*_Instance` dataclasses hold state
5. **Two-Tier Data**: Scene PropertyGroups (persistent) ↔ RTC (transient) with Data Mirror sync
6. **Hook-Based Communication**: Blocks communicate via named hook functions, not direct calls
7. **Single init**: `_init_wrapper()` replaces the old two-phase `init_pre_bpy` / `init_post_bpy`
8. **Graceful Degradation**: Defensive checks, structured logging, early returns
9. **Lifecycle Discipline**: `Wrapper_Control_Plane` drives all init/destroy sequencing
10. **Consistency**: Naming, structure, patterns repeated across all blocks
