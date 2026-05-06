# DGBlocks — Block Authoring Guide

> Step-by-step recipe for adding a new block. Pair with `systemPatterns.md`
> for *why* each step looks the way it does.

This guide builds a fictional `block-example` that owns a single PropertyGroup
and one feature with multiple instances. Replace `example` / `Example` with
your block's name as you go.

---

## 0. Before You Start

Decide the answers to these. If you can't, your block is probably trying to do
two things — split it.

1. **What single capability does this block deliver?** (One sentence.)
2. **Does it depend on any other block?** (Always at least `block-core`.)
3. **Does it need persistent state in `.blend` files?** (PropertyGroups vs.
   RTC-only.)
4. **Does it need to publish events to other blocks?** (Hooks.)
5. **Does it run code at runtime that other blocks should be able to inject
   into?** (Hooks, the other direction.)

---

## 1. Create the Folder

```
native_blocks/block_example/
├── __init__.py
├── constants.py
├── helper_functions.py        # optional
├── feature_example_thing.py   # optional, one per major feature
└── README.md                  # optional but encouraged
```

Folder name in `snake_case`. Block ID will be `kebab-case`.

---

## 2. Write `constants.py`

This is the block's contract surface. Even an extremely simple block declares
all three enums (use empty bodies if needed, but the *file* should exist for
consistency).

```python
from enum import Enum
from typing import Any

_BLOCK_ID = "block-example"

# ==============================================================================================================================
# HOOK SOURCES
# ==============================================================================================================================

class Block_Hook_Sources(Enum):
    # value[0] = function name a subscriber must define
    # value[1] = expected kwargs dict {name: type}
    EXAMPLE_THING_FIRED = ("hook_example_thing_fired", {"thing_instance": Any})

# ==============================================================================================================================
# LOGGERS
# ==============================================================================================================================

class Block_Logger_Definitions(Enum):
    # value[0] = display name
    # value[1] = default level
    LIFECYCLE     = ("example_lifecycle",     "DEBUG")
    THING_EVENTS  = ("example_thing_events",  "INFO")

# ==============================================================================================================================
# RTC MEMBERS
# ==============================================================================================================================

class Block_RTC_Members(Enum):
    # value[0] = RTC dict key
    # value[1] = default value (deep-copied at init)
    THINGS = ("things", {})
```

---

## 3. Write the Feature File

One feature wrapper per file. For a block with one feature:

```python
# native_blocks/block_example/feature_example_thing.py

from dataclasses import dataclass, field
from typing import Optional
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import (
    Abstract_Feature_Wrapper,
    Abstract_Datawrapper_Instance_Manager,
    Enum_Sync_Events,
)

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ..block_core.core_features.feature_runtime_cache import Wrapper_Runtime_Cache
from ..block_core.core_features.feature_logs import get_logger

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Logger_Definitions, Block_RTC_Members

# ==============================================================================================================================
# RECORD
# ==============================================================================================================================

@dataclass
class RTC_Example_Thing_Instance:
    """Record — instance state only, no manager logic."""
    thing_id: str
    label: str
    fire_count: int = 0
    _internal_handle: Optional[object] = field(default=None, repr=False)

# ==============================================================================================================================
# WRAPPER (MANAGER)
# ==============================================================================================================================

class Wrapper_Example_Things(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):
    """Manager — classmethods only, no instance state."""

    # --------------------------------------------------------------
    # Implemented from Abstract_Feature_Wrapper
    # --------------------------------------------------------------

    @classmethod
    def init_pre_bpy(cls, event: Enum_Sync_Events) -> bool:
        get_logger(Block_Logger_Definitions.LIFECYCLE).debug("init_pre_bpy")
        return True

    @classmethod
    def init_post_bpy(cls, event: Enum_Sync_Events) -> bool:
        get_logger(Block_Logger_Definitions.LIFECYCLE).debug("init_post_bpy")
        return True

    @classmethod
    def destroy_wrapper(cls, event: Enum_Sync_Events) -> bool:
        get_logger(Block_Logger_Definitions.LIFECYCLE).debug("destroy_wrapper")
        return True

    # --------------------------------------------------------------
    # Implemented from Abstract_Datawrapper_Instance_Manager
    # --------------------------------------------------------------

    @classmethod
    def create_instance(cls, thing_id: str, label: str) -> RTC_Example_Thing_Instance:
        all_things = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.THINGS)
        if thing_id in all_things:
            get_logger(Block_Logger_Definitions.LIFECYCLE).warning(
                f"Thing '{thing_id}' already exists — skipping"
            )
            return all_things[thing_id]

        instance = RTC_Example_Thing_Instance(thing_id=thing_id, label=label)
        all_things[thing_id] = instance
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.THINGS, all_things)
        return instance

    @classmethod
    def destroy_instance(cls, thing_id: str) -> bool:
        all_things = Wrapper_Runtime_Cache.get_cache(Block_RTC_Members.THINGS)
        if thing_id not in all_things:
            return False
        del all_things[thing_id]
        Wrapper_Runtime_Cache.set_cache(Block_RTC_Members.THINGS, all_things)
        return True
```

Add `Abstract_BL_and_RTC_Data_Syncronizer` only if your records mirror a
`bpy.types.PropertyGroup` collection. See `feature_block_manager.py` for the
canonical example.

---

## 4. Write the `__init__.py`

```python
import bpy  # type: ignore

# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_helpers.data_structures import Enum_Sync_Events
from ...addon_helpers.generic_helpers import get_self_block_module

# --------------------------------------------------------------
# Inter-block imports
# --------------------------------------------------------------
from ..block_core.core_features.feature_block_manager import Wrapper_Block_Management
from ..block_core.core_features.feature_logs import Core_Block_Loggers, get_logger

# --------------------------------------------------------------
# Intra-block imports
# --------------------------------------------------------------
from .constants import Block_Hook_Sources, Block_Logger_Definitions, Block_RTC_Members
from .feature_example_thing import Wrapper_Example_Things

# ==============================================================================================================================
# BLOCK DEFINITION
# ==============================================================================================================================

_BLOCK_ID           = "block-example"
_BLOCK_VERSION      = (0, 1, 0)
_BLOCK_DEPENDENCIES = ["block-core"]

# ==============================================================================================================================
# BLENDER DATA FOR BLOCK
# ==============================================================================================================================

class DGBLOCKS_PG_Example_Props(bpy.types.PropertyGroup):
    is_enabled: bpy.props.BoolProperty(default=True)  # type: ignore

# ==============================================================================================================================
# REGISTRATION EVENTS
# ==============================================================================================================================

_block_classes_to_register = [
    DGBLOCKS_PG_Example_Props,
]
_feature_wrapper_classes_to_register = [
    Wrapper_Example_Things,
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

    bpy.types.Scene.dgblocks_example_props = bpy.props.PointerProperty(
        type=DGBLOCKS_PG_Example_Props
    )
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block(event: Enum_Sync_Events):
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting unregistration for '{_BLOCK_ID}'")

    Wrapper_Block_Management.destroy_instance(event, block_id=_BLOCK_ID)

    if hasattr(bpy.types.Scene, "dgblocks_example_props"):
        del bpy.types.Scene.dgblocks_example_props

    logger.debug(f"Finished unregistration for '{_BLOCK_ID}'")

# ==============================================================================================================================
# HOOK SUBSCRIBERS (optional — react to hooks owned by other blocks)
# ==============================================================================================================================

def hook_post_register_init():
    """Fired after bpy.context is fully ready, once per session."""
    get_logger(Block_Logger_Definitions.LIFECYCLE).info(
        f"'{_BLOCK_ID}' post-register init"
    )
    return True
```

---

## 5. Activate the Block

Open `my_activated_blocks.py` and add the import + entry:

```python
from .native_blocks import block_example

_ordered_blocks_list = [
    block_core,
    # ... other blocks ...
    block_example,
]
```

Order matters: a block must come *after* every block it depends on.

---

## 6. Smoke Test

1. Reload Blender or hit "Reload Scripts".
2. Watch the system console for `Starting registration for 'block-example'`
   followed by `Finished registration for 'block-example'`. No tracebacks.
3. Open the dev panel → Loggers UIList. Your loggers should be listed
   (`example_lifecycle`, `example_thing_events`).
4. Open the Debug Console-Print panel and dump RTC. The `things` member should
   be present (empty dict by default).
5. Disable the block via the Blocks UIList — your `unregister_block` should
   run with no errors. Re-enable and verify it comes back clean.

---

## 7. Add UI (when you have something to show)

Drawing logic goes in `helper_functions.py` as `uilayout_*` functions. The
Panel class in `__init__.py` should be a thin shell. See `systemPatterns.md`
§14 for the full pattern.

---

## 8. Add Hook Subscribers (optional)

If your block reacts to events from other blocks, add `hook_*` functions to
your `__init__.py`. Discovery is by name — no registration needed beyond
existing in the module. Use `@hook_data_filter` for conditional bypass.

---

## 9. Add Hook Sources (optional)

If your block emits events:

1. Add the source enum to `Block_Hook_Sources` (already done in §2).
2. Call `Wrapper_Hooks.run_hooked_funcs(...)` at the right moment with kwargs
   matching `value[1]`.

---

## 10. Promotion Checklist

A block is "ready" when:

- [ ] Folder named `block_<feature>`, ID `block-<feature>`.
- [ ] All required `_BLOCK_*` constants present.
- [ ] `register_block(event)` and `unregister_block(event)` accept the `event` arg.
- [ ] All three enums (`Block_Hook_Sources`, `Block_Logger_Definitions`,
      `Block_RTC_Members`) defined in `constants.py`.
- [ ] No string literals for hook names / logger ids / RTC keys outside the enums.
- [ ] All wrappers extend `Abstract_Feature_Wrapper`. Wrappers with multiple
      instances also extend `Abstract_Datawrapper_Instance_Manager`. Wrappers
      that mirror BL data also extend `Abstract_BL_and_RTC_Data_Syncronizer`.
- [ ] All bpy classes use the `DGBLOCKS_<TYPE>_*` prefix and `# type: ignore`
      on prop fields.
- [ ] Section banners (`BLOCK DEFINITION`, etc.) in canonical order.
- [ ] No `print()` calls. All diagnostics through loggers.
- [ ] Block can be enabled and disabled at runtime without errors.
- [ ] Debug console-print dump of the block's RTC is human-readable.
- [ ] `README.md` written following the §15 outline of `systemPatterns.md`.
- [ ] Removing the block (folder delete + `_ordered_blocks_list` entry remove)
      does not break any other block.

---

## 11. Common Pitfalls

- **Circular imports** between `__init__.py` and a feature file. Move shared
  constants to `constants.py`.
- **Forgetting `# type: ignore`** on `bpy.props.*` lines — they'll lint clean
  but your editor will complain forever.
- **Holding RTC sub-references across handler boundaries.** Always re-fetch.
- **Calling `Wrapper_<X>` methods during `init_pre_bpy`** that depend on
  `bpy.context.scene` — defer to `init_post_bpy` or to a
  `hook_post_register_init` subscriber.
- **Not guarding `update=` callbacks** with the syncing flag, causing
  re-entrant sync loops.
- **Adding a hook subscriber without an empty-kwargs guard.** A subscriber
  signature must match the hook source's `value[1]` dict. Mismatch silently
  raises — check logs.
