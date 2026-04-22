
import os
import threading
import bpy # type: ignore

from ..addon_config import (
        addon_name, 
        addon_title,
        addon_bl_type_prefix,
        should_show_developer_ui_panels,
        Documentation_URLs)

from ...blocks_natively_included import _block_core
from ..blocks_natively_included._block_core.core_feature_runtime_cache import Wrapper_Runtime_Cache
from ..blocks_natively_included._block_core.core_helper_uilayouts import uilayout_draw_block_panel_header, ui_box_with_header
from ..blocks_natively_included._block_core.core_helper_functions import register_block_components, unregister_block_components
from ..blocks_natively_included._block_core.core_feature_logs import get_logger
from ..blocks_natively_included._block_core.core_block_constants import (Core_Block_Loggers)

from .. import block_event_listeners

from .. import block_data_enforcement
from ..block_data_enforcement.feature_library_import.library_installation_wrapper import Library_Installation_Wrapper
from ..block_data_enforcement.block_constants import Python_Library_Dependencies

from . import feature_numba_function_wrapper
from .block_constants import Block_Logger_Definitions, Enum_Runtime_Cache_Keys

#================================================================
# BLOCK DATA - A unique ID & list of Dependencies is required for every Block
# =============================================================================

_BLOCK_ID = "block-numba-accelerate"
_BLOCK_DEPENDENCIES = [
    _block_core._BLOCK_ID,
    block_event_listeners._BLOCK_ID
]

#================================================================
# INIT EVENTS - Called after register_block() finishes & bpy.context is fully usable
# This function is automatically called by event_listeners
#================================================================

def hook_post_register_init(context):
    """
    Initialize numba acceleration system after addon registration.
    Sets up function registry and cache directory.
    """
    logger = get_logger(Core_Block_Loggers.POST_REGISTRATE)
    
    # Initialize function registry in runtime cache
    Wrapper_Runtime_Cache.set_instance(Enum_Runtime_Cache_Keys.NUMBA_FUNCTION_REGISTRY, {})
    
    # Ensure numba cache directory exists if base folder is valid
    feature_numba_function_wrapper._ensure_numba_cache_dir()
    
    # Pre-import numba decorators if available
    feature_numba_function_wrapper.get_numba_imports()
    
    logger.info(f"Initialized numba acceleration system")
    return True

# =============================================================================
# DATABLOCKS - Attached to Scene
# Stores state info of each listener type
# =============================================================================

class DGBLOCKS_PG_Scene_Numba_Acceleration_Props(bpy.types.PropertyGroup):
    """
    Scene properties for numba acceleration configuration.
    """
    is_enabled: bpy.props.BoolProperty(
        name="Enable Numba Acceleration", 
        description="Enable numba JIT compilation for supported functions (requires numba to be installed)",
        default=False
    ) # type: ignore

#=================================================================================
# OPERATORS
#=================================================================================

class DGBLOCKS_OT_Numba_Cache_Operations(bpy.types.Operator):
    """
    Operator for managing numba cache operations.
    """
    bl_idname = "dgblocks.numba_cache_operations"
    bl_label = "Numba Cache Operations"
    bl_description = "Manage numba compilation cache"
    
    action: bpy.props.EnumProperty(
        items=[
            ('CLEAR', "Clear Cache", "Clear all numba compiled code cache"),
            ('OPEN', "Open Folder", "Open the numba cache folder in file explorer"),
        ],
        default='CLEAR'
    ) # type: ignore
    
    @classmethod
    def poll(cls, context):
        return context.scene.dgblocks_core_props.addon_is_active
    
    def execute(self, context):
        logger = get_logger(Block_Logger_Definitions.NUMBA_CACHE)
        
        if self.action == 'CLEAR':
            success = feature_numba_function_wrapper._clear_numba_cache()
            if success:
                self.report({'INFO'}, "Numba cache cleared successfully")
            else:
                self.report({'WARNING'}, "Failed to clear numba cache")
            
        elif self.action == 'OPEN':
            cache_dir = feature_numba_function_wrapper._get_numba_cache_dir()
            if not cache_dir or not os.path.exists(cache_dir):
                self.report({'ERROR'}, "Cache directory does not exist")
                return {'CANCELLED'}
            
            # Reuse the open folder operator from block_data_enforcement
            bpy.ops.dgblocks.open_folder(folder_path=cache_dir)
        
        return {'FINISHED'}

#================================================================
# UI
#================================================================

def uilayout_draw_main_panel(context, layout):
    """
    Draw the main numba acceleration panel.
    """
    scene = context.scene
    props = scene.dgblocks_numba_accelerate_props
    
    # Check numba status
    is_numba_installed = Library_Installation_Wrapper.is_installed("numba")
    
    # Main settings box
    settings_box = ui_box_with_header(context, layout, "Numba Acceleration")
    
    # Numba status and install button
    status_row = settings_box.row()
    
    if is_numba_installed:
        status_row.label(text="Numba is installed", icon='CHECKMARK')
    else:
        status_row.label(text="Numba is not installed", icon='ERROR')
        
        # Show install button (links to library manager)
        op_row = settings_box.row()
        op_row.operator(
            "dgblocks.library_manager",
            text="Install Numba",
            icon='IMPORT'
        ).library_name = Python_Library_Dependencies.NUMBA.value[0]
        op_row.enabled = True
        
        # Can't enable numba if it's not installed
        settings_box.label(text="Install numba to enable acceleration")
        settings_box.enabled = False
        return
    
    # Enable/disable toggle
    toggle_row = settings_box.row()
    toggle_row.prop(props, "is_enabled")
    
    # Cache info
    cache_dir = feature_numba_function_wrapper._get_numba_cache_dir()
    
    cache_box = ui_box_with_header(context, layout, "Compilation Cache")
    if cache_dir and os.path.exists(cache_dir):
        cache_box.label(text=f"Cache directory:", icon='FILE_FOLDER')
        path_row = cache_box.row()
        path_row.label(text=cache_dir)
        
        # Cache operations
        op_row = cache_box.row(align=True)
        op_row.operator(
            "dgblocks.numba_cache_operations", 
            text="Clear Cache", 
            icon='TRASH'
        ).action = 'CLEAR'
        
        op_row.operator(
            "dgblocks.numba_cache_operations", 
            text="Open Folder", 
            icon='FILEBROWSER'
        ).action = 'OPEN'
    else:
        cache_box.label(text="No cache directory available", icon='INFO')
        cache_box.label(text="Set addon_saved_data_folder in preferences")
    
    # Function registry
    registry = feature_numba_function_wrapper.Wrapper_Runtime_Cache.get_instance(
        Enum_Runtime_Cache_Keys.NUMBA_FUNCTION_REGISTRY
    )
    
    if registry and len(registry) > 0:
        func_box = ui_box_with_header(context, layout, "Registered Functions")
        for func_name, func_data in registry.items():
            row = func_box.row()
            
            # Show with icon based on compilation status
            has_compiled = func_data.get('compiled') is not None
            icon = 'CHECKMARK' if has_compiled else 'DOT'
            status = " (compiled)" if has_compiled else ""
            
            row.label(text=f"{func_name}{status}", icon=icon)

class DGBLOCKS_PT_Numba_Accelerate_Default_Panel(bpy.types.Panel):
    bl_label = ""
    bl_idname = f"{addon_bl_type_prefix}_PT_Numba_Accelerate_Default_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = addon_title
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return should_show_developer_ui_panels and context.scene.dgblocks_core_props.addon_is_active
    
    def draw_header(self, context):
        uilayout_draw_block_panel_header(
            context, self.layout, 
            _BLOCK_ID.upper(), 
            Documentation_URLs.MY_PLACEHOLDER_URL_2, 
            icon_name="SCRIPTPLUGINS"
        )
    
    def draw(self, context):
        uilayout_draw_main_panel(context, self.layout)

#================================================================
# REGISTRATION EVENTS - Should only called from the addon's main __init__.py
#================================================================

# Only bpy.types.* classes should be registered
_block_classes_to_register = [
        DGBLOCKS_PG_Scene_Numba_Acceleration_Props,
        DGBLOCKS_OT_Numba_Cache_Operations,
        DGBLOCKS_PT_Numba_Accelerate_Default_Panel]

def register_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.log_with_linebreak(f"Starting registration for '{_BLOCK_ID}'")
    
    register_block_components(classes = _block_classes_to_register, loggers = Block_Logger_Definitions)
    
    bpy.types.Scene.dgblocks_numba_accelerate_props = bpy.props.PointerProperty(type=DGBLOCKS_PG_Scene_Numba_Acceleration_Props) 
    
    logger.info(f"Finished registration for '{_BLOCK_ID}'")

def unregister_block():
    
    logger = get_logger(Core_Block_Loggers.REGISTRATE)
    logger.debug(f"Starting unregistration for '{_BLOCK_ID}'")
    
    unregister_block_components(_block_classes_to_register)

    # Delete Scene Properties
    if hasattr(bpy.types.Scene, "dgblocks_numba_accelerate_props"):
        del bpy.types.Scene.dgblocks_numba_accelerate_props
        
    logger.info(f"Finished unregistration for '{_BLOCK_ID}'")