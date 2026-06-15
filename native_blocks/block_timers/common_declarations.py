
from ...addon_helpers.data_structures import Hook_Source_Declaration, Logger_Declaration, RTC_Member_Declaration, RTC_Member_Data_Mirror_Declaration, Shared_UIList_Declaration, String_Comparable_Mixin
from ..block_timers.ui import _uilist_draw_selection_details, _uilist_draw_uilist_row

# ==============================================================================================================================
# MAIN BLOCK COMPONENTS
# ==============================================================================================================================

class Block_Hook_Sources(String_Comparable_Mixin):
    hook_get_timer_definitions = Hook_Source_Declaration({})


class Block_Loggers(String_Comparable_Mixin):
    TIMER_LIFECYCLE   = Logger_Declaration("DEBUG")
    TIMER_FIRE_EVENTS = Logger_Declaration("DEBUG")


class Block_RTC_Members(String_Comparable_Mixin):
    TIMERS = RTC_Member_Declaration()


class Block_Data_Mirrors(String_Comparable_Mixin):
    TIMER_MIRROR = RTC_Member_Data_Mirror_Declaration(
        RTC_key                  = Block_RTC_Members.TIMERS.name,
        FWC_name                 = "Wrapper_Timer_Manager",
        mirrored_key_field_names  = ["timer_uid"],
        mirrored_data_field_names = ["is_enabled"],
        scene_colprop_path       = "dgblocks_timers_props.timer_mirror",
    )


class Block_UIList_Configs(String_Comparable_Mixin):
    TIMERS_UILIST = Shared_UIList_Declaration(
        col_names  = ["Timer UID", "Frequency", "Runs", "Enabled"],
        col_widths = [3, 2, 1, 1],
        scene_parent_path                           = "dgblocks_timers_props",
        scene_colprop_path                          = "timer_mirror",
        scene_colprop_path_UIList_selection_idx_path = "timer_mirror_selected_idx",
        RTC_key                                     = Block_RTC_Members.TIMERS,
        callback_draw_row            = _uilist_draw_uilist_row,
        callback_draw_details_section= _uilist_draw_selection_details,
    )
