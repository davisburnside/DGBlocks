# Block UI Display Modal

## Purpose
Provides a comprehensive system for creating and managing UI elements in the Blender 3D viewport using OpenGL and shader-based drawing. This block enables advanced visual feedback, overlays, and interactive elements beyond what Blender's standard UI system offers.

## Architecture
- `__init__.py`: Defines block registration and hook functions
- `rendered_ui_modal.py`: Implements the modal operator and drawing system
- `shader_wrapper.py`: Manages shader compilation and binding
- `draw_functions/`: Contains specialized drawing utilities
  - `alert_system.py`: Implements transient notifications
  - `my_draw_funcs_2d.py`: 2D drawing functions
  - `my_draw_funcs_3d.py`: 3D drawing functions
  - `shared_helper_functions.py`: Common drawing utilities
- `shaders/`: Contains GLSL shader code
  - `my_custom_shaders.py`: Custom shader definitions
  - `shared_custom_shaders.py`: Common shader utilities

## Key Features
- Real-time drawing in the 3D viewport
- Custom shader support for advanced visuals
- 2D UI elements (text, icons, shapes)
- 3D drawing capabilities (lines, shapes, meshes)
- Alert system for transient notifications
- Frame-by-frame updating

## Dependencies
- **Internal**: block-core, block-event-listeners
- **External**: bpy, gpu, mathutils, bgl

## Hook Functions
- `hook_post_register_init`: Initializes the modal system
- Various event hooks for responding to Blender events

## Public API
- Modal system activation/deactivation
- Alert display functions
- Drawing primitive functions
- Shader management

## Usage Notes
This block is valuable for addons that need to provide visual feedback directly in the 3D viewport, such as:
- Tool overlays showing measurements or guides
- Interactive manipulation handles
- Status displays and feedback
- Custom visualization of data
- Temporary drawing elements during operations
