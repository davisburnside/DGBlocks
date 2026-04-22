# Block Event Listeners

## Purpose
Provides a standardized system for listening to Blender events and propagating them to other blocks through hook functions. This block serves as the event backbone of the addon, enabling other blocks to respond to Blender events without directly registering handlers.

## Architecture
- `__init__.py`: Defines block properties, registration, and UI
- `block_constants.py`: Event type definitions and constants
- `feature_generic_listener_wrapper.py`: Implements the event listener and hook system

## Key Features
- Wraps Blender's app.handlers events into a unified system
- Enables/disables individual event listeners through UI
- Propagates events to hooks in other blocks
- Tracks and reports event statistics
- Filters high-frequency events to prevent performance issues

## Supported Events
- Depsgraph updates (pre/post)
- Frame change (pre/post)
- Undo/Redo (pre/post)
- Save (pre/post)
- Bake (pre/post)
- Composite (pre/post)

## Dependencies
- **Internal**: block-core
- **External**: bpy

## Hook Functions
- `hook_post_register_init`: Initializes event listeners after addon registration
- `hook_debug_get_state_data_to_print`: Provides debugging information
- `hook_debug_uilayout_draw_console_print_settings`: Renders debug UI

## Public API
All interaction with this block should happen through hook functions:

```python
# In your block's __init__.py:
def hook_frame_change_pre(context):
    # This will be called when a frame change event occurs
    return True

def hook_depsgraph_post(context, depsgraph):
    # This will be called after the dependency graph updates
    return True
```

## Usage Notes
This block is essential for any addon that needs to respond to Blender events. It centralizes event handling and provides a clean interface for other blocks to hook into specific events.