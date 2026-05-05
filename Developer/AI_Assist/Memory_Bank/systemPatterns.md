# DGBlocks — System Patterns

> The micro-to-macro standards reference. This is the file an AI assistant
> should be fed when authoring or editing block code. Examples are pulled
> verbatim from the three reference blocks: `block_core`,
> `block_debug_console_print`, and `block_onscreen_drawing`.

---

## 1. Repository Layout (Macro)

```
<addon_root>/
├── __init__.py                  # bl_info, register/unregister entry points
├── my_addon_config.py           # User-editable addon-wide config (no DGBlocks imports)
├── my_activated_blocks.py       # The ordered _ordered_blocks_list
├── addon_helpers/               # Generic helpers usable by any block (no block deps)
│   ├── data_structures.py       # Abstract_*_Wrapper, Enum_Sync_Events, Global_Addon_State
│   ├── data_tools.py
│   ├── generic_helpers.py
│   └── ui_drawing_helpers.py
├── native_blocks/               # Blocks shipped with this template
│   ├── block_core/              # Required by every other block
│   ├── block_debug_console_print/
│   ├── block_onscreen_drawing/
│   └── block_<name>/
├── external_blocks/             # Blocks pulled in from other repos / projects
├── unfinished_blocks/           # WIP blocks, not in _ordered_blocks_list
└── Developer/                   # Docs, cheatsheets, this Memory Bank
```

**Rules:**
- `addon_helpers/` may **never** import from any block. Blocks may import from it.
- `native_blocks/<block>/` may **never** be imported into `addon_helpers/`.
- A block may import from another block *only* if that other block is listed
  in its `_BLOCK_DEPENDENCIES`.
- `my_addon_config.py` and `my_activated_blocks.py` are the only files an
  end-user (re-skinning the template) is expected to edit.

---

## 2. Block Folder Layout (Macro)

```
block_<feature_name>/
├── __init__.py                  # REQUIRED — see §3
├── constants.py                 # REQUIRED if block has any Hook/Logger/RTC enums
├── helper_functions.py          # OPTIONAL — UI draw funcs, operator execute logic, formatting
├── feature_<name>.py            # OPTIONAL — one file per feature wrapper class
├── <subfeature>/                # OPTIONAL — sub-package for complex features
│   ├── __init__.py              # Often empty; see §6 on circular-dep avoidance
│   └── <module>.py
└── README.md                    # OPTIONAL but recommended; see §15
```

**Rules:**
- Block folder name uses `snake_case`: `block_onscreen_drawing`.
- Block ID uses `kebab-case`: `block-onscreen-drawing`.
- The folder name and the `_BLOCK_ID` should match (mod the dash/underscore swap).
- Files prefixed `feature_` host one major feature wrapper class each.
- Files prefixed `helper_` host pure functions — no bpy class registrations.

---

## 3. Required Contents of a Block's `__init__.py` (Macro)

Every block's `__init__.py` must define:

```python
_BLOCK_ID           = "block-<name>"        # kebab-case string, globally unique
_BLOCK_VERSION      = (1, 0, 0)             # SemVer tuple
_BLOCK_DEPENDENCIES = ["block-core", ...]   # List of other _BLOCK_IDs (kebab-case)

def register_block(event):    ...           # Sets up the block
def unregister_block(event):  ...           # Tears it down
```

`register_block` and `unregister_block` must accept a single positional arg
`event: Enum_Sync_Events`. Most of the time, that argument is just passed
through to `Wrapper_Block_Management.create_instance()` /
`destroy_instance()`.

Optional but commonly present:
- **Hook implementations** (functions named `hook_*`) — picked up by name.
- **Module-level lists** — `_block_classes_to_register`,
  `_feature_wrapper_classes_to_register`. By convention these live just
  before `register_block`.

---

## 4. Naming Conventions (Micro)

### 4.1 Identifiers

| Kind | Style | Example |
|---|---|---|
| Block ID | `kebab-case` string | `"block-onscreen-drawing"` |
| Block folder | `snake_case` | `block_onscreen_drawing` |
| Module file | `snake_case` | `feature_draw_handler_manager.py` |
| Class | `PascalCase` | `Wrapper_Draw_Handlers` |
| Function | `snake_case` | `register_block`, `get_logger` |
| Variable | `snake_case` | `cache_key_blocks` |
| Constant | `SCREAMING_SNAKE_CASE` | `_BLOCK_ID`, `LOG_LEVELS` |

### 4.2 Visibility

| Prefix | Meaning |
|---|---|
| `_leading_underscore` | Internal to the file. Don't import from outside. |
| `__double_leading` | Reserved for Python name-mangling; avoid. |
| `my_*` | User-editable config knob. Always near top of file under a `# CONFIGURATION` banner. |

### 4.3 Function Verbs

The verb at the start of a function name carries semantic weight:

| Verb | Meaning |
|---|---|
| `get_*` | Cheap retrieval from an existing cache/dict. Returns `None` if missing. |
| `determine_*` | Same as `get_*` but does real work. Result is often cached so the next call is `get_*`. |
| `create_*` | Instantiates new state. Errors / no-ops if it already exists. |
| `set_*` | Updates existing state, or creates if missing. |
| `destroy_*` | Removes an instance. |
| `init_*` | One-time setup hook. |
| `sync_*` / `update_*_with_mirrored_*` | Rebuilds one layer (BL/RTC) from the other. |
| `register_*` / `unregister_*` | Adds/removes from Blender's class registry. |
| `activate_*` / `deactivate_*` | Toggles without destroying. |
| `validate_*` | Reads, raises or returns `(ok, reasons)` — never mutates. |
| `is_*` / `has_*` | Returns bool. |
| `hook_*` | A subscriber callback, dispatched by name from `Wrapper_Hooks`. |
| `callback_*` | A Blender-supplied callback (update fn, app handler, etc). |
| `uilayout_*` / `ui_draw_*` | Draws into a `bpy.types.UILayout`. No state changes. |
| `op_*` | Operator execution body, called by `Operator.execute()`. |
| `_rtc_*` | Module-private RTC accessor helper. |

### 4.4 bpy Class Prefixes

All `bpy.types.*` subclasses use the prefix from `addon_bl_type_prefix` in
`my_addon_config.py` (default `DGBLOCKS`). Suffix indicates the type:

| Suffix | Class kind |
|---|---|
| `_PG_` | `bpy.types.PropertyGroup` |
| `_OT_` | `bpy.types.Operator` |
| `_PT_` | `bpy.types.Panel` |
| `_UL_` | `bpy.types.UIList` |
| `_MT_` | `bpy.types.Menu` |
| `_UP_` | `bpy.types.AddonPreferences` |

Example: `DGBLOCKS_PG_Core_Props`, `DGBLOCKS_OT_Open_Help_Page`,
`DGBLOCKS_PT_Core_Block_Panel`, `DGBLOCKS_UL_Blocks`,
`DGBLOCKS_UP_Core_Preferences`.

### 4.5 Dataclass / Wrapper Naming

The Wrapper-Record pattern (§7) names classes as:
- **Wrapper** (manager): `Wrapper_<Feature>` → `Wrapper_Draw_Handlers`,
  `Wrapper_Loggers`, `Wrapper_Hooks`.
- **Record** (RTC dataclass): `RTC_<Feature>_Instance` →
  `RTC_Draw_Handler_Instance`, `RTC_Block_Instance`, `RTC_FWC_Instance`.

---

## 5. Comment & Banner Style (Micro)

### 5.1 Major Section Banner
Used to mark the major divisions in a file. Always 80 `=` characters. Always
ALL CAPS title. Always a blank line before and after.

```python

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================
```

### 5.2 Subsection Separator
Used inside a class or large function to mark sub-areas. 60 `-` characters.
Title in sentence case.

```python
    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------
```

### 5.3 Standard Section Order in `__init__.py`

Every block's `__init__.py` follows this order:

1. Standard-library imports
2. `# Addon-level imports` separator
3. `# Inter-block imports` separator
4. `# Intra-block imports` separator
5. `# === BLOCK DEFINITION ===` banner — the three required `_BLOCK_*` constants
6. `# === BLENDER DATA FOR BLOCK ===` banner — PropertyGroups
7. `# === OPERATORS ===` banner
8. `# === UI ===` banner — Panels, AddonPreferences, UILists
9. `# === REGISTRATION EVENTS ===` banner — class lists + `register_block` / `unregister_block`
10. *(optional)* hook callback functions

If a block doesn't have one of the categories (e.g. no Operators), that banner
is omitted — don't leave empty banners.

### 5.4 Docstrings

- **Wrapper / record classes** get a one-line role tag at the top of the
  docstring identifying their architectural role:
  ```python
  """Manager — classmethods only, no instance state."""
  """Record — instance state only, no manager logic."""
  ```
- **Public functions** document Args, Returns, and Side effects (briefly).
- **Private helpers** use a single-line docstring or none.
- **Inline comments** explain *why*, not *what*. The `what` should be readable
  from the code.

---

## 6. Import Organization (Micro)

Three-tier import block, separated by 60-dash banners. Standard-library imports
go above all banners with no banner of their own.

```python
import os
from typing import Optional
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...my_addon_config import Documentation_URLs, addon_title, addon_name
from ...addon_helpers.data_structures import Enum_Sync_Events

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from .. import block_core
from ..block_core.core_features.feature_logs import Core_Block_Loggers, get_logger
from ..block_core.core_features.feature_hooks import Wrapper_Hooks

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Hook_Sources, Block_RTC_Members
from .feature_draw_handler_manager import Wrapper_Draw_Handlers
```

**Rules:**
- Always `# type: ignore` on the `import bpy` line and on bpy property
  annotations (false positives from static analyzers).
- Always **relative imports** within the addon (`from ...` /  `from ..` /
  `from .`). Never `from <addon_name>....`.
- Never import from a block not listed in `_BLOCK_DEPENDENCIES`.
- A block's `__init__.py` should not own variables/functions that other files
  in the same block need to import. Put those in `constants.py` or a feature
  module to avoid circular imports.

---

## 7. The Wrapper / Record Pattern (Macro)

This is the dominant pattern for any feature that has 0-to-many runtime
instances (timers, loggers, draw handlers, hooks, blocks…).

### 7.1 The Record (`@dataclass`)

```python
@dataclass
class RTC_Draw_Handler_Instance:
    """Record — instance state only, no manager logic."""
    draw_phase_name: str
    region_name: str
    groups_to_shaders_map: defaultdict[list]
    _optional_draw_callback: Callable = field(default=None, repr=False)
    _generated_handle: Callable = field(init=False, default=None, repr=False)
```

- All instance state. No methods (or only trivial property getters).
- Stored in the RTC under a `Block_RTC_Members` key, usually as a
  `dict[str, RTC_<Thing>_Instance]`.
- Underscore-prefixed fields are internal; mark them `repr=False` so dataclass
  prints stay readable.

### 7.2 The Wrapper (Manager)

```python
class Wrapper_Draw_Handlers(Abstract_Feature_Wrapper):
    """Manager — classmethods only, no instance state."""

    @classmethod
    def init_pre_bpy(cls) -> bool: ...

    @classmethod
    def init_post_bpy(cls) -> bool: ...

    @classmethod
    def destroy_wrapper(cls) -> bool: ...

    @classmethod
    def create_instance(cls, ...): ...

    @classmethod
    def destroy_instance(cls, ...): ...
```

- **Never** holds instance attributes. Every method is a `@classmethod`.
- Reads/writes records via the RTC.
- This is what gets imported by other blocks; the record stays internal.

### 7.3 Why split them?

- Breakpoint-based debugging: when stepping through a wrapper method, locals
  contain only the record(s) being acted on, not the manager's state.
- `console-print` debugging: a record's `__repr__` is meaningful; a manager's
  is not.
- Wrappers are **stateless and trivially mockable** in tests.

### 7.4 The Three Abstract Base Classes

Defined in `addon_helpers/data_structures.py`:

| Base class | When to inherit |
|---|---|
| `Abstract_Feature_Wrapper` | **Every** wrapper. Forces `init_pre_bpy`, `init_post_bpy`, `destroy_wrapper`. |
| `Abstract_Datawrapper_Instance_Manager` | Wrappers that manage 0-to-many records via CRUD. Forces `create_instance`, `destroy_instance`. |
| `Abstract_BL_and_RTC_Data_Syncronizer` | Wrappers whose records mirror Scene PropertyGroup data. Forces `update_RTC_with_mirrored_BL_data`, `update_BL_with_mirrored_RTC_data`. |

---

## 8. The Three Standard Enums (Micro)

Every block that has hooks, loggers, or RTC slots defines them in
`constants.py` using these three enums. The shape is fixed:

### 8.1 `Block_Hook_Sources`

```python
class Block_Hook_Sources(Enum):
    DRAW_EVENT = ("hook_draw_event", {"draw_handler_instance": Any})
    # value[0] = hook function name (string the subscriber must implement)
    # value[1] = expected kwargs dict {name: type}
```

### 8.2 `Block_Logger_Definitions`

```python
class Block_Logger_Definitions(Enum):
    DRAWHANDLER_LIFECYCLE = ("drawhandler_lifecycle", "DEBUG")
    SHADER_BATCH_EVENTS   = ("shader_batch_events",   "DEBUG")
    # value[0] = logger display name (snake-or-kebab case)
    # value[1] = default level: DEBUG | INFO | WARNING | ERROR | CRITICAL
```

### 8.3 `Block_RTC_Members`

```python
class Block_RTC_Members(Enum):
    DRAW_PHASES = ("draw_phases", {})
    SHADERS     = ("shader",      {})
    # value[0] = RTC dict key
    # value[1] = default value (deep-copied at init time)
```

**Rules:**
- All three enum *names* are in `SCREAMING_SNAKE_CASE`.
- Enum *values* are unique tuples (Python aliases enums with duplicate values).
- The first enum member should be the most-fundamental one.
- These enums are passed verbatim into `Wrapper_Block_Management.create_instance(...)`.

---

## 9. Registration Boilerplate (Macro)

The canonical body of `register_block` / `unregister_block` for a normal block:

```python
_block_classes_to_register = [
    DGBLOCKS_PG_<Block>_Props,
    DGBLOCKS_OT_<...>,
    DGBLOCKS_PT_<...>,
]
_feature_wrapper_classes_to_register = [
    Wrapper_<Feature_A>,
    Wrapper_<Feature_B>,
]

def register_block(event: Enum_Sync_Events):
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")

    block_module = get_self_block_module(block_manager_wrapper=Wrapper_Block_Management)
    Wrapper_Block_Management.create_instance(
        event,
        block_module                  = block_module,
        block_bpy_types_classes       = _block_classes_to_register,
        block_feature_wrapper_classes = _feature_wrapper_classes_to_register,
        block_hook_source_enums       = Block_Hook_Sources,
        block_RTC_member_enums        = Block_RTC_Members,
        block_logger_enums            = Block_Logger_Definitions,
    )

    bpy.types.Scene.<addon>_<block>_props = bpy.props.PointerProperty(
        type=DGBLOCKS_PG_<Block>_Props
    )
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block(event: Enum_Sync_Events):
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Block_Management.destroy_instance(event, block_id=_BLOCK_ID)

    if hasattr(bpy.types.Scene, "<addon>_<block>_props"):
        del bpy.types.Scene.<addon>_<block>_props

    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")
```

**Rules:**
- Always pass *enum classes*, not lists of values, to `create_instance`.
- Always log start and end of (un)registration via `Core_Block_Loggers.REGISTRATE`.
- Cleanup order is the reverse of setup order.
- Defensive `hasattr` guard before `del bpy.types.Scene.<prop>`.

---

## 10. Hook System (Macro / Micro)

### 10.1 Publishing
Inside the block that owns the event:

```python
Wrapper_Hooks.run_hooked_funcs(
    hook_func_name           = Block_Hook_Sources.TIMER_FIRE,
    should_halt_on_exception = False,
    timer_instance           = data,           # passed as **kwargs to subscribers
)
```

### 10.2 Subscribing
In any other block's `__init__.py`:

```python
def hook_timer_fire(timer_instance):
    logger = get_logger(My_Block_Loggers.MY_THING)
    # ... do work ...
    return True   # or a meaningful return value; see §10.4
```

The function name must match `Block_Hook_Sources.TIMER_FIRE.value[0]`.
No registration call is needed; discovery happens at registration time by
introspecting the block module.

### 10.3 Conditional bypass

```python
@hook_data_filter(lambda hook_metadata, context, **_:
    context.scene.my_props.is_enabled)
def hook_timer_fire(timer_instance):
    ...
```

The decorator's predicate is evaluated *before* the body. If it returns
falsy, the call is bypassed and the bypass is counted in hook metadata.

### 10.4 Return values
- Most hooks return `True` (success) / `False` (failure) or `None`.
- Modal-style hooks return `{'PASS_THROUGH'}`, `{'RUNNING_MODAL'}`, etc;
  `Wrapper_Hooks.run_hooked_funcs` aggregates results so the first
  non-`PASS_THROUGH` wins.

### 10.5 Core-block-provided hooks
Available to every block:

| Hook | When fired |
|---|---|
| `hook_post_register_init` | After `bpy.context` is fully ready, once per session. |
| `hook_core_event_undo` | Post-undo, after RTC has been re-synced from BL. |
| `hook_core_event_redo` | Post-redo, after RTC has been re-synced from BL. |
| `hook_block_registered` | A new block was registered at runtime. |
| `hook_block_unregistered` | A block was unregistered at runtime. |

---

## 11. Logging (Micro)

```python
# In constants.py:
class Block_Logger_Definitions(Enum):
    DRAWHANDLER_LIFECYCLE = ("drawhandler_lifecycle", "DEBUG")
    SHADER_BATCH_EVENTS   = ("shader_batch_events",   "DEBUG")

# In any feature file:
from ..block_core.core_features.feature_logs import get_logger
from .constants import Block_Logger_Definitions

logger = get_logger(Block_Logger_Definitions.DRAWHANDLER_LIFECYCLE)
logger.debug("Detail trace")
logger.info("Significant state change")
logger.warning("Recoverable issue")
logger.error("Failed", exc_info=True)
logger.critical("Unrecoverable")
logger.log_with_linebreak("Used at start/end of registration")
```

**Rules:**
- **Never use `print`** in checked-in code (debug-console-print's prettifier is
  the only sanctioned exception).
- One logger per concern, not per file. A feature with multiple concerns
  (lifecycle vs. per-event execution) should have a logger for each.
- Always `exc_info=True` when logging an exception.
- Default levels in committed code should be `DEBUG` while a block is in
  development, raised to `INFO`/`WARNING` once stable.
- Log messages prefer the imperative or progressive tense:
  "Starting…", "Finished…", "Skipping…", "Removing…".
- Embed identifying data: ``f"Timer '{timer_name}' fired"``, not just
  ``"Timer fired"``.

---

## 12. RTC Access Patterns (Micro)

```python
# Read
all_handlers = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)

# Write
Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, all_handlers)

# Convenience helpers (recommended for any RTC member touched in many places)
def _rtc_get_all() -> dict[str, RTC_Draw_Handler_Instance]:
    return Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.DRAW_PHASES)

def _rtc_set_all(data: dict) -> None:
    Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.DRAW_PHASES, data)
```

For **list-shaped registries** (the dominant pattern in core-block) there are
also indexed helpers:

```python
idx, instance, full_list = Wrapper_Runtime_Cache.get_unique_instance_from_registry_list(
    member_key            = Core_Runtime_Cache_Members.REGISTRY_ALL_BLOCKS,
    uniqueness_field      = "block_id",
    uniqueness_field_value= "block-onscreen-drawing",
)
```

**Rules:**
- Don't hold long-lived references to RTC sub-dicts/lists across yield points.
  Re-`get_cache` after any awaitable / handler boundary.
- Don't mutate RTC contents from inside a `bpy.types.PropertyGroup`'s
  `update=` callback before checking the syncing flag (see §13).

---

## 13. Two-Way BL ↔ RTC Sync (Macro)

Inheriting `Abstract_BL_and_RTC_Data_Syncronizer` opts a wrapper into automatic
sync on file-load / undo / redo. The wrapper must implement:

```python
@classmethod
def update_RTC_with_mirrored_BL_data(cls, event: Enum_Sync_Events):
    """BL is source of truth. Rebuild RTC dataclasses from CollectionProperty rows."""
    update_dataclasses_to_match_collectionprop(
        actual_FWC    = cls,
        source        = scene_collection_prop,
        target        = rtc_dict_or_list,
        key_fields    = [...],
        data_fields   = [...],
        actions_denied= set(),
        debug_logger  = logger_or_None,
    )

@classmethod
def update_BL_with_mirrored_RTC_data(cls, event: Enum_Sync_Events):
    """RTC is source of truth. Push dataclass values into CollectionProperty rows."""
    Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key, True)
    try:
        update_collectionprop_to_match_dataclasses(...)
    finally:
        Wrapper_Runtime_Cache.flag_cache_as_syncing(cache_key, False)
```

**Property-update callback pattern:**

```python
def _callback_thing_changed(self, context):
    if Wrapper_Runtime_Cache.is_cache_flagged_as_syncing(cache_key) or not is_bpy_ready():
        return
    try:
        Wrapper_<Feature>.update_RTC_with_mirrored_BL_data(Enum_Sync_Events.PROPERTY_UPDATE)
    except Exception:
        get_logger(...).error("Sync failed", exc_info=True)
```

The syncing flag prevents reentrancy when a sync action itself touches a
property that has an `update=` callback.

---

## 14. UI Patterns (Macro)

### 14.1 Panel structure

```python
class DGBLOCKS_PT_<Block>_Panel(bpy.types.Panel):
    bl_label       = ""               # Empty — drawn in draw_header
    bl_idname      = f"{addon_bl_type_prefix}_PT_<Name>"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = addon_title
    bl_options     = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return should_show_developer_ui_panels   # If it's a dev/debug panel

    def draw_header(self, context):
        ui_draw_block_panel_header(
            context, self.layout, _BLOCK_ID,
            Documentation_URLs.MY_PLACEHOLDER_URL_2,
            icon_name="TOOL_SETTINGS",
        )

    def draw(self, context):
        uilayout_draw_<feature>_panel(context, self.layout)
```

### 14.2 Drawing logic lives outside the Panel class

Keep `Panel.draw` minimal. All real layout code goes in `helper_functions.py`
as `uilayout_*` functions, taking `(context, container, ...)` and returning
nothing. This is so:
- The same drawing can be reused inside another panel/popover.
- The `__init__.py` stays scannable.
- UI is testable without instantiating a Panel.

### 14.3 Operator pattern

```python
class DGBLOCKS_OT_<Action>(bpy.types.Operator):
    bl_idname  = "dgblocks.<verb>_<noun>"
    bl_label   = "<Human label>"
    bl_options = {"REGISTER"}

    some_arg: bpy.props.StringProperty()  # type: ignore

    def execute(self, context):
        return op_<verb>_<noun>(context, self.some_arg)
```

Real work goes in `op_*` functions in `helper_functions.py`, returning the
`{'FINISHED'}` / `{'CANCELLED'}` set.

---

## 15. Block README Template (Macro)

Every block's `README.md` follows this outline:

1. **Block ID & Version**
2. **Block Dependencies** (list of `_BLOCK_ID`s)
3. **External Dependencies** (pip libs)
4. **Purpose** — one paragraph
5. **Architecture** — brief file-by-file roles
6. **Key Features** — bullet list
7. **Hook Functions** — both source (this block fires) and subscriber
   (this block listens to) hooks
8. **Public API** — what other blocks may import
9. **Usage Notes** — quirks, limitations, how to remove

---

## 16. Type Hints & Annotations (Micro)

- All new classmethod / function signatures get type hints. No exceptions.
- `bpy.props.*` fields get `# type: ignore` after the colon, because the
  `prop: Type(...)` syntax confuses static analyzers:
  ```python
  is_enabled: bpy.props.BoolProperty(default=True)  # type: ignore
  ```
- `import bpy` always has `# type: ignore`.
- Dataclass internal-only fields use `field(default=..., init=False, repr=False)`.
- Use `Optional[X]` instead of `X | None` for now (consistency with current code).

---

## 17. Error Handling (Micro)

```python
# Use try/except/finally for cleanup-required regions.
try:
    Wrapper_Hooks.run_hooked_funcs(...)
    data.count_fire_success += 1
except Exception:
    data.count_fire_failure += 1
    logger.error("Exception in callback", exc_info=True)
finally:
    data.is_currently_running = False
```

```python
# Defensive early returns for "this should be impossible" states.
if metadata is None:
    logger.warning(f"Timer metadata not found — stopping")
    return None

if name not in registry:
    logger.warning(f"'{name}' not found")
    return False
```

**Rules:**
- A wrapper method should never let an exception escape into Blender's event
  loop. `try/except/log/continue` instead.
- `finally` blocks reset re-entrancy flags and counters even on exception.
- An exception during *registration* should be logged with `exc_info=True` and
  *should* propagate — `Wrapper_Block_Management` will catch and log
  per-block, marking the block invalid rather than aborting the whole addon.

---

## 18. Decision Matrix — Where Does My Code Go?

| If your code… | Put it in… |
|---|---|
| …is generic enough to use across multiple addons | `addon_helpers/` |
| …is the contract a feature exposes (hooks, RTC keys, log ids) | `<block>/constants.py` |
| …is "the manager" of a feature with multiple instances | `<block>/feature_<name>.py` (the wrapper class) |
| …represents one instance's state | A `@dataclass RTC_*_Instance` in the feature file |
| …draws UI | `<block>/helper_functions.py` as `uilayout_*` |
| …is the body of an operator | `<block>/helper_functions.py` as `op_*` |
| …is a Blender-fired callback (update fn, app handler) | The feature file owning the data, prefixed `_callback_*` |
| …is a hook subscriber | The block's `__init__.py`, prefixed `hook_*` |
| …is config a downstream developer might tweak | `my_addon_config.py` if addon-wide; a `my_*` var near the top of the file otherwise |

---

## 19. Things You Are *Not* Allowed to Do

- Use `print` for diagnostic output. Use a logger.
- Cache `bpy.types.ID` references in the RTC.
- Import from a block not in your `_BLOCK_DEPENDENCIES`.
- Have `__init__.py` own state needed by sibling files (causes circular imports).
- Use string literals for hook names, RTC keys, or logger ids — use the enums.
- Modify a `_BLOCK_*` private name from outside the block.
- Register a `bpy.types.*` class outside the block-management flow (i.e., not
  in `_block_classes_to_register`).
- Catch `Exception` silently — always log at minimum WARNING.
