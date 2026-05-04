# Block Data Enforcement

## Purpose
Provides systems to ensure data integrity and consistency across Blender sessions, including stable datablock IDs, Python library management, and datablock importing from blend files.

## Architecture
- `__init__.py`: Defines block properties, registration, and UI
- `block_constants.py`: Constants and cache keys
- `block_config.py`: Configuration settings
- `feature_stable_datablock_id.py`: Implements the stable ID system
- `feature_wrapper_library_import.py`: Manages external Python libraries
- `feature_datablock_import/`: Handles importing Blender datablocks

## Key Features
- **Stable Datablock IDs**: Assigns and maintains persistent IDs for Blender objects
- **Library Import**: Manages Python library dependencies
- **Datablock Import**: Imports Blender datablocks from external blend files
- **Object Modifier Stack**: Enforces consistent modifier stacks on objects

## Dependencies
- **Internal**: block-core, block-event-listeners
- **External**: bpy, threading

## Hook Functions
- `hook_post_register_init`: Initializes stable IDs and library registries
- `block_api_depsgraph_update_post`: Responds to depsgraph updates

## Public API
- Stable ID access: `object.dgblocks_object_stable_id_props.stable_id`
- Library management through UI operators
- Datablock import through the feature wrapper

## Usage Notes
This block is useful for addons that need to:
- Track objects across sessions
- Maintain object references after file operations
- Integrate external Python libraries
- Import Blender assets from external files

The stable ID system is particularly valuable for addons that need to maintain object references across file operations or sessions, as it provides a more reliable identifier than Blender's internal pointers or names.