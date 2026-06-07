import bpy
from ..core_features.control_plane.data_structures import DGBLOCKS_PG_Block_Record
from ..core_features.hooks.data_structures import DGBLOCKS_PG_Hook_Reference
from ..core_features.loggers.data_structures import DGBLOCKS_PG_Logger_Instance

class DGBLOCKS_PG_Core_Props(bpy.types.PropertyGroup):
    
    # The "lights-off switch". When false, all addon features should be disabled. The only available action should be to toggle this value
    addon_is_active: bpy.props.BoolProperty(default = False, name = "Addon is Enabled?") # type: ignore
    
    # General settings
    documentation_weblinks_enabled: bpy.props.BoolProperty(default = True, name = "Enable [ ? ] Webpage Links") # type: ignore  
    
    # Enables extra UI options for debugging. Most properties & functions that begin with "debug_" are not used when this value is false
    debug_mode_enabled: bpy.props.BoolProperty(default = False, name = "Is in Debug Mode?") # type: ignore
    
    # When true, all sync actions for create/edit/move/remove actions are printed to the console:
    debug_log_all_RTC_BL_sync_actions: bpy.props.BoolProperty(default = False)# type: ignore

    # Empties all CollectionProps created by this addon eveyr startup
    debug_clear_BL_data_on_startup: bpy.props.BoolProperty(default = False)# type: ignore

    # --------------------------------------------------------------
    # Persistent, undo/redo-enabled Scene data for each feature-wrapper's mirrored  RTC data
    # More info for structure/metadata is found inside each DGBLOCKS_* class
    # --------------------------------------------------------------
    managed_blocks: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Block_Record) # type: ignore
    managed_blocks_selected_idx: bpy.props.IntProperty() # type: ignore
    managed_hooks: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Hook_Reference)  # type: ignore
    managed_hooks_selected_idx: bpy.props.IntProperty()  # type: ignore
    managed_loggers_selected_idx: bpy.props.IntProperty()  # type: ignore
    managed_loggers: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Logger_Instance) # type: ignore
