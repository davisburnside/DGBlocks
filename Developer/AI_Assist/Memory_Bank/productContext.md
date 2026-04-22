# DGBlocks Product Context

## How the Block System Works

### Block Definition
Each "block" is a Python package with a standardized structure:
- `__init__.py` with required variables:
  - `_BLOCK_ID`: Unique identifier for the block
  - `_BLOCK_DEPENDENCIES`: List of other block IDs this block depends on
  - `register_block()`: Function to register all components
  - `unregister_block()`: Function to unregister all components
- Optional hook callback functions that respond to events from other blocks
- Additional modules that implement the block's functionality

### Registration Flow
1. Main addon `__init__.py` registers blocks in dependency order
2. Each block registers its bpy.types classes, properties, and handlers
3. Post-registration callbacks initialize blocks once bpy.context is available
4. During runtime, blocks communicate through hooks and the shared runtime cache

### Hook System
- One-directional callbacks between blocks
- Example: When block-event-listener detects a frame change, it can trigger callbacks in any block with a matching hook function
- Standardized hook naming: `hook_[event_name]`
- Returns boolean (True for success, False for failure)
- Execution is serial in a predetermined order

## Developer Experience

### Adding Features
1. Create a new block package with standard structure
2. Register the block in `addon_blocks_to_register.py`
3. Implement desired functionality within the block
4. Define hooks for interaction with other blocks (optional)

### Removing Features
1. Remove block from `addon_blocks_to_register.py`
2. Delete the block package (or keep it inactive)
3. No code changes needed in other blocks (due to hook system design)

### Customizing
- Update template names and variables
- Modify UI elements as needed
- Configure loggers for debugging
- Add block-specific properties to Blender objects

## Problems Solved

### Code Organization
- Clear separation between different features
- Standardized structure makes code navigation intuitive
- Reduced cognitive load when working on complex addons

### Dependency Management
- One-way dependencies prevent circular references
- Explicit dependency declaration in each block
- Support for both Python libraries and Blender data dependencies

### Feature Isolation
- Issues in one block don't cascade to others
- Features can be developed and tested independently
- Teams can work on different blocks simultaneously

### Data Persistence
- Clear distinction between persistent data (saved in .blend files)
- Non-persistent data managed through runtime cache
- Thread-safe runtime data storage

### Debugging
- Comprehensive logging system with configurable levels
- Debug panels and operators for inspecting state
- Clear error reporting during registration and runtime