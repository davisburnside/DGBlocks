
from ...native_blocks.block_modal_events.data_structures import User_Input_Capture_Instance
from ...addon_helpers.data_structures import (
    Hook_Source_Declaration,
    Logger_Declaration,
    RTC_Member_Declaration,
    RTC_Member_Data_Mirror_Declaration,
    Shared_UIList_Declaration,
    String_Comparable_Mixin,
)
from .ui import _uilist_draw_selection_details, _uilist_draw_uilist_row

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Hook_Sources(String_Comparable_Mixin):
    # Pull-based: subscribers return a (single-element) list of Modal_Listener_Definition
    hook_get_modal_listener_definitions = Hook_Source_Declaration({})
    hook_get_workspace_tool_definitions = Hook_Source_Declaration({})
    # Compatibility source for declarations written before workspace tools became generic.
    hook_get_modal_workspace_tool_definitions = Hook_Source_Declaration({})

    # Broadcast: fired once at true router start / stop. Any block may subscribe.
    hook_modal_started = Hook_Source_Declaration({"context": any})
    hook_modal_ended   = Hook_Source_Declaration({"context": any, "reason": any})
    hook_modal_listener_ended = Hook_Source_Declaration(
        {"context": any, "reason": any, "listener_info": any}
    )


class Block_Loggers(String_Comparable_Mixin):
    MODAL_LIFECYCLE = Logger_Declaration("INFO")
    MODAL_EVENTS    = Logger_Declaration("INFO")


class Block_RTC_Members(String_Comparable_Mixin):
    LISTENERS = RTC_Member_Declaration()
    USER_INPUT_CAPTURE = RTC_Member_Declaration(User_Input_Capture_Instance())
    WORKSPACE_TOOLS = RTC_Member_Declaration()

class Block_Data_Mirrors(String_Comparable_Mixin):
    LISTENER_MIRROR = RTC_Member_Data_Mirror_Declaration(
        RTC_key                   = Block_RTC_Members.LISTENERS.name,
        FWC_name                  = "Wrapper_Modal_Manager",
        mirrored_key_field_names  = ["src_block_id"],
        mirrored_data_field_names = ["is_enabled"],
        scene_colprop_path        = "dgblocks_modal_events_props.listener_mirror",
    )


class Block_UIList_Configs(String_Comparable_Mixin):
    LISTENERS_UILIST = Shared_UIList_Declaration(
        col_names  = ["Source Block", "Priority", "Events", "Enabled"],
        col_widths = [4, 1, 1, 1],
        scene_parent_path                            = "dgblocks_modal_events_props",
        scene_colprop_path                           = "listener_mirror",
        scene_colprop_path_UIList_selection_idx_path = "listener_mirror_selected_idx",
        RTC_key                                      = Block_RTC_Members.LISTENERS,
        callback_draw_row             = _uilist_draw_uilist_row,
        callback_draw_details_section = _uilist_draw_selection_details,
    )
