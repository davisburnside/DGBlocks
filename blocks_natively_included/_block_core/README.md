# Block Core

## Purpose
Provides core functionality and infrastructure for all blocks in the addon, including logging, runtime data caching, registration lifecycle management, and UI utilities.

## Architecture
- `__init__.py`: Handles registration/unregistration and defines hook callbacks
- `block_constants.py`: Defines enumerations and constants
- `feature_logging.py`: Logging system implementation
- `feature_block_hooks.py`: Post-registration initialization
- `feature_runtime_data_cache.py`: Thread-safe data cache
- `helper_functions.py`: General utility functions
- `helper_debug_functions.py`: Debug-specific utilities
- `helper_uilayout_templates.py`: UI layout utilities

## Key Features: Each has a dedicated feature-wrapper
- Multi-logger system: a global registry of loggers for each block. Stores log-level data in Blender's Scene Datablock
- Hooks (callback functions) system: call functions in downstream-dependant blocks. Stores hook metadata in Blender's Scene Datablock
- Runtime Cache (RTC): Thread-safe python data cache, reset upon load/reload/new file. Stores no data in Blender
- Core Events: Init, Undo, & Redo handlers to ensure RTC remains synced & up-to-date. Stores no data in Blender. Causes hook functions to trigger for those 3 events in other downstream blocks

## Other Features
- UI utilities and templates
- Debug tools and console output

## Dependencies
- **Internal**: None (core block has no dependencies)
- **External**: bpy, threading, logging, importlib, enum

## Hook Functions
- `hook_debug_get_state_data_to_print`: Provides debugging data
- `hook_debug_uilayout_draw_console_print_settings`: Debug UI

## Public API
- `get_logger(logger)`: Access the logging system
- `Wrapper_Runtime_Cache.get_cache(key)`: Retrieve data from cache
- `Wrapper_Runtime_Cache.set_cache(key, value)`: Store data in cache
- `register_block_components(classes)`: Register block components
- `unregister_block_components(classes)`: Unregister block components

## Usage Notes
This block is required by all other blocks and should never be removed from the project. It provides the fundamental infrastructure that enables the modular block system to function.