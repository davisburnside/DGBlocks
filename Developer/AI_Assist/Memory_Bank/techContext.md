# DGBlocks Technical Context

## Core Technologies

### Blender & Python Requirements
- Blender 5.0+ (as specified in bl_info)
- Python 3.10+ (as included with Blender 5.0)
- Blender Python API (bpy)

### Standard Library Dependencies
- `threading`: For thread-safe operations
- `logging`: Logging infrastructure
- `importlib`: For dynamic module reloading
- `enum`: For type-safe constants and options
- `os`, `sys`: For file and system operations
- `datetime`: For timestamp operations
- `typing`: For type annotations

### Optional External Dependencies
- **Numba**: For code acceleration (JIT compilation)
- Other Python libraries can be integrated via the library import system

## Key Subsystems

### Addon Registration System
- Standardized block registration/unregistration
- Recursive module reloading
- Dependency validation
- Post-registration initialization

### Runtime Data Cache
- Thread-safe global data store
- Key-based storage with enum-based organization
- Support for complex data types
- Non-persistent (cleared on register/reload)

### Logging System
- Configurable log levels per logger
- UI integration for log level adjustment
- Persistent log settings
- Contextual logging with source identification

### Event Listener System
- Wraps Blender's event handlers (app.handlers)
- Configurable activation/deactivation
- Event filtering and propagation control
- Hook-based callback mechanism

### Data Enforcement System
- Stable datablock IDs across sessions
- Support for library/module imports
- DataBlock import capabilities (from blend files)

### UI Modal Display System
- Custom drawing in 3D viewport
- Shader support
- Alert system

## File Structure and Organization

### Main Addon Files
- `__init__.py`: Main registration point
- `addon_config.py`: Configuration settings
- `addon_blocks_to_register.py`: Block registration order

### Block Naming Convention
- Block packages: `block_[feature_name]`
- Core block: `_block_core`
- Block files:
  - `__init__.py`: Main block definition
  - `block_constants.py`: Constants and enums
  - `block_config.py`: User configuration
  - `feature_[name].py`: Feature implementations
  - `helper_[name].py`: Helper functions

### Code Organization Patterns
- Sections marked with `#=== SECTION NAME ===`
- Code grouped by function type (properties, operators, UI, etc.)
- Constants and configuration at the top of files
- Hooks and callbacks clearly labeled

## Naming Conventions

### Variables
- `ALL_CAPS`: Constants, not meant to be modified
- `_leading_underscore`: Internal use, not for external access
- `my_*`: User-modifiable configuration values
- `camelCase`: Often used for bpy property names

### Functions
- `get_*`: Simple retrievals with minimal computation
- `determine_*`: Complex retrievals with computation
- `callback_*`: Event callback functions
- `uilayout_*`: UI drawing functions
- `hook_*`: Hook callback functions

### Classes
- Blender-specific class prefixes:
  - `PG_`: Property Group
  - `OT_`: Operator
  - `PT_`: Panel
  - `MT_`: Menu

## Development Workflow

### Adding Features
1. Create new block package following structure pattern
2. Implement required registration functions
3. Add to `addon_blocks_to_register.py`
4. Implement hook functions as needed
5. Add block-specific logging

### Debugging Techniques
- Use block-specific loggers at appropriate levels
- Leverage the debug panels in the UI
- Check the console for registration issues
- Use the runtime data cache inspection tools