
from ....addon_helpers.data_structures import Global_Addon_State, Hook_Source_Declaration, Logger_Declaration, RTC_Member_Declaration, RTC_Member_Data_Mirror_Declaration, Shared_UIList_Declaration, String_Comparable_Mixin
from ..core_helpers.ui import _uilist_blocks_draw_row, _uilist_blocks_draw_selection_details, _uilist_hooks_draw_row, _uilist_hooks_draw_selection_details, _uilist_loggers_draw_row

_BLOCK_ID = "block-core"

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS - Loggers, Hooks, & RTC (Runtime Cache) Members

class Core_Block_Loggers(String_Comparable_Mixin):
    HOOKS = Logger_Declaration("DEBUG")
    BLOCK_MGMT = Logger_Declaration("INFO")
    RTC_DATA_SYNC = Logger_Declaration("INFO")
    REGISTRATE = Logger_Declaration("INFO")
    POST_REGISTRATE = Logger_Declaration("INFO")
    UI = Logger_Declaration("WARNING")
    TRACKED_DATABLOCK_TYPES = Logger_Declaration("INFO")
    SCENE_MONITOR = Logger_Declaration("INFO")

class Core_Block_Hook_Sources(String_Comparable_Mixin):
    hook_core_event_undo = Hook_Source_Declaration({})
    hook_core_event_redo = Hook_Source_Declaration({})
    hook_post_startup = Hook_Source_Declaration()
    # SCENE_MONITOR_SCENE_CHANGED = Hook_Source_Declaration({"old_scene": str, "new_scene": str})
    # SCENE_MONITOR_ACTIVE_SCENE_CHANGED = Hook_Source_Declaration({"old_id": tuple, "new_id": tuple})
    # SCENE_MONITOR_ACTIVE_WORKSPACE_CHANGED = Hook_Source_Declaration({"old_id": tuple, "new_id": tuple})
    # SCENE_MONITOR_ACTIVE_MODE_CHANGED = Hook_Source_Declaration({"old_id": tuple, "new_id": tuple})
    # SCENE_MONITOR_ACTIVE_OBJ_CHANGED = Hook_Source_Declaration({"old_id": tuple, "new_id": tuple})

class Core_Runtime_Cache_Members(String_Comparable_Mixin): # no arg => empty list as default
    ADDON_METADATA = RTC_Member_Declaration(Global_Addon_State())
    REGISTRY_ALL_BLOCKS = RTC_Member_Declaration()
    REGISTRY_ALL_FWCS = RTC_Member_Declaration()
    REGISTRY_ALL_HOOK_SOURCES = RTC_Member_Declaration()
    REGISTRY_ALL_HOOK_SUBSCRIBERS = RTC_Member_Declaration({}) # dict, not list
    REGISTRY_ALL_LOGGERS = RTC_Member_Declaration()
    REGISTRY_ALL_DATA_MIRRORS = RTC_Member_Declaration()
    META_REGISTRIES_BEING_SYNCED = RTC_Member_Declaration()
    SHARED_UILIST_CONFIGS = RTC_Member_Declaration()

class Core_Data_Mirrors(String_Comparable_Mixin):
    BLOCKS_LIST = RTC_Member_Data_Mirror_Declaration(
        RTC_key = "REGISTRY_ALL_BLOCKS",
        FWC_name = "Wrapper_Control_Plane",
        mirrored_key_field_names = ["block_id"],
        mirrored_data_field_names = ["is_valid", "error_message", "is_block_enabled"],
        scene_colprop_path = None, # Non-standard, 1-direction sync
    )
    HOOKS_LIST = RTC_Member_Data_Mirror_Declaration(
        RTC_key = "REGISTRY_ALL_HOOK_SOURCES",
        FWC_name = "Wrapper_Hooks",
        mirrored_key_field_names = ["hook_func_name",], 
        mirrored_data_field_names = ["src_block_id", "is_hook_enabled"],
        scene_colprop_path = "dgblocks_core_props.managed_hooks",
    )
    LOGGERS_LIST = RTC_Member_Data_Mirror_Declaration(
        RTC_key = "REGISTRY_ALL_LOGGERS",
        FWC_name = "Wrapper_Loggers",
        mirrored_key_field_names = ["logger_name"], 
        mirrored_data_field_names = ["level_name", "src_block_id"],
        scene_colprop_path = "dgblocks_core_props.managed_loggers",
    )


class Core_UIList_Configs(String_Comparable_Mixin):
    LOGGERS_UILIST = Shared_UIList_Declaration(
        col_names = ["Logger", "Source Block", "Level"],
        col_widths = [3, 3, 2],
        scene_parent_path = "dgblocks_core_props",
        scene_colprop_path = "managed_loggers",
        scene_colprop_path_UIList_selection_idx_path = "managed_loggers_selected_idx",
        RTC_key = "REGISTRY_ALL_LOGGERS",
        callback_draw_row = _uilist_loggers_draw_row,
        callback_draw_details_section = None
    )
    HOOKS_UILIST = Shared_UIList_Declaration(
        col_names = ["Function Name", "Source Block", "Subs", "Runs", "Enabled"],
        col_widths = [3, 3, 1, 1, 1],
        scene_parent_path = "dgblocks_core_props",
        scene_colprop_path = "managed_hooks",
        scene_colprop_path_UIList_selection_idx_path = "managed_hooks_selected_idx",
        RTC_key = "REGISTRY_ALL_HOOK_SOURCES",
        callback_draw_row = _uilist_hooks_draw_row,
        callback_draw_details_section = _uilist_hooks_draw_selection_details
    )
    BLOCKS_UILIST = Shared_UIList_Declaration(
        col_names = ["Status", "Block Name", "Version",],
        col_widths = [1, 4, 2],
        scene_parent_path = "dgblocks_core_props",
        scene_colprop_path = "managed_blocks",
        scene_colprop_path_UIList_selection_idx_path = "managed_blocks_selected_idx",
        RTC_key = "REGISTRY_ALL_BLOCKS",
        callback_draw_row = _uilist_blocks_draw_row,
        callback_draw_details_section = _uilist_blocks_draw_selection_details
    )
    
