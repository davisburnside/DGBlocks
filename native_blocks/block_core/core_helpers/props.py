import bpy
from ..core_features.control_plane.data_structures import DGBLOCKS_PG_Block_Record
from ..core_features.hooks.data_structures import DGBLOCKS_PG_Hook_Reference
from ..core_features.hooks.helpers import _callback_hook_sub_uilist_selection_idx_updated, _callback_hooks_hide_unsub_changed
from ..core_features.loggers.data_structures import DGBLOCKS_PG_Logger_Instance, _callback_logger_include_datetime_changed

class DGBLOCKS_PG_Core_Props(bpy.types.PropertyGroup):
    
    # The "lights-off switch". When false, all addon features should be disabled. The only available action should be to toggle this value
    addon_is_active: bpy.props.BoolProperty(default = False, name = "Addon is Enabled?") # type: ignore
    
    # General settings
    documentation_weblinks_enabled: bpy.props.BoolProperty(default = True, name = "Enable [ ? ] Webpage Links") # type: ignore  
    
    # When true, all sync actions for create/edit/move/remove actions are printed to the console:
    debug_log_all_RTC_BL_sync_actions: bpy.props.BoolProperty(default = False)# type: ignore

    # Empties all CollectionProps created by this addon eveyr startup
    debug_clear_BL_data_on_startup: bpy.props.BoolProperty(default = False)# type: ignore

    # Hooks subpanel filter: hide hook sources that have no subscribers
    hooks_hide_unsub: bpy.props.BoolProperty(  # type: ignore
        default = True,
        name    = "Hide hooks with no subscribers",
        update  = _callback_hooks_hide_unsub_changed,
    )

    # In the "All Loggers" panel: datetime prefix for log lines
    # None = no timestamp, Condensed = short timestamp, Full = full datetime, Raw = unix timestamp
    logger_include_datetime: bpy.props.EnumProperty(  # type: ignore
        name = "Include Datetime",
        description = "Show a datetime prefix on log lines",
        items = [
            ("NONE", "None", "No timestamp on log lines"),
            ("CONDENSED", "Condensed", "Short HH:MM:SS timestamp"),
            ("FULL", "Full", "Full YYYY-MM-DD HH:MM:SS timestamp"),
            ("RAW", "Raw Timestamp", "Raw unix timestamp"),
        ],
        default = "NONE",
        update = _callback_logger_include_datetime_changed,
    )

    # --------------------------------------------------------------
    # Persistent, undo/redo-enabled Scene data for each feature-wrapper's mirrored  RTC data
    # More info for structure/metadata is found inside each DGBLOCKS_* class
    # --------------------------------------------------------------
    managed_blocks: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Block_Record) # type: ignore
    managed_blocks_selected_idx: bpy.props.IntProperty() # type: ignore
    managed_hooks: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Hook_Reference)  # type: ignore
    managed_hooks_selected_idx: bpy.props.IntProperty(update = _callback_hook_sub_uilist_selection_idx_updated)  # type: ignore
    managed_loggers_selected_idx: bpy.props.IntProperty()  # type: ignore
    managed_loggers: bpy.props.CollectionProperty(type=DGBLOCKS_PG_Logger_Instance) # type: ignore
