

from ...addon_helpers.data_structures import Hook_Source_Declaration, Logger_Declaration, RTC_Member_Declaration, RTC_Member_Data_Mirror_Declaration, Shared_UIList_Declaration, String_Comparable_Mixin
from ..block_onscreen_drawing.ui import _uilist_draw_selection_details, _uilist_draw_uilist_row

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Hook_Sources(String_Comparable_Mixin):
    hook_get_shader_definitions = Hook_Source_Declaration({})
    hook_before_first_draw      = Hook_Source_Declaration({})


class Block_Loggers(String_Comparable_Mixin):    
    DRAWHANDLER_LIFECYCLE = Logger_Declaration("INFO")
    SHADER_BATCH_EVENTS   = Logger_Declaration("INFO")
    ANIMATION_LIFECYCLE   = Logger_Declaration("INFO")
    ANIMATION_TICK_EVENTS = Logger_Declaration("INFO")


class Block_RTC_Members(String_Comparable_Mixin):
    DRAW_PHASES = RTC_Member_Declaration()
    SHADERS     = RTC_Member_Declaration()


class Block_Data_Mirrors(String_Comparable_Mixin):
    SHADER_MIRROR = RTC_Member_Data_Mirror_Declaration(
        RTC_key = Block_RTC_Members.SHADERS.name,
        FWC_name = "Wrapper_Shader_Manager",
        mirrored_key_field_names = ["shader_uid"],
        # is_enabled is RTC-only now; BL mirror holds only the uid key + display fields, so
        # there are no user-editable mirrored data fields (the planner never emits an Edit).
        mirrored_data_field_names = [],
        scene_colprop_path = "dgblocks_onscreen_drawing_props.shader_mirror",
    )

class Block_UIList_Configs(String_Comparable_Mixin):
    SHADERS_UILIST = Shared_UIList_Declaration(
        col_names = ["Shader Name", "Type / Draw Phase", "Anims", "Batches", "Enabled"],
        col_widths = [3, 3, 1, 1, 1],
        scene_parent_path = "dgblocks_onscreen_drawing_props",
        scene_colprop_path = "shader_mirror",
        scene_colprop_path_UIList_selection_idx_path = "shader_mirror_selected_idx",
        RTC_key = Block_RTC_Members.SHADERS,
        callback_draw_row =_uilist_draw_uilist_row,
        callback_draw_details_section = _uilist_draw_selection_details,
    )
