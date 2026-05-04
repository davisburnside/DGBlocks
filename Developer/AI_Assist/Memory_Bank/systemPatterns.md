# DGBlocks System Patterns

## Block Architecture Pattern

### Core Structure
Every block follows this standardized pattern:
```
block_[feature_name]/
├── __init__.py           # Required: Contains _BLOCK_ID, _BLOCK_DEPENDENCIES, register/unregister functions
├── block_constants.py    # Optional: Block-specific constants and enums
├── block_config.py       # Optional: User-configurable settings
├── feature_[name].py     # Optional: Modules implementing specific features
├── helper_[name].py      # Optional: Helper functions and utilities
└── [sub_feature]/        # Optional: Sub-packages for complex features
```

### Required Elements
Each block's `__init__.py` must contain:
```python
_BLOCK_ID = "block-[name]"
_BLOCK_DEPENDENCIES = ["block-core", "block-dependency-2", ...]

def register_block():
    # Registration logic here
    
def unregister_block():
    # Unregistration logic here
```

### Block Registration Pattern
```python
# Block components are registered in a specific order: Loggers → Runtime Cache Members → Classes → Properties → Handlers
def register_block():
    register_block_components(_block_classes_to_register, Block_Logger_Definitions)
    bpy.types.Scene.my_property = bpy.props.PointerProperty(type=MY_PG)
    # Additional registration

def unregister_block():
    # Unregister in reverse order
    if hasattr(bpy.types.Scene, "my_property"):
        del bpy.types.Scene.my_property
    unregister_block_classes(_block_classes_to_register)
```

## Hook System Pattern

### Definition
The hook system allows blocks to trigger callbacks in other blocks without direct dependencies.

### Implementation
1. Block A defines a hook trigger function that calls all registered hook callbacks
2. Block B implements a hook callback function with the correct name
3. When triggered, Block A calls all matching hooks in other blocks

### Example
```python
# In block_event_listeners
def _trigger_frame_change_hook(context, type="PRE"):
    hook_name = f"hook_frame_change_{type.lower()}"
    _call_registered_hooks(hook_name, context)

# In another block
def hook_frame_change_pre(context):
    # This will be called automatically when frame changes
    return True
```

### Hook Metadata
- Each hook tracks success/failure statistics
- Hooks are called in order of block registration
- Failed hooks (return False) halt the hook chain

## Runtime Data Cache Pattern

### Purpose
Thread-safe, non-persistent storage for data that:
- Doesn't need to be saved with .blend files
- Needs to be accessed across different blocks
- Might be accessed from multiple threads

### Implementation
```python
# Store data
set_into_addon_runtime_cache("key", value)

# Retrieve data
data = get_from_addon_runtime_cache("key")

# Delete data
delete_from_addon_runtime_cache("key")
```

### Key Features
- Atomic operations (thread-safe)
- Option to copy retrieved data to prevent reference issues
- Organized with enum keys for better code organization
- Cleared on addon reload/register

## Logging Infrastructure Pattern

### Components
- Block-specific loggers with configurable levels
- Persistent log level settings saved with .blend files
- UI integration for adjusting log levels
- Automatic logger creation during block registration

### Usage
```python
# Define logger in block_constants.py
class Block_Logger_Definitions(Enum):
    MAIN = Block_Logger_Config("MyFeature Main", "INFO")

# Use in code
logger = get_logger(Block_Logger_Definitions.MAIN)
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

## UI Layout Patterns

### Panel Structure
```python
class ADDON_PT_Panel(bpy.types.Panel):
    bl_label = ""  # Empty, filled by draw_header
    bl_idname = f"{addon_bl_type_prefix}_PT_Panel_Name"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    
    def draw_header(self, context):
        uilayout_draw_block_panel_header(context, self.layout, "PANEL TITLE", doc_url)
        
    def draw(self, context):
        # Panel content here
```

### Helper Functions
- `uilayout_draw_block_panel_header`: Standardized panel headers with documentation links
- `create_ui_box_with_header`: Consistent box sections within panels
- `draw_wrapped_text`: Multi-line text display