# Block Stable Modal

A stable modal operator system for Blender addons that provides hook-based keyboard, mouse, and area-change event routing to downstream blocks.

## Features

- **Persistent Modal Configuration**: Settings are saved with the .blend file via scene properties
- **Runtime Cache Integration**: Modal metadata and state are managed in the addon's runtime cache
- **Hook System**: Modal triggers event callbacks in downstream blocks via three distinct hooks
- **Automatic Restart**: The "stable" designation means the modal auto-restarts on crash/error
- **Area Change Detection**: Detects when the mouse enters a new context.area
- **Smart Return Aggregation**: Multiple downstream hooks can control modal behavior

## Architecture

### Data Storage

1. **Scene Properties** (Source of Truth)
   - `DGBLOCKS_PG_Modal_Props`: Modal configuration
     - `is_enabled`: Whether modal is active
     - `should_be_activated_after_startup`: Auto-start on load
     - `should_restart_on_error`: Auto-restart on crash (the "stable" feature)

2. **Runtime Cache** (Transient) — single RTC member
   - `MODAL_INSTANCE`: Single `Modal_Instance_Data` record holding:
     - Enabled state, running status, event statistics
     - Crash/restart tracking
     - Area tracking for area-change events
     - Operator instance reference

### Modal Wrapper

The `Modal_Wrapper` class follows the `Abstract_Feature_Wrapper` pattern and provides:

- `create_instance()`: Initialize the modal
- `get_instance()`: Retrieve modal metadata
- `set_instance()`: Update modal state (enabled/disabled)
- `destroy_instance()`: Remove the modal
- `sync_scene_to_rtc()`: Synchronize scene data to runtime cache
- `start_modal()` / `stop_modal()`: Manual control

### Hook System

The modal propagates three distinct hooks to downstream blocks:

#### 1. Keyboard Events
```python
def hook_modal_key_event(context, event):
    """Called on keyboard events"""
    if event.type == 'G' and event.value == 'PRESS':
        # Handle G key press
        return {'FINISHED'}  # Optional: control modal behavior
    return {'PASS_THROUGH'}  # Default: let event pass through
```

#### 2. Mouse Events
```python
def hook_modal_mouse_event(context, event):
    """Called on mouse events"""
    if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
        # Handle left click
        return {'PASS_THROUGH'}
    return {'PASS_THROUGH'}
```

#### 3. Area Change Events
```python
def hook_modal_area_change(context, event, old_area, new_area):
    """Called when mouse enters a new area"""
    print(f"Changed from {old_area.type} to {new_area.type}")
    return {'PASS_THROUGH'}
```

### Return Value Aggregation

The modal operator intelligently handles return values from multiple downstream hooks:

- **Default**: `{'PASS_THROUGH'}` — allows all Blender operations to continue
- **Override**: If ANY hook returns `{'FINISHED'}`, `{'CANCELLED'}`, or `{'RUNNING_MODAL'}`, the **first non-PASS_THROUGH value** is used
- This gives downstream blocks control when needed, without blocking by default

## Usage

### For Addon Users

1. Open the N-panel in the 3D viewport
2. Find the "BLOCK-STABLE-MODAL" panel
3. Toggle "Modal Enabled" to start/stop
4. Configure auto-start and auto-restart behavior
5. View runtime statistics (event counts, restart count)

### For Block Developers

To respond to events in your block, implement the hook functions in your block's `__init__.py`:

```python
# In your block's __init__.py

def hook_modal_key_event(context, event):
    """Respond to keyboard events"""
    logger = get_logger(Your_Logger)
    
    # Example: Trigger action on spacebar
    if event.type == 'SPACE' and event.value == 'PRESS':
        logger.info("Spacebar pressed!")
        # Your logic here
        return {'FINISHED'}  # Consume the event
    
    return {'PASS_THROUGH'}  # Let other blocks handle it

def hook_modal_mouse_event(context, event):
    """Respond to mouse events"""
    if event.type == 'MOUSEMOVE':
        # Track mouse position
        mouse_x = event.mouse_region_x
        mouse_y = event.mouse_region_y
        # Your logic here
    
    return {'PASS_THROUGH'}

def hook_modal_area_change(context, event, old_area, new_area):
    """Respond to area changes"""
    if new_area.type == 'VIEW_3D':
        # Mouse entered 3D viewport
        # Your logic here
        pass
    
    return {'PASS_THROUGH'}
```

### Programmatic Control

```python
from blocks_natively_included.block_stable_modal.feature_modal_wrapper import Modal_Wrapper

# Start the modal
Modal_Wrapper.start_modal(context)

# Stop the modal
Modal_Wrapper.stop_modal(context)

# Get modal status
modal_data = Modal_Wrapper.get_instance()
if modal_data and modal_data.is_running:
    print("Modal is active!")

# Update modal settings
Modal_Wrapper.set_instance(is_enabled=False)
```

## Use Cases

### 🎯 Interactive Tools
- Custom manipulation handles with real-time feedback
- Gizmo systems for complex parameter control
- Visual snapping systems during operations
- Interactive measurement tools

### 🎨 Viewport Drawing
- Custom cursor overlays showing tool state
- Brush preview systems with parameter displays
- Framing guides (rule-of-thirds, golden ratio)
- Debug visualizations (ray casts, bounds, normals)

### 📊 Real-time Monitoring
- Performance overlays (FPS, memory, render stats)
- Animation playback HUD
- Data visualization updates
- Sensor/telemetry displays

### 🎓 User Guidance
- Interactive tutorials with highlighted UI elements
- Context-sensitive help and shortcuts
- Onboarding flows for complex addons
- Tooltip systems

### 🎮 Input Systems
- Gesture recognition (detect mouse patterns)
- Macro recording and playback
- Context-aware custom shortcuts
- Spatial navigation for 3D mice / VR

### 🔧 Development Tools
- State inspection overlays
- Profiling displays
- Debug information rendering
- Property monitoring during development

### 🤝 Collaboration
- Multi-user cursor displays (networked addons)
- Annotation and markup tools
- Session recording for training
- Live collaboration indicators

## Implementation Details

### Modal Lifecycle

1. **Registration**: Modal configuration is created in scene properties
2. **Initialization**: On addon startup, `hook_post_register_init` syncs scene → RTC
3. **Activation**: Modal operator is invoked and begins event routing
4. **Execution**: Each event is routed to appropriate hooks (key/mouse/area)
5. **Error Handling**: If modal crashes and `should_restart_on_error=True`, auto-restart after 0.1s
6. **Cleanup**: On unregister, modal is stopped and RTC is cleared

### Synchronization

The sync process (`sync_scene_to_rtc`) ensures:
- Modal instance is created if missing
- Modal enabled state matches scene property
- Modal starts/stops based on configuration changes

### Update Callbacks

Scene property changes automatically trigger `sync_scene_to_rtc` via update callbacks:
- Toggling `is_enabled` starts/stops the modal immediately

### Stability Features

**Auto-restart on Error**: When `should_restart_on_error=True`:
- Exceptions in the modal's event handler are caught
- Modal is flagged for restart
- A timer schedules restart after 0.1 seconds
- Restart count is incremented and displayed in UI

**Auto-start on Load**: When `should_be_activated_after_startup=True`:
- Post-register init checks if modal should be running
- If not running but should be, starts automatically
- Ensures modal is always active when expected

## Dependencies

- `_block_core`: Core runtime cache, hooks, and logging systems

## Files

- `__init__.py`: Block registration, operators, UI components, modal operator
- `block_constants.py`: Enums for loggers, hooks (KEY/MOUSE/AREA), and RTC members
- `feature_modal_wrapper.py`: Modal management wrapper class
- `helper_functions.py`: UI drawing and operator execution logic
- `README.md`: This documentation

## Notes

- The modal uses `{'PASS_THROUGH'}` by default, making it non-blocking
- Only ONE modal instance exists per addon (unlike timers which can have multiple)
- Event statistics are tracked: successes, failures, restarts
- Area change detection only fires when transitioning between different areas
- The modal automatically stops if disabled or flagged via `is_running=False`

## Comparison with block-stable-timers

| Feature | block-stable-timers | block-stable-modal |
|---------|--------------------|--------------------|
| **Instance Count** | Multiple timers | Single modal |
| **Dataclass** | Timer_Instance_Data | Modal_Instance_Data |
| **Hooks Provided** | `hook_timer_fire` | `hook_modal_key_event`<br>`hook_modal_mouse_event`<br>`hook_modal_area_change` |
| **Trigger Type** | Time-based (frequency_ms) | Event-based (user input) |
| **Scene UI** | UIList of timers | Simple enable/disable toggles |
| **Auto-restart** | On crash during fire | On crash during event handling |

Both blocks follow the same `Abstract_Feature_Wrapper` pattern and provide "stable" (auto-restarting) functionality for predictable, crash-resistant addon behavior.
