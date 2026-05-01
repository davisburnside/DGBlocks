# Block Timer

A timer management system for Blender addons that provides persistent timer definitions with hook-based callbacks.

## Features

- **Persistent Timer Definitions**: Timer configurations are saved with the .blend file via scene properties
- **Runtime Cache Integration**: Timer metadata and instances are managed in the addon's runtime cache
- **Hook System**: Timers trigger `hook_timer_fire` callbacks in subscriber blocks
- **UI Management**: UIList interface in the N-panel for adding, removing, and configuring timers
- **Automatic Sync**: Scene properties and runtime cache are automatically synchronized on startup and updates

## Architecture

### Data Storage

1. **Scene Properties** (Source of Truth)
   - `DGBLOCKS_PG_Timer_Item`: Individual timer definition
     - `timer_name`: Unique identifier
     - `frequency_ms`: Fire interval in milliseconds
     - `is_enabled`: Active state
   - `DGBLOCKS_PG_Timer_Props`: Collection of all timers

2. **Runtime Cache** (Transient) — single RTC member
   - `TIMER_INSTANCES`: `Dict[str, Timer_Wrapper.Instance_Data]` — one entry per named timer.
     Each `Instance_Data` record holds all metadata (frequency, enabled state, fire stats,
     subscriber hook names) **and** the `bpy.app.timers` callable reference (`_timer_func`).
     This collapses the old two-member design into one, mirroring the `Wrapper_Hooks` pattern.

### Timer Wrapper

The `Timer_Wrapper` class follows the `Abstract_Feature_Wrapper` pattern and provides:

- `create_instance()`: Create a new timer
- `get_instance()`: Retrieve timer metadata
- `set_instance()`: Update timer properties (frequency, enabled state)
- `destroy_instance()`: Remove a timer
- `sync_scene_to_rtc()`: Synchronize scene data to runtime cache

### Hook System

Timers propagate the `hook_timer_fire` hook to subscriber blocks:

```python
def hook_timer_fire(context, timer_name: str):
    """Called when a timer fires"""
    # Your timer callback logic here
    return True
```

## Usage

### For Addon Users

1. Open the N-panel in the 3D viewport
2. Find the "TIMERS" panel
3. Click the "+" button to add a new timer
4. Configure the timer name and frequency (in milliseconds)
5. Toggle the checkbox to enable/disable the timer
6. The timer will fire at the specified interval and trigger any registered hooks

### For Block Developers

To respond to timer events in your block, implement the hook function:

```python
# In your block's __init__.py
def hook_timer_fire(context, timer_name: str):
    """Respond to timer events"""
    logger = get_logger(Your_Logger)
    logger.info(f"Timer '{timer_name}' fired!")
    
    # Your logic here
    # ...
    
    return True
```

To programmatically create/manage timers:

```python
from blocks_natively_included.block_timer.feature_timer_wrapper import Timer_Wrapper

# Create a timer
Timer_Wrapper.create_instance("my_timer", frequency_ms=1000, is_enabled=True)

# Update a timer
Timer_Wrapper.set_instance("my_timer", frequency_ms=2000)

# Get timer metadata
metadata = Timer_Wrapper.get_instance("my_timer")

# Remove a timer
Timer_Wrapper.destroy_instance("my_timer")
```

## Implementation Details

### Timer Lifecycle

1. **Registration**: Timer definitions are created in scene properties
2. **Initialization**: On addon startup, `hook_post_register_init` syncs scene data to RTC
3. **Activation**: Enabled timers are registered with `bpy.app.timers`
4. **Execution**: Timer callback updates metadata and propagates hooks
5. **Cleanup**: On unregister, all timers are stopped and cleaned up

### Synchronization

The sync process (`sync_scene_to_rtc`) ensures:
- Timers in scene but not in RTC are created
- Timers in RTC but not in scene are destroyed
- Timer properties (frequency, enabled state) are updated to match scene

### Update Callbacks

Scene property changes automatically trigger `sync_scene_to_rtc` via update callbacks:
- Changing timer name
- Changing frequency
- Toggling enabled state

## Dependencies

- `_block_core`: Core runtime cache, hooks, and logging systems

## Files

- `__init__.py`: Block registration, UI components, operators
- `block_constants.py`: Enums for loggers, hooks, and RTC members
- `feature_timer_wrapper.py`: Timer management wrapper class
- `README.md`: This documentation

## Notes

- Timer frequencies are specified in milliseconds but converted to seconds for Blender's timer API
- Timers automatically stop if disabled or removed from the scene
- The "count_subscriber_hooks" field shows how many blocks are listening to timer events
- Last fire time is displayed in milliseconds since epoch
