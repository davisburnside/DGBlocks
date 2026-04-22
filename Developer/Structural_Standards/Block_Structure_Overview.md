
# Blender Addon Architecture Patterns - Comprehensive Analysis

Note that any instance of "DGBLOCKS", in any capitilization, is to be replaced with your own addon's name in the final export step
TODO create export code later
TODO changes to make:
1.namingConvention.classes: "UP" for prefs panels should be "AP"

---

## 1. FILE ORGANIZATION & NAMING

### Block Structure
Each block follows a consistent directory layout:
```
block_name/
├── __init__.py              # Registration, UI, operators, hook implementations
├── block_constants.py       # Enums for loggers, hooks, RTC members
├── block_config.py          # Optional: user-configurable settings
├── feature_*_wrapper.py     # Main feature implementation (Abstract_Feature_Wrapper)
├── helper_functions.py      # UI drawing & operator execution logic
└── README.md                # Block documentation
```

### Naming Conventions
- **Block IDs**: Lowercase with hyphens: `"block-stable-timers"`, `"block-core"`
- **Files**: Snake_case: `core_feature_logs.py`, `feature_timer_wrapper.py`
- **Classes**: PascalCase with prefixes:
  - `DGBLOCKS_PG_*` - PropertyGroups
  - `DGBLOCKS_OT_*` - Operators
  - `DGBLOCKS_PT_*` - Panels
  - `DGBLOCKS_UL_*` - UILists
  - `DGBLOCKS_UP_*` - AddonPreferences
- **Functions**: Snake_case: `register_block()`, `get_instance()`
- **Hook functions**: `hook_` prefix: `hook_post_register_init`, `hook_timer_fire`
- **Private/internal**: Leading underscore: `_rtc_get_all()`, `_register_bpy_timer()`
- **Constants**: SCREAMING_SNAKE_CASE: `_BLOCK_ID`, `_BLOCK_VERSION`

---

## 2. COMMENT & DOCUMENTATION STYLES

### Banner Comments (Section Separators)
Used for major file sections with consistent formatting:
```python
#================================================================================
# MAJOR SECTION NAME
#================================================================================

# ------------------------------------------------------------
# Subsection name
# ------------------------------------------------------------
```

**Pattern rules:**
- Major sections: 80 `=` characters
- Subsections: 60 `-` characters
- ALL CAPS for major sections
- Sentence case for subsections
- Always blank line before/after

### Docstrings
**Comprehensive docstrings** for wrapper classes and complex functions:
```python
class Timer_Wrapper(Abstract_Feature_Wrapper):
    """
    Manager — classmethods only, no instance state.
    Manages Blender app timers with metadata tracking and hook propagation.
    All per-timer state is stored in Timer_Instance_Data objects...
    """
```

**Inline comments** explain non-obvious logic:
```python
# Re-entrancy guard
if data.is_currently_running:
    logger.debug(f"Already running — skipping")
    return data.frequency_ms / 1000.0
```

### Documentation Headers
Functions document:
- Purpose (one-liner or paragraph)
- Args (with types)
- Returns (with type and meaning)
- Side effects / behavior notes

---

## 3. IMPORT ORGANIZATION

**Strict three-tier hierarchy** with visual separators:

```python
# --------------------------------------------------------------
# Addon-level imports
# --------------------------------------------------------------
from ...addon_config import addon_name

# --------------------------------------------------------------
# Inter-block imports (from other blocks)
# --------------------------------------------------------------
from .._block_core.core_feature_logs import get_logger
from .._block_core.core_feature_runtime_cache import Wrapper_Runtime_Cache

# --------------------------------------------------------------
# Intra-block imports (same block, other files)
# --------------------------------------------------------------
from .block_constants import Block_Logger_Definitions
from .feature_timer_wrapper import Timer_Wrapper
```

**Rules:**
1. Standard library first (no separator)
2. Then addon-level, inter-block, intra-block with separators
3. Relative imports preferred within addon
4. `# type: ignore` on bpy imports to suppress type checker warnings

---

## 4. CONSTANTS & ENUM PATTERNS

### Block Metadata (Always at top of `__init__.py`)
```python
_BLOCK_ID = "block-stable-timers"
_BLOCK_VERSION = (1,0,0)
_BLOCK_DEPENDENCIES = [_block_core._BLOCK_ID]
```

### Enum Classes for Structured Data
Three standard enums in `block_constants.py`:

**1. Block_Logger_Definitions**
```python
class Block_Logger_Definitions(Enum):
    TIMER_FIRE = ("timer-exec", "INFO")
    TIMER_LIFECYCLE = ("timer-lifecycle", "DEBUG")
    # Format: (display_name:, default_log_level)
```

**2. Block_Hooks**
```python
class Block_Hooks(Enum):
    TIMER_FIRE = ("hook_timer_fire", {
        "context": bpy.types.Context, 
        "timer_name": str
    })
    # Format: (function_name, expected_args_dict)
```

**3. Block_Runtime_Cache_Members**
```python
class Block_Runtime_Cache_Members(Enum):
    TIMER_INSTANCES = ("timer-instances", {})
    # Format: (cache_key_string, default_value)
```

**Pattern notes:**
- Enum NAMES are used as identifiers (autocomplete-friendly)
- Enum VALUES hold metadata (tuple unpacking)
- Comments document the value format
- Prevents "magic string" anti-pattern

---

## 5. ARCHITECTURE PATTERNS

### Abstract Base Classes (Core Pattern)

**Two-tier abstraction system:**

```python
# All feature wrappers inherit from this
class Abstract_Feature_Wrapper(ABC):
    @classmethod
    @abstractmethod
    def init_pre_bpy(cls, **kwargs): pass
    
    @classmethod
    @abstractmethod
    def init_post_bpy(cls, **kwargs): pass
    
    @classmethod
    @abstractmethod
    def destroy_wrapper(cls, **kwargs): pass
```

```python
# Multi-instance features add CRUD operations
class Abstract_Datawrapper_Instance_Manager(ABC):
    @classmethod
    @abstractmethod
    def create_instance(cls, **kwargs) -> any: pass
    
    @classmethod
    @abstractmethod
    def get_instance(cls, **kwargs) -> any: pass
    
    @classmethod
    @abstractmethod
    def set_instance(cls, **kwargs): pass
    
    @classmethod
    @abstractmethod
    def destroy_instance(cls, **kwargs): pass
```

### Wrapper + Instance Pattern

**Manager-Record separation:**
- **Wrapper class** 
    - Manager (classmethods only, no state/data)
    -  Allows cleaner breakpoint-based debug workflow
- **Instance dataclass** 
    - Record (data only, no logic)
    - Allows cleaner data-based debugging, like when using the builtin console-print tools with dev-friendly formatted & filtered output

Example:
```python
@dataclass
class Timer_Instance_Data:
    """Record — instance state only, no manager logic."""
    timer_name: str
    frequency_ms: int
    is_enabled: bool = True
    # ... metadata fields
    _timer_func: Optional[Callable] = field(default=None, init=False, repr=False)

class Timer_Wrapper(Abstract_Feature_Wrapper, Abstract_Datawrapper_Instance_Manager):
    """Manager — classmethods only, no instance state."""
    
    @classmethod
    def create_instance(cls, timer_name: str, ...):
        # Creates Timer_Instance_Data, stores in RTC
```

**Key insight:** All instance data lives in a dataclass in the RTC (Runtime Cache), not in the stateless wrapper class.
Wrappers without instances can still create/edit/delete data in the RTC

---

## 6. DATA STORAGE ARCHITECTURE

### Two-Tier Data System

**Scene Properties (Source of Truth)**
- Persistent (saved in .blend file)
- User-editable via UI
- PropertyGroups attached to `bpy.types.Scene`

**Runtime Cache (Transient)**
- Volatile (lost on reload/unregister)
- Stores instance metadata, callables, references
- Thread-safe dictionary managed by `Wrapper_Runtime_Cache`

**Synchronization Pattern:**
```python
@classmethod
def sync_scene_to_rtc(cls, scene) -> None:
    """
    Rebuild RTC from scene properties.
    Scene properties are the source of truth.
    
    Called:
      - During post-register init (app startup / file load)
      - When properties change (via update callbacks)
    """
```

**Update callback pattern:**
```python
is_enabled: BoolProperty(
    name="Enabled",
    update=lambda self, context: Timer_Wrapper.sync_scene_to_rtc(context.scene)
)
```

---

## 7. LOGGING PATTERNS

### Logger Access
```python
logger = get_logger(Block_Logger_Definitions.TIMER_LIFECYCLE)
```

### Log Level Usage
- **DEBUG**: Detailed flow tracing (`"Starting sync_scene_to_rtc"`)
- **INFO**: Significant state changes (`"Created timer 'my_timer'"`)
- **WARNING**: Recoverable issues (`"Timer already exists — skipping"`)
- **ERROR**: Failures with recovery (`"Failed to register timer"`, `exc_info=True`)
- **CRITICAL**: Unrecoverable failures (addon broken)

### Logging Conventions
- Log at function entry/exit for lifecycle methods
- Always use `exc_info=True` with exception logging
- Include relevant IDs in messages: `f"Timer '{timer_name}' fired"`
- Use verbs: "Starting", "Finished", "Skipping", "Removing"

---

## 8. REGISTRATION LIFECYCLE

### Consistent Registration Flow

**In every `__init__.py`:**

```python
_block_classes_to_register = [
    DGBLOCKS_PG_Timer_Props,
    DGBLOCKS_OT_Timer_Add,
    DGBLOCKS_PT_Timer_Panel,
]

def register_block():
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    register_block_components(
        block_id=_BLOCK_ID,
        block_classes=_block_classes_to_register,
        block_runtime_cache_members=Block_Runtime_Cache_Members,
        block_hooks=Block_Hooks,
        block_loggers=Block_Logger_Definitions
    )
    
    # Attach PropertyGroup to Scene
    bpy.types.Scene.dgblocks_timer_props = PointerProperty(type=DGBLOCKS_PG_Timer_Props)
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")
    
    # Cleanup before unregistering
    Timer_Wrapper.destroy_wrapper()
    
    unregister_block_components(
        block_id=_BLOCK_ID,
        block_classes=_block_classes_to_register,
        block_runtime_cache_members=Block_Runtime_Cache_Members,
        block_hooks=Block_Hooks,
        block_loggers=Block_Logger_Definitions
    )
    
    # Remove PropertyGroup
    if hasattr(bpy.types.Scene, "dgblocks_timer_props"):
        del bpy.types.Scene.dgblocks_timer_props
    
    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")
```

**Pattern rules:**
1. List classes at module level (`_block_classes_to_register`)
2. Log at start/end of register/unregister
3. Use helper functions (`register_block_components`)
4. Clean up in reverse order (wrappers before components)
5. Defensive checks (`hasattr` before `del`)

---

## 9. HOOK SYSTEM PATTERNS

### Hook Definition
In `block_constants.py`:
```python
class Block_Hooks(Enum):
    TIMER_FIRE = ("hook_timer_fire", {
        "context": bpy.types.Context, 
        "timer_name": str
    })
```

### Hook Implementation
In block's `__init__.py`:
```python
def hook_timer_fire(timer_instance: Timer_Instance_Data):
    """Respond to timer events"""
    logger = get_logger(My_Logger)
    # ... implementation
    return True  # Optional return value
```

### Hook Propagation
```python
Wrapper_Hooks.run_hooked_funcs(
    hook_func_name=Block_Hooks.TIMER_FIRE,
    should_halt_on_exception=False,  # Continue even if one fails
    timer_instance=timer_instance,
)
```

### Hook Data Filter Decorator
```python
@hook_data_filter(lambda hook_metadata, context, **_:
    context.scene.my_props.is_enabled)
def hook_timer_fire(context):
    # Only runs when predicate returns True
    pass
```

**Pattern notes:**
- Hooks are optional (blocks without them are skipped)
- Return values aggregated (first non-`PASS_THROUGH` wins for modals)
- Metadata tracks success/failure counts, bypass reasons, timing
- Re-entrancy protection via `is_currently_running` flag

---

## 10. UI PATTERNS

### Panel Header Pattern
```python
def draw_header(self, context):
    # Dynamic label showing state
    status = "( On )" if is_enabled else "( Off )"
    label = f"{_BLOCK_ID.upper()} {status}"
    
    uilayout_draw_block_panel_header(
        context, 
        self.layout, 
        label, 
        Documentation_URLs.MY_PLACEHOLDER_URL, 
        icon_name="TIME"
    )
```

### UI Drawing Separation
```python
# In helper_functions.py
def uilayout_draw_timer_panel(context, container):
    """All drawing logic lives here"""
    box = ui_box_with_header(context, container, "Timer Control")
    # ... layout code

# In __init__.py Panel.draw()
def draw(self, context):
    uilayout_draw_timer_panel(context, self.layout)
```

**Rationale:** Keeps `__init__.py` clean, drawing logic reusable/testable

### Operator Execution Separation
Same pattern for operators:
```python
# In helper_functions.py
def op_timer_add(context):
    """Execution logic"""
    # ... implementation
    return {'FINISHED'}

# In __init__.py Operator.execute()
def execute(self, context):
    return op_timer_add(context)
```

---

## 11. TYPE HINTS & ANNOTATIONS

### Comprehensive Type Hinting
```python
@classmethod
def create_instance(
    cls,
    timer_name: str,
    frequency_ms: int,
    is_enabled: bool = True,
) -> bool:
```

### Blender Property Type Annotations
```python
timer_name: StringProperty(...) # type: ignore
frequency_ms: IntProperty(...) # type: ignore
is_enabled: BoolProperty(...) # type: ignore
```
**Note:** `# type: ignore` suppresses false positives from static analyzers

### Dataclass Field Annotations
```python
@dataclass
class Timer_Instance_Data:
    timer_name: str
    frequency_ms: int
    is_enabled: bool = True
    
    # Private fields excluded from __init__ and __repr__
    _timer_func: Optional[Callable] = field(default=None, init=False, repr=False)
```

---

## 12. ERROR HANDLING PATTERNS

### Try-Except-Finally for Cleanup
```python
try:
    Wrapper_Hooks.run_hooked_funcs(...)
    data.count_fire_success += 1
except Exception as e:
    data.count_fire_failure += 1
    logger.error(f"Exception in callback", exc_info=True)
finally:
    # Always clean up
    data.is_currently_running = False
```

### Graceful Degradation
```python
if metadata is None:
    logger.warning(f"Timer metadata not found — stopping")
    return None  # Stop the timer, don't crash
```

### Defensive Programming
```python
if not hasattr(scene, "dgblocks_timer_props"):
    logger.warning("Scene has no timer props")
    return  # Early exit

if timer_name not in all_timers:
    logger.warning(f"Timer '{timer_name}' not found")
    return False
```

---

## 13. NAMING SEMANTICS

### Verb Conventions
- **create_**: Makes new instance, fails if exists
- **get_**: Retrieves existing, returns None if missing
- **set_**: Updates existing, creates if missing
- **destroy_**: Removes instance
- **sync_**: Rebuilds cache from source of truth
- **register_**: Adds to Blender's registry
- **unregister_**: Removes from Blender's registry
- **activate_/deactivate_**: Enable/disable without destroying
- **init_**: One-time setup
- **destroy_wrapper**: Complete teardown

### Prefix Conventions
- `_rtc_`: Private RTC helper functions
- `hook_`: Callback functions for hook system
- `callback_`: Blender callbacks (update functions, handlers)
- `uilayout_`: UI drawing functions
- `op_`: Operator execution logic
- `debug_`: Debug-only features

---

## 14. CONSISTENCY PATTERNS


```python
def _factory_property_update_func(listener_def: Enum) -> Callable:
    """Create unique update function for each listener"""
    def update(self, context):
        if getattr(self, listener_def.property_name):
            _add_listener(listener_def)
        else:
            _remove_listener(listener_def)
    return update
```

### RTC Convenience Helpers
**Module-level private helpers** for RTC access:
```python
def _rtc_get_all() -> Dict[str, Timer_Instance_Data]:
    """Return live dict from RTC."""
    return Wrapper_Runtime_Cache.get_instance(Block_Runtime_Cache_Members.TIMER_INSTANCES)

def _rtc_set_all(data: Dict[str, Timer_Instance_Data]) -> None:
    """Write dict to RTC."""
    Wrapper_Runtime_Cache.set_instance(Block_Runtime_Cache_Members.TIMER_INSTANCES, data)
```

---

## 15. DOCUMENTATION PATTERNS

### README.md Structure
Every block README follows this outline:
1. **Purpose** - One-paragraph overview
2. **Features** - Bullet list of capabilities
3. **Architecture** - Data storage layers, wrapper pattern
4. **Usage** - For users and developers
5. **Implementation Details** - Lifecycle, sync, callbacks
6. **Dependencies** - Internal/external
7. **Files** - Brief description of each file

### Inline Architecture Documentation
```python
"""
Record — instance state only, no manager logic.
Holds all metadata for a single timer...
"""

"""
Manager — classmethods only, no instance state.
Manages Blender app timers...
"""
```
**Pattern:** Every class docstring identifies its architectural role

---

## 16. ADVANCED PATTERNS

### Callable Instance Pattern (Event Listeners)
```python
@dataclass
class Event_Listener_Wrapper:
    handler_type: Enum
    
    def __call__(self, *args) -> None:
        """Makes instance usable as Blender handler callback."""
        # ... implementation

# Register the instance itself
bpy.app.handlers.depsgraph_update_post.append(listener_wrapper)
```

### Return Value Aggregation (Modal)
```python
def _aggregate_hook_returns(self, results: dict, default: set) -> set:
    """First non-PASS_THROUGH wins"""
    for block_id, return_value in results.items():
        if return_value != {'PASS_THROUGH'}:
            return return_value
    return default
```

### Helper Utilities for Data Sync
```python
def diff_collections(old_keys, new_keys):
    """Returns (to_add, to_remove, to_update)"""
    
def sync_blender_propertygroup_and_raw_python(pg):
    """Convert Blender PropertyGroup to dict & vice versa. Used to sync RTC and Blender data"""
    
def merge_dataclass_with_dict(dataclass_instance, update_dict):
    """Update dataclass fields from dict, preserve others"""
```

---

## Summary: Key Architectural Principles

1. **Separation of Concerns**: UI, logic, data storage in separate files
2. **Declarative Configuration**: Enums define structure, minimize magic strings
3. **Manager-Record Pattern**: Wrappers manage, dataclasses hold state
4. **Two-Tier Data**: Scene (persistent) → RTC (transient) with sync
5. **Hook-Based Communication**: Blocks communicate via hook system, not direct calls
6. **Graceful Degradation**: Defensive checks, logging, early returns
7. **Lifecycle Discipline**: Init/destroy pairs, cleanup in reverse order
8. **Type Safety**: Comprehensive hints, dataclasses, abstract base classes
9. **Consistency**: Naming, structure, patterns repeated across all blocks
10. **Documentation**: Inline comments, docstrings, READMEs follow templates
